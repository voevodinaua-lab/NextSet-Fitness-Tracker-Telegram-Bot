import os
import logging
import pg8000
import json
from datetime import datetime
from urllib.parse import urlparse

from utils_constants import DEFAULT_STRENGTH_EXERCISES, DEFAULT_CARDIO_EXERCISES

logger = logging.getLogger(__name__)

# Константы для типов упражнений
STRENGTH_TYPE = 'strength'
CARDIO_TYPE = 'cardio'


def ensure_bot_schema():
    """Создаёт вспомогательные таблицы, если их ещё нет (идемпотентно)."""
    conn = get_db_connection()
    if not conn:
        logger.warning("ensure_bot_schema: DATABASE_URL недоступен, пропуск")
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_hidden_defaults (
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    PRIMARY KEY (user_id, name, type)
                )
                """
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"ensure_bot_schema: {e}")


def _hidden_defaults_rows(user_id):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, type FROM user_hidden_defaults WHERE user_id = %s",
                (user_id,),
            )
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка чтения скрытых упражнений {user_id}: {e}")
        return []


def get_hidden_defaults(user_id):
    """Имена стандартных упражнений, скрытых для пользователя."""
    hidden = {"strength": set(), "cardio": set()}
    for name, type_ in _hidden_defaults_rows(user_id):
        if type_ == STRENGTH_TYPE:
            hidden["strength"].add(name)
        elif type_ == CARDIO_TYPE:
            hidden["cardio"].add(name)
    return hidden


def add_hidden_default_exercise(user_id, name, type_):
    """Скрыть стандартное упражнение из каталога пользователя."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_hidden_defaults (user_id, name, type)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, name, type) DO NOTHING
                """,
                (user_id, name, type_),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка скрытия упражнения {user_id}/{name}: {e}")
        return False


def get_visible_exercise_lists(user_id):
    """Каталог упражнений пользователя: стандартные минус скрытые + свои."""
    hidden = get_hidden_defaults(user_id)
    custom = get_custom_exercises(user_id)

    strength = [n for n in DEFAULT_STRENGTH_EXERCISES if n not in hidden["strength"]]
    for n in custom["strength"]:
        if n not in strength:
            strength.append(n)

    cardio = [n for n in DEFAULT_CARDIO_EXERCISES if n not in hidden["cardio"]]
    for n in custom["cardio"]:
        if n not in cardio:
            cardio.append(n)

    return {"strength": strength, "cardio": cardio}


def remove_exercise_from_user_catalog(user_id, name, exercise_type):
    """Убрать упражнение из списка: своё — удалить из БД; стандартное — скрыть."""
    custom = get_custom_exercises(user_id)
    if name in custom[exercise_type]:
        return delete_custom_exercise(user_id, name, exercise_type)
    if exercise_type == STRENGTH_TYPE and name in DEFAULT_STRENGTH_EXERCISES:
        return add_hidden_default_exercise(user_id, name, STRENGTH_TYPE)
    if exercise_type == CARDIO_TYPE and name in DEFAULT_CARDIO_EXERCISES:
        return add_hidden_default_exercise(user_id, name, CARDIO_TYPE)
    return False

def get_db_connection():
    """Получить соединение с PostgreSQL для Supabase"""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL не установлен")
            return None
        
        url = urlparse(database_url)
        
        # Создаем SSL контекст с отключенной проверкой сертификата
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        conn = pg8000.connect(
            host=url.hostname,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            database=url.path[1:],
            ssl_context=ssl_context,
            timeout=10
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к базе: {e}")
        return None

def create_user(user_id, username, first_name):
    """Создать нового пользователя"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO users (user_id, username, first_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            ''', (user_id, username, first_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания пользователя {user_id}: {e}")
        return False

