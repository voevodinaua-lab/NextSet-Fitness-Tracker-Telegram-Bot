import os
import logging
import pg8000
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Константы для типов упражнений
STRENGTH_TYPE = 'strength'
CARDIO_TYPE = 'cardio'

def get_db_connection():
    """Получить соединение с PostgreSQL для Supabase"""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL не установлен")
            return None
        
        url = urlparse(database_url)
        
        conn = pg8000.connect(
            host=url.hostname,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            database=url.path[1:],
            ssl_context=True,
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
                cur.execute('''
                    INSERT INTO training_exercises 
                    (training_id, name, type, sets)
                    VALUES (%s, %s, %s, %s)
                ''', (
                    training_id, 
                    exercise_data['name'], 
                    STRENGTH_TYPE,
                    exercise_data.get('sets', [])
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