def get_current_training(user_id):
    """Получить текущую (незавершенную) тренировку пользователя"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT training_id, date_start, comment, measurements
                FROM trainings 
                WHERE user_id = %s AND date_end IS NULL
                ORDER BY date_start DESC 
                LIMIT 1
            ''', (user_id,))
            result = cur.fetchone()
        
        conn.close()
        
        if result:
            training = {
                'training_id': result[0],
                'date_start': result[1].strftime("%d.%m.%Y %H:%M"),
                'comment': result[2] or '',
                'measurements': result[3] or ''
            }
            
            # Загружаем упражнения для этой тренировки
            training['exercises'] = get_training_exercises(result[0])
            return training
        
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка получения текущей тренировки {user_id}: {e}")
        return None

def create_training(user_id):
    """Создать новую тренировку"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        current_date = datetime.now()
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO trainings (user_id, date_start)
                VALUES (%s, %s)
                RETURNING training_id
            ''', (user_id, current_date))
            training_id = cur.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return {
            'training_id': training_id,
            'date_start': current_date.strftime("%d.%m.%Y %H:%M"),
            'exercises': [],
            'comment': '',
            'measurements': ''
        }
    except Exception as e:
        logger.error(f"❌ Ошибка создания тренировки {user_id}: {e}")
        return None

def delete_all_user_data(user_id):
    """Удалить ВСЕ данные пользователя (очистка истории)"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            # Удаляем упражнения из тренировок
            cur.execute('''
                DELETE FROM training_exercises 
                WHERE training_id IN (
                    SELECT training_id FROM trainings WHERE user_id = %s
                )
            ''', (user_id,))
            
            # Удаляем тренировки
            cur.execute('''
                DELETE FROM trainings WHERE user_id = %s
            ''', (user_id,))
            
            # Удаляем пользовательские упражнения
            cur.execute('''
                DELETE FROM custom_exercises WHERE user_id = %s
            ''', (user_id,))

            cur.execute(
                "DELETE FROM user_hidden_defaults WHERE user_id = %s",
                (user_id,),
            )
            
            # Удаляем замеры
            cur.execute('''
                DELETE FROM user_measurements WHERE user_id = %s
            ''', (user_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Все данные пользователя {user_id} удалены")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления данных пользователя {user_id}: {e}")
        return False

def save_training_measurements(training_id, measurements):
    """Сохранить замеры для тренировки"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                UPDATE trainings 
                SET measurements = %s
                WHERE training_id = %s
            ''', (measurements, training_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения замеров {training_id}: {e}")
        return False

def add_exercise_to_training(training_id, exercise_data):
    """Добавить упражнение к тренировке"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            if exercise_data['type'] == STRENGTH_TYPE:
                # СЕРИАЛИЗУЕМ список в JSON строку
                import json
                sets_data = exercise_data.get('sets', [])
                sets_json = json.dumps(sets_data)  # ← ВАЖНО!
                
                cur.execute('''
                    INSERT INTO training_exercises 
                    (training_id, name, type, sets)
                    VALUES (%s, %s, %s, %s)
                ''', (
                    training_id, 
                    exercise_data['name'], 
                    STRENGTH_TYPE,
                    sets_json  # ← передаем JSON строку
                ))
            else:  # CARDIO
                cur.execute('''
                    INSERT INTO training_exercises 
                    (training_id, name, type, time_minutes, distance_meters, speed_kmh, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    training_id,
                    exercise_data['name'],
                    CARDIO_TYPE,
                    exercise_data.get('time_minutes'),
                    exercise_data.get('distance_meters'),
                    exercise_data.get('speed_kmh'),
                    exercise_data.get('details', '')
                ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления упражнения {training_id}: {e}")
        return False

def get_training_exercises(training_id):
    """Получить все упражнения для тренировки"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT exercise_id, name, type, sets, time_minutes, 
                       distance_meters, speed_kmh, details
                FROM training_exercises 
                WHERE training_id = %s
                ORDER BY exercise_id
            ''', (training_id,))
            results = cur.fetchall()
        
        conn.close()
        
        exercises = []
        for row in results:
            exercise = {
                'exercise_id': row[0],
                'name': row[1],
                'type': row[2]
            }
            
            if row[2] == STRENGTH_TYPE:
                exercise['sets'] = row[3] or []
                exercise['is_cardio'] = False
            else:  # CARDIO
                exercise.update({
                    'time_minutes': row[4],
                    'distance_meters': row[5],
                    'speed_kmh': row[6],
                    'details': row[7] or '',
                    'is_cardio': True
                })
            
            exercises.append(exercise)
        
        return exercises
    except Exception as e:
        logger.error(f"❌ Ошибка получения упражнений {training_id}: {e}")
        return []

def finish_training(training_id, comment=""):
    """Завершить тренировку"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                UPDATE trainings 
                SET date_end = CURRENT_TIMESTAMP, comment = %s
                WHERE training_id = %s
            ''', (comment, training_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка завершения тренировки {training_id}: {e}")
        return False

def get_user_trainings(user_id, limit=10):
    """Получить историю тренировок пользователя"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT training_id, date_start, date_end, comment, measurements
                FROM trainings 
                WHERE user_id = %s AND date_end IS NOT NULL
                ORDER BY date_start DESC
                LIMIT %s
            ''', (user_id, limit))
            results = cur.fetchall()
        
        conn.close()
        
        trainings = []
        for row in results:
            training = {
                'training_id': row[0],
                'date_start': row[1].strftime("%d.%m.%Y %H:%M"),
                'date_end': row[2].strftime("%d.%m.%Y %H:%M") if row[2] else None,
                'comment': row[3] or '',
                'measurements': row[4] or '',
                'exercises': get_training_exercises(row[0])
            }
            trainings.append(training)
        
        return trainings
    except Exception as e:
        logger.error(f"❌ Ошибка получения истории тренировок {user_id}: {e}")
        return []

# Функции для работы с пользовательскими упражнениями
def get_custom_exercises(user_id):
    """Получить пользовательские упражнения"""
    conn = get_db_connection()
    if not conn:
        return {'strength': [], 'cardio': []}
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT name, type FROM custom_exercises 
                WHERE user_id = %s
            ''', (user_id,))
            results = cur.fetchall()
        
        conn.close()
        
        exercises = {'strength': [], 'cardio': []}
        for name, type_ in results:
            exercises[type_].append(name)
        
        return exercises
    except Exception as e:
        logger.error(f"❌ Ошибка получения упражнений {user_id}: {e}")
        return {'strength': [], 'cardio': []}

def add_custom_exercise(user_id, name, type_):
    """Добавить пользовательское упражнение"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO custom_exercises (user_id, name, type)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, name, type) DO NOTHING
            ''', (user_id, name, type_))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления упражнения {user_id}: {e}")
        return False

def delete_custom_exercise(user_id, name, type_):
    """Удалить пользовательское упражнение"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                DELETE FROM custom_exercises 
                WHERE user_id = %s AND name = %s AND type = %s
            ''', (user_id, name, type_))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления упражнения {user_id}: {e}")
        return False

# Функции для работы с замерами
def save_measurement(user_id, measurements):
    """Сохранить замеры пользователя"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO user_measurements (user_id, measurement_date, measurements)
                VALUES (%s, CURRENT_TIMESTAMP, %s)
            ''', (user_id, measurements))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения замеров {user_id}: {e}")
        return False

def get_measurements_history(user_id, limit=10):
    """Получить историю замеров"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT measurement_date, measurements
                FROM user_measurements 
                WHERE user_id = %s
                ORDER BY measurement_date DESC
                LIMIT %s
            ''', (user_id, limit))
            results = cur.fetchall()
        
        conn.close()
        
        measurements = []
        for date, meas in results:
            measurements.append({
                'date': date.strftime("%d.%m.%Y %H:%M"),
                'measurements': meas
            })
        
        return measurements
    except Exception as e:
        logger.error(f"❌ Ошибка получения замеров {user_id}: {e}")
        return []

