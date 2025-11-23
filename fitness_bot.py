import os
import logging
import sys
import socket
import pg8000
import json
import threading
import requests
import time
import csv
import io
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния бота
(
    MAIN_MENU, TRAINING, CHOOSE_EXERCISE, INPUT_SETS,
    ADD_CUSTOM_EXERCISE, ADD_CUSTOM_CARDIO, INPUT_MEASUREMENTS, 
    INPUT_COMMENT, STATS_PERIOD, EXPORT_MENU, EXPORT_PERIOD,
    EXERCISES_MANAGEMENT, DELETE_EXERCISE, CHOOSE_EXERCISE_TYPE,
    CARDIO_TYPE_SELECTION, INPUT_CARDIO_DETAILS, CONFIRM_FINISH,
    EDIT_TRAINING, EDIT_EXERCISE, INPUT_MEASUREMENTS_CHOICE
) = range(20)

# База упражнений по умолчанию
DEFAULT_STRENGTH_EXERCISES = [
    "Румынская тяга", "Ягодичный мостик", "Болгарский выпад",
    "Скручивания (пресс) в тренажере", "Воздушные выпады с отягощением на степе",
    "Отведения ноги назад в кроссовере", "Отведение ноги в сторону в кроссовере",
    "Скручивания и разгибание колен на полу"
]

DEFAULT_CARDIO_EXERCISES = ["Бег на дорожке"]

# Глобальная переменная для статуса базы данных
DB_AVAILABLE = False

def test_db_connection_quick():
    """Быстрая проверка подключения к базе с таймаутом"""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL не установлен")
            return False
        
        from urllib.parse import urlparse
        url = urlparse(database_url)
        
        print("🔧 Быстрая проверка подключения...")
        
        # Устанавливаем таймаут для сокета
        socket.setdefaulttimeout(10)
        
        conn = pg8000.connect(
            host=url.hostname,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            database=url.path[1:],
            ssl_context=True,
            timeout=5  # Короткий таймаут
        )
        
        # Быстрая проверка - просто попробуем выполнить простой запрос
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
            result = cur.fetchone()
        
        conn.close()
        print("🎉 База данных доступна!")
        return True
        
    except Exception as e:
        print(f"⚠️ База данных недоступна: {e}")
        return False

def get_db_connection():
    """Получить соединение с PostgreSQL для Supabase"""
    global DB_AVAILABLE
    
    if not DB_AVAILABLE:
        return None
        
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            return None
        
        from urllib.parse import urlparse
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

def init_database():
    """Инициализация базы данных"""
    global DB_AVAILABLE
    
    if not DB_AVAILABLE:
        print("❌ Пропускаем инициализацию - база недоступна")
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    user_data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return False

# Временное хранилище в памяти (на случай недоступности БД)
user_data_cache = {}

def save_user_data(user_id, user_data):
    """Сохранить данные пользователя"""
    global DB_AVAILABLE
    
    # Всегда сохраняем в кеш
    user_data_cache[user_id] = user_data
    
    # Пытаемся сохранить в базу, если доступна
    if DB_AVAILABLE:
        conn = get_db_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO users (user_id, user_data, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET user_data = %s, updated_at = CURRENT_TIMESTAMP
                ''', (user_id, json.dumps(user_data), json.dumps(user_data)))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в БД {user_id}: {e}")
            DB_AVAILABLE = False  # Помечаем базу как недоступную
            return False
    
    return True  # Возвращаем True, т.к. данные сохранены в кеш

def load_user_data(user_id):
    """Загрузить данные пользователя"""
    global DB_AVAILABLE
    
    # Сначала пробуем из кеша
    if user_id in user_data_cache:
        return user_data_cache[user_id]
    
    # Пытаемся из базы, если доступна
    if DB_AVAILABLE:
        conn = get_db_connection()
        if not conn:
            return get_default_user_data()
        
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT user_data FROM users WHERE user_id = %s', (user_id,))
                result = cur.fetchone()
            
            conn.close()
            
            if result and result[0]:
                user_data = json.loads(result[0])
                user_data_cache[user_id] = user_data  # Сохраняем в кеш
                return user_data
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки из БД {user_id}: {e}")
            DB_AVAILABLE = False  # Помечаем базу как недоступную
    
    # Возвращаем данные по умолчанию
    return get_default_user_data()

def get_default_user_data():
    """Получить данные по умолчанию для нового пользователя"""
    return {
        'trainings': [],
        'current_training': None,
        'measurements_history': [],
        'custom_exercises': {
            'strength': [],
            'cardio': []
        },
        'statistics': {
            'total_trainings': 0,
            'total_exercises': 0,
            'total_strength_exercises': 0,
            'total_cardio_exercises': 0,
            'weekly_stats': {},
            'monthly_stats': {},
            'yearly_stats': {},
            'exercise_stats': {}  # Новая статистика по упражнениям
        }
    }

def get_user_data(user_id):
    """Получить данные пользователя"""
    return load_user_data(user_id)

def get_user_exercises(user_id):
    """Получить все упражнения пользователя"""
    user_data = get_user_data(user_id)
    return {
        'strength': DEFAULT_STRENGTH_EXERCISES + user_data['custom_exercises']['strength'],
        'cardio': DEFAULT_CARDIO_EXERCISES + user_data['custom_exercises']['cardio']
    }

def generate_csv_export(user_id, period_type="current_month"):
    """Генерация CSV файла для скачивания"""
    user_data = get_user_data(user_id)
    
    if not user_data or not user_data['trainings']:
        return None
    
    # Определяем период
    today = datetime.now()
    if period_type == "current_month":
        target_month = today.month
        target_year = today.year
        trainings = [t for t in user_data['trainings'] 
                    if datetime.strptime(t['date_start'], "%d.%m.%Y %H:%M").month == target_month
                    and datetime.strptime(t['date_start'], "%d.%m.%Y %H:%M").year == target_year]
    elif period_type == "all_time":
        trainings = user_data['trainings']
    else:
        trainings = user_data['trainings']
    
    if not trainings:
        return None
    
    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовок таблицы
    writer.writerow(['Дата тренировки', 'Тип упражнения', 'Название упражнения', 'Вес (кг)', 'Повторения', 'Время (мин)', 'Дистанция (м)', 'Скорость (км/ч)', 'Детали'])
    
    # Данные тренировок
    for training in trainings:
        training_date = training['date_start']
        
        for exercise in training['exercises']:
            if exercise.get('is_cardio'):
                # Кардио упражнение
                writer.writerow([
                    training_date,
                    'Кардио',
                    exercise['name'],
                    '',  # Вес
                    '',  # Повторения
                    exercise.get('time_minutes', ''),
                    exercise.get('distance_meters', ''),
                    exercise.get('speed_kmh', ''),
                    exercise.get('details', '')
                ])
            else:
                # Силовое упражнение
                for set_data in exercise.get('sets', []):
                    writer.writerow([
                        training_date,
                        'Силовое',
                        exercise['name'],
                        set_data['weight'],
                        set_data['reps'],
                        '',  # Время
                        '',  # Дистанция
                        '',  # Скорость
                        ''   # Детали
                    ])
    
    return output.getvalue()

def update_statistics(user_id, training):
    """Обновление статистики пользователя"""
    user_data = get_user_data(user_id)
    if not user_data:
        return
    
    stats = user_data['statistics']
    
    # Подсчет упражнений по типам
    strength_count = 0
    cardio_count = 0
    
    for exercise in training['exercises']:
        if exercise.get('is_cardio'):
            cardio_count += 1
        else:
            strength_count += 1
    
    # Общая статистика
    stats['total_trainings'] += 1
    stats['total_exercises'] += len(training['exercises'])
    stats['total_strength_exercises'] += strength_count
    stats['total_cardio_exercises'] += cardio_count
    
    # Статистика по датам
    training_date = datetime.strptime(training['date_start'], "%d.%m.%Y %H:%M")
    week_key = training_date.strftime("%Y-%W")
    month_key = training_date.strftime("%Y-%m")
    year_key = training_date.strftime("%Y")
    
    # Недельная статистика
    if week_key not in stats['weekly_stats']:
        stats['weekly_stats'][week_key] = {
            'trainings': 0, 
            'exercises': 0,
            'strength_exercises': 0,
            'cardio_exercises': 0,
            'period_name': f"Неделя {training_date.strftime('%W')} ({training_date.strftime('%d.%m')})"
        }
    stats['weekly_stats'][week_key]['trainings'] += 1
    stats['weekly_stats'][week_key]['exercises'] += len(training['exercises'])
    stats['weekly_stats'][week_key]['strength_exercises'] += strength_count
    stats['weekly_stats'][week_key]['cardio_exercises'] += cardio_count
    
    # Месячная статистика
    if month_key not in stats['monthly_stats']:
        stats['monthly_stats'][month_key] = {
            'trainings': 0, 
            'exercises': 0,
            'strength_exercises': 0,
            'cardio_exercises': 0,
            'period_name': f"{training_date.strftime('%B %Y')}"
        }
    stats['monthly_stats'][month_key]['trainings'] += 1
    stats['monthly_stats'][month_key]['exercises'] += len(training['exercises'])
    stats['monthly_stats'][month_key]['strength_exercises'] += strength_count
    stats['monthly_stats'][month_key]['cardio_exercises'] += cardio_count
    
    # Годовая статистика
    if year_key not in stats['yearly_stats']:
        stats['yearly_stats'][year_key] = {
            'trainings': 0, 
            'exercises': 0,
            'strength_exercises': 0,
            'cardio_exercises': 0,
            'period_name': f"{training_date.strftime('%Y')} год"
        }
    stats['yearly_stats'][year_key]['trainings'] += 1
    stats['yearly_stats'][year_key]['exercises'] += len(training['exercises'])
    stats['yearly_stats'][year_key]['strength_exercises'] += strength_count
    stats['yearly_stats'][year_key]['cardio_exercises'] += cardio_count
    
    # Статистика по упражнениям
    for exercise in training['exercises']:
        exercise_name = exercise['name']
        if exercise_name not in stats['exercise_stats']:
            stats['exercise_stats'][exercise_name] = {
                'type': 'cardio' if exercise.get('is_cardio') else 'strength',
                'total_count': 0,
                'history': []
            }
        
        stats['exercise_stats'][exercise_name]['total_count'] += 1
        
        exercise_record = {
            'date': training['date_start'],
            'training_date': training_date.strftime("%Y-%m-%d")
        }
        
        if exercise.get('is_cardio'):
            # Кардио статистика
            exercise_record.update({
                'time_minutes': exercise.get('time_minutes'),
                'distance_meters': exercise.get('distance_meters'),
                'speed_kmh': exercise.get('speed_kmh')
            })
        else:
            # Силовая статистика
            if exercise.get('sets'):
                max_weight = max([s['weight'] for s in exercise['sets']])
                total_reps = sum([s['reps'] for s in exercise['sets']])
                total_sets = len(exercise['sets'])
                exercise_record.update({
                    'max_weight': max_weight,
                    'total_reps': total_reps,
                    'total_sets': total_sets,
                    'sets': exercise['sets']
                })
        
        stats['exercise_stats'][exercise_name]['history'].append(exercise_record)
    
    # Сохраняем обновленные данные
    save_user_data(user_id, user_data)

# Асинхронные функции бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало работы с ботом"""
    user = update.message.from_user
    
    # Инициализируем данные пользователя при первом старте
    user_data = load_user_data(user.id)
    
    welcome_text = f"""
Привет, {user.first_name}! 🏋️

Я твой фитнес-трекер! Выбери действие:
    """
    
    keyboard = [
        ['💪 Начать тренировку', '📊 История тренировок'],
        ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
        ['📤 Выгрузка данных', '❓ Помощь']
    ]
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return MAIN_MENU

async def start_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало тренировки"""
    user_id = update.message.from_user.id
    
    # Создаем новую тренировку
    current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    user_data = get_user_data(user_id)
    user_data['current_training'] = {
        'date_start': current_date,
        'exercises': [],
        'comment': '',
        'measurements': ''
    }
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    keyboard = [
        ['📝 Ввести замеры', '⏭️ Отказаться'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        f"🎯 Отлично стартуем! Сегодня {current_date}\n\n"
        "📏 Хотите ли ввести замеры перед тренировкой?\n"
        "(например: вес 65кг, талия 70см, бедра 95см)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return INPUT_MEASUREMENTS_CHOICE

async def handle_measurements_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора ввода замеров"""
    choice = update.message.text
    
    if choice == '🔙 Главное меню':
        return await start(update, context)
    
    elif choice == '⏭️ Отказаться':
        # Пропускаем ввод замеров, переходим к тренировке
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        
        await update.message.reply_text(
            "✅ Начинаем тренировку! Выберите тип упражнения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING
    
    elif choice == '📝 Ввести замеры':
        await update.message.reply_text(
            "Введите ваши замеры:\n"
            "(например: вес 65кг, талия 70см, бедра 95см)\n"
            "Или напишите 'пропустить' чтобы продолжить без замеров",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_MEASUREMENTS

async def save_measurements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение замеров и переход к тренировке"""
    user_id = update.message.from_user.id
    
    try:
        user_data = get_user_data(user_id)
        measurements = update.message.text
        
        if measurements.lower() != 'пропустить':
            # СОХРАНЯЕМ ТОЛЬКО В ПАМЯТИ, ЕСЛИ БАЗА НЕДОСТУПНА
            if user_data and 'current_training' in user_data:
                user_data['current_training']['measurements'] = measurements
                # Сохраняем замеры в историю (в памяти)
                if 'measurements_history' not in user_data:
                    user_data['measurements_history'] = []
                user_data['measurements_history'].append({
                    'date': datetime.now().strftime("%d.%m.%Y %H:%M"),
                    'measurements': measurements
                })
            
            # Пытаемся сохранить в базу, но не падаем при ошибке
            try:
                save_user_data(user_id, user_data)
            except Exception as e:
                print(f"⚠️ Не удалось сохранить в базу: {e}")
        
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        
        await update.message.reply_text(
            "✅ Замеры сохранены! Выберите тип упражнения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING
        
    except Exception as e:
        print(f"❌ Ошибка в save_measurements: {e}")
        # Продолжаем работу даже при ошибке
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        
        await update.message.reply_text(
            "✅ Продолжаем тренировку! Выберите тип упражнения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING

async def show_strength_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать силовые упражнения в виде кнопок"""
    user_id = update.message.from_user.id
    exercises = get_user_exercises(user_id)['strength']
    
    # Создаем клавиатуру с упражнениями
    keyboard = []
    for i in range(0, len(exercises), 2):
        row = exercises[i:i+2]
        keyboard.append(row)
    
    keyboard.append(['🔙 Назад к тренировке'])
    
    await update.message.reply_text(
        "💪 Выберите силовое упражнение:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_EXERCISE

async def handle_exercise_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора упражнения"""
    exercise_name = update.message.text
    
    if exercise_name == '🔙 Назад к тренировке':
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        await update.message.reply_text(
            "Выберите тип упражнения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING
    
    user_id = update.message.from_user.id
    
    # Проверяем тип упражнения
    user_exercises = get_user_exercises(user_id)
    is_cardio = exercise_name in user_exercises['cardio']
    
    # Сохраняем выбранное упражнение
    context.user_data['current_exercise'] = {
        'name': exercise_name,
        'is_cardio': is_cardio
    }
    
    if is_cardio:
        # Для кардио сразу переходим к выбору формата
        keyboard = [
            ['⏱️ Мин/Метры', '🚀 Км/Час'],
            ['🔙 Назад к кардио']
        ]
        
        await update.message.reply_text(
            f"🏃 Выбрано: {exercise_name}\n\n"
            "Выберите формат ввода:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CARDIO_TYPE_SELECTION
    else:
        # Для силового упражнения запрашиваем подходы
        context.user_data['current_exercise']['sets'] = []
        
        await update.message.reply_text(
            f"💪 Выбрано: {exercise_name}\n\n"
            "Введите подходы в формате (каждый подход с новой строки):\n"
            "**Вес Количество_повторений**\n\n"
            "📝 Пример:\n"
            "50 12\n"
            "55 10\n"
            "60 8\n\n"
            "Или введите один подход: 50 12",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_SETS

async def handle_set_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода подходов - поддерживает многострочный ввод"""
    user_id = update.message.from_user.id
    text = update.message.text
    
    # Разбиваем на строки для обработки нескольких подходов
    lines = text.strip().split('\n')
    valid_sets = []
    errors = []
    
    for line_num, line in enumerate(lines, 1):
        if not line.strip():  # Пропускаем пустые строки
            continue
            
        # Парсим ввод: поддерживаем разные форматы
        line_clean = line.replace(',', '.').replace('/', ' ').replace('х', ' ').replace('x', ' ')
        parts = line_clean.split()
        
        if len(parts) >= 2:
            try:
                weight = float(parts[0])
                reps = int(parts[1])
                
                valid_sets.append({
                    'weight': weight,
                    'reps': reps
                })
                
            except (ValueError, IndexError):
                errors.append(f"Строка {line_num}: неверный формат '{line}'")
        else:
            errors.append(f"Строка {line_num}: недостаточно данных '{line}'")
    
    # Если есть валидные подходы, добавляем их
    if valid_sets:
        context.user_data['current_exercise']['sets'].extend(valid_sets)
        
        # Формируем текст с текущими подходами
        sets_count = len(context.user_data['current_exercise']['sets'])
        sets_text = "✅ Текущие подходы:\n"
        for i, set_data in enumerate(context.user_data['current_exercise']['sets'], 1):
            sets_text += f"{i}. {set_data['weight']}кг × {set_data['reps']} повторений\n"
        
        # Сообщение об ошибках, если они есть
        error_text = ""
        if errors:
            error_text = "\n❌ Ошибки:\n" + "\n".join(errors) + "\n"
        
        keyboard = [['✅ Добавить еще подходы', '💾 Сохранить упражнение'], ['❌ Отменить упражнение']]
        
        await update.message.reply_text(
            f"{sets_text}\n"
            f"Всего подходов: {sets_count}\n"
            f"{error_text}\n"
            "Выберите действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return INPUT_SETS
        
    else:
        # Если нет валидных подходов, показываем ошибку
        await update.message.reply_text(
            "❌ Не удалось распознать подходы.\n\n"
            "Введите подходы в формате (каждый подход с новой строки):\n"
            "**Вес Количество_повторений**\n\n"
            "📝 Пример:\n"
            "50 12\n"
            "55 10\n"
            "60 8\n\n"
            "Или введите один подход: 50 12"
        )
        return INPUT_SETS

async def add_another_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление еще подходов"""
    await update.message.reply_text(
        "Введите следующие подходы в формате (каждый подход с новой строки):\n"
        "**Вес Количество_повторений**\n\n"
        "📝 Пример:\n"
        "65 6\n"
        "70 4\n\n"
        "Или введите один подход: 65 6",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_SETS

async def save_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение упражнения с подходами"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if 'current_exercise' not in context.user_data:
        await update.message.reply_text("❌ Нет данных для сохранения.")
        return await show_strength_exercises(update, context)
    
    # Сохраняем упражнение
    exercise_data = context.user_data['current_exercise'].copy()
    
    # Убираем время из упражнения
    if 'timestamp' in exercise_data:
        del exercise_data['timestamp']
    
    user_data['current_training']['exercises'].append(exercise_data)
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    # Формируем текст сохраненного упражнения
    if exercise_data.get('is_cardio'):
        exercise_text = f"🏃 {exercise_data['name']}:\n"
        exercise_text += f"Детали: {exercise_data['details']}\n"
    else:
        exercise_text = f"💪 {exercise_data['name']}:\n"
        for i, set_data in enumerate(exercise_data['sets'], 1):
            exercise_text += f"{i}. {set_data['weight']}кг × {set_data['reps']} повторений\n"
    
    # Очищаем временные данные
    context.user_data.pop('current_exercise', None)
    context.user_data.pop('cardio_type', None)
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        f"✅ Упражнение сохранено!\n\n{exercise_text}\n"
        "Выберите следующее упражнение или завершите тренировку:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    return TRAINING

async def show_exercises_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать управление упражнениями"""
    user_id = update.message.from_user.id
    exercises = get_user_exercises(user_id)
    
    exercises_text = "📝 Ваши упражнения:\n\n"
    exercises_text += "💪 Силовые:\n"
    for ex in exercises['strength']:
        exercises_text += f"• {ex}\n"
    
    exercises_text += "\n🏃 Кардио:\n"
    for ex in exercises['cardio']:
        exercises_text += f"• {ex}\n"
    
    keyboard = [
        ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        exercises_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return EXERCISES_MANAGEMENT

async def choose_exercise_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор типа упражнения для добавления"""
    keyboard = [
        ['💪 Силовое упражнение', '🏃 Кардио упражнение'],
        ['🔙 Назад к управлению упражнениями']
    ]
    
    await update.message.reply_text(
        "Выберите тип упражнения для добавления:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_EXERCISE_TYPE

async def add_custom_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление пользовательского упражнения"""
    exercise_type = update.message.text
    
    if exercise_type == '🔙 Назад к управлению упражнениями':
        return await show_exercises_management(update, context)
    
    if '💪 Силовое' in exercise_type:
        context.user_data['adding_exercise_type'] = 'strength'
        await update.message.reply_text(
            "Введите название нового силового упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
    elif '🏃 Кардио' in exercise_type:
        context.user_data['adding_exercise_type'] = 'cardio'
        await update.message.reply_text(
            "Введите название нового кардио упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
    
    return ADD_CUSTOM_EXERCISE

async def save_custom_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение пользовательского упражнения"""
    user_id = update.message.from_user.id
    exercise_name = update.message.text
    exercise_type = context.user_data.get('adding_exercise_type', 'strength')
    
    user_data = get_user_data(user_id)
    if exercise_name not in user_data['custom_exercises'][exercise_type]:
        user_data['custom_exercises'][exercise_type].append(exercise_name)
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    await update.message.reply_text(f"✅ Упражнение '{exercise_name}' добавлено в ваш список!")
    
    # Очищаем временные данные
    context.user_data.pop('adding_exercise_type', None)
    
    return await show_exercises_management(update, context)

async def show_delete_exercise_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню удаления упражнений"""
    user_id = update.message.from_user.id
    exercises = get_user_exercises(user_id)
    
    # Создаем клавиатуру со всеми упражнениями
    keyboard = []
    
    # Силовые упражнения
    for ex in exercises['strength']:
        keyboard.append([f"💪 {ex}"])
    
    # Кардио упражнения
    for ex in exercises['cardio']:
        keyboard.append([f"🏃 {ex}"])
    
    keyboard.append(['🔙 Назад к управлению упражнениями'])
    
    await update.message.reply_text(
        "🗑️ Выберите упражнение для удаления:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return DELETE_EXERCISE

async def delete_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Удаление выбранного упражнения"""
    user_id = update.message.from_user.id
    exercise_with_emoji = update.message.text
    exercise_name = exercise_with_emoji[2:]  # Убираем эмодзи
    
    user_data = get_user_data(user_id)
    
    # Пытаемся удалить из стандартных упражнений
    if exercise_name in DEFAULT_STRENGTH_EXERCISES:
        DEFAULT_STRENGTH_EXERCISES.remove(exercise_name)
        await update.message.reply_text(f"✅ Упражнение '{exercise_name}' удалено!")
    elif exercise_name in DEFAULT_CARDIO_EXERCISES:
        DEFAULT_CARDIO_EXERCISES.remove(exercise_name)
        await update.message.reply_text(f"✅ Упражнение '{exercise_name}' удалено!")
    # Пытаемся удалить из пользовательских упражнений
    elif exercise_name in user_data['custom_exercises']['strength']:
        user_data['custom_exercises']['strength'].remove(exercise_name)
        await update.message.reply_text(f"✅ Упражнение '{exercise_name}' удалено!")
    elif exercise_name in user_data['custom_exercises']['cardio']:
        user_data['custom_exercises']['cardio'].remove(exercise_name)
        await update.message.reply_text(f"✅ Упражнение '{exercise_name}' удалено!")
    else:
        await update.message.reply_text("❌ Упражнение не найдено.")
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    return await show_exercises_management(update, context)

async def handle_cardio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кардио упражнений"""
    user_id = update.message.from_user.id
    exercises = get_user_exercises(user_id)['cardio']
    
    keyboard = [[exercise] for exercise in exercises]
    keyboard.append(['✏️ Добавить кардио упражнение'])
    keyboard.append(['🔙 Назад к тренировке'])
    
    await update.message.reply_text(
        "🏃 Выберите кардио упражнение:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_EXERCISE

async def handle_cardio_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора кардио упражнения"""
    exercise_name = update.message.text
    
    if exercise_name == '✏️ Добавить кардио упражнение':
        context.user_data['adding_exercise_type'] = 'cardio'
        await update.message.reply_text(
            "Введите название нового кардио упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_CUSTOM_CARDIO
    
    if exercise_name == '🔙 Назад к тренировке':
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        await update.message.reply_text(
            "Выберите тип упражнения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING
    
    # Сохраняем выбранное кардио упражнение
    context.user_data['current_exercise'] = {
        'name': exercise_name,
        'is_cardio': True
    }
    
    # Предлагаем выбрать формат ввода
    keyboard = [
        ['⏱️ Мин/Метры', '🚀 Км/Час'],
        ['🔙 Назад к кардио']
    ]
    
    await update.message.reply_text(
        f"🏃 Выбрано: {exercise_name}\n\n"
        "Выберите формат ввода:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CARDIO_TYPE_SELECTION

async def handle_cardio_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора формата кардио"""
    cardio_type = update.message.text
    
    if cardio_type == '🔙 Назад к кардио':
        return await handle_cardio(update, context)
    
    context.user_data['cardio_type'] = cardio_type
    
    if cardio_type == '⏱️ Мин/Метры':
        await update.message.reply_text(
            "Введите время и дистанцию в формате:\n"
            "**Время_в_минутах Дистанция_в_метрах**\n\n"
            "📝 Пример: 30 5000 (30 минут, 5000 метров)",
            reply_markup=ReplyKeyboardRemove()
        )
    elif cardio_type == '🚀 Км/Час':
        await update.message.reply_text(
            "Введите время и скорость в формате:\n"
            "**Время_в_минутах Скорость_км/ч**\n\n"
            "📝 Пример: 30 10 (30 минут, 10 км/ч)",
            reply_markup=ReplyKeyboardRemove()
        )
    
    return INPUT_CARDIO_DETAILS

async def handle_cardio_details_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода деталей кардио"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    text = update.message.text
    
    try:
        parts = text.split()
        if len(parts) != 2:
            raise ValueError("Нужно ввести два числа")
        
        time_minutes = int(parts[0])
        value = float(parts[1])
        
        cardio_type = context.user_data.get('cardio_type', '⏱️ Мин/Метры')
        
        # Сохраняем кардио в тренировку
        exercise_data = context.user_data['current_exercise'].copy()
        exercise_data['is_cardio'] = True
        
        if cardio_type == '⏱️ Мин/Метры':
            exercise_data['details'] = f"{time_minutes} минут, {value} метров"
            exercise_data['cardio_format'] = 'min_meters'
            exercise_data['time_minutes'] = time_minutes
            exercise_data['distance_meters'] = value
        else:  # 🚀 Км/Час
            exercise_data['details'] = f"{time_minutes} минут, {value} км/ч"
            exercise_data['cardio_format'] = 'km_h'
            exercise_data['time_minutes'] = time_minutes
            exercise_data['speed_kmh'] = value
        
        user_data['current_training']['exercises'].append(exercise_data)
        
        # Сохраняем данные
        save_user_data(user_id, user_data)
        
        # Очищаем временные данные
        context.user_data.pop('current_exercise', None)
        context.user_data.pop('cardio_type', None)
        
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        
        await update.message.reply_text(
            f"✅ Кардио сохранено!\n{exercise_data['name']}: {exercise_data['details']}\n\n"
            "Выберите следующее упражнение или завершите тренировку:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return TRAINING
        
    except (ValueError, IndexError):
        cardio_type = context.user_data.get('cardio_type', '⏱️ Мин/Метры')
        
        if cardio_type == '⏱️ Мин/Метры':
            await update.message.reply_text(
                "❌ Неверный формат. Введите два числа:\n"
                "**Время_в_минутах Дистанция_в_метрах**\n\n"
                "📝 Пример: 30 5000"
            )
        else:
            await update.message.reply_text(
                "❌ Неверный формат. Введите два числа:\n"
                "**Время_в_минутах Скорость_км/ч**\n\n"
                "📝 Пример: 30 10"
            )
        return INPUT_CARDIO_DETAILS

async def add_custom_cardio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление пользовательского кардио упражнения"""
    exercise_name = update.message.text
    user_id = update.message.from_user.id
    
    user_data = get_user_data(user_id)
    if exercise_name not in user_data['custom_exercises']['cardio']:
        user_data['custom_exercises']['cardio'].append(exercise_name)
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    await update.message.reply_text(f"✅ Кардио упражнение '{exercise_name}' добавлено!")
    
    # Возвращаемся к выбору кардио упражнений
    return await handle_cardio(update, context)

async def cancel_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущего упражнения"""
    exercise_name = context.user_data.get('current_exercise', {}).get('name', 'упражнение')
    context.user_data.pop('current_exercise', None)
    context.user_data.pop('cardio_type', None)
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        f"❌ {exercise_name} - удалено",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    return TRAINING

async def finish_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершение тренировки - показ сводки"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['current_training']['exercises']:
        await update.message.reply_text(
            "❌ В тренировке нет упражнений. Добавьте хотя бы одно упражнение перед завершением.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Силовые упражнения', '🏃 Кардио'],
                ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
            ], resize_keyboard=True)
        )
        return TRAINING
    
    # Формируем сводку по тренировке
    training = user_data['current_training']
    
    report = "📊 СВОДКА ПО ТРЕНИРОВКЕ\n\n"
    report += f"📅 Дата: {training['date_start']}\n\n"
    
    if training['measurements'] and training['measurements'] != 'пропустить':
        report += f"📏 Замеры: {training['measurements']}\n\n"
    
    report += "💪 Выполненные упражнения:\n\n"
    
    total_exercises = len(training['exercises'])
    strength_count = 0
    cardio_count = 0
    
    for i, exercise in enumerate(training['exercises'], 1):
        if exercise.get('is_cardio'):
            cardio_count += 1
            report += f"🏃 {i}. {exercise['name']}\n"
            report += f"   Детали: {exercise['details']}\n\n"
        else:
            strength_count += 1
            report += f"💪 {i}. {exercise['name']}\n"
            for j, set_data in enumerate(exercise['sets'], 1):
                report += f"   {j}. {set_data['weight']}кг × {set_data['reps']}\n"
            report += "\n"
    
    report += f"📊 Всего упражнений: {total_exercises}\n"
    report += f"• Силовых: {strength_count}\n"
    report += f"• Кардио: {cardio_count}\n"
    
    keyboard = [
        ['✅ Точно завершить', '✏️ Скорректировать'],
        ['🔙 Продолжить тренировку']
    ]
    
    await update.message.reply_text(
        report,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CONFIRM_FINISH

async def handle_finish_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения завершения тренировки"""
    choice = update.message.text
    
    if choice == '🔙 Продолжить тренировку':
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        await update.message.reply_text(
            "Продолжаем тренировку! Выберите действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING
    
    elif choice == '✏️ Скорректировать':
        keyboard = [
            ['📝 Добавить упражнение', '🗑️ Удалить упражнение'],
            ['🔙 Назад к сводке']
        ]
        await update.message.reply_text(
            "Что вы хотите сделать?",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return EDIT_TRAINING
    
    elif choice == '✅ Точно завершить':
        return await save_comment(update, context)

async def handle_edit_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка редактирования тренировки"""
    choice = update.message.text
    
    if choice == '🔙 Назад к сводке':
        return await finish_training(update, context)
    
    elif choice == '📝 Добавить упражнение':
        # Сохраняем контекст редактирования и переходим к выбору типа упражнения
        context.user_data['editing_mode'] = True
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🔙 Назад к редактированию']
        ]
        await update.message.reply_text(
            "Выберите тип упражнения для добавления:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING
    
    elif choice == '🗑️ Удалить упражнение':
        user_id = update.message.from_user.id
        user_data = get_user_data(user_id)
        
        if not user_data['current_training']['exercises']:
            await update.message.reply_text("❌ В тренировке нет упражнений для удаления.")
            return await finish_training(update, context)
        
        # Создаем клавиатуру с упражнениями для удаления
        keyboard = []
        for i, exercise in enumerate(user_data['current_training']['exercises'], 1):
            emoji = "🏃" if exercise.get('is_cardio') else "💪"
            keyboard.append([f"{emoji} {i}. {exercise['name']}"])
        
        keyboard.append(['🔙 Назад к редактированию'])
        
        await update.message.reply_text(
            "Выберите упражнение для удаления:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        context.user_data['editing'] = True
        return EDIT_EXERCISE

async def handle_exercise_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка удаления упражнения из тренировки"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if update.message.text == '🔙 Назад к редактированию':
        return await finish_training(update, context)
    
    try:
        # Извлекаем номер упражнения из текста
        exercise_text = update.message.text
        exercise_num = int(exercise_text.split('.')[0].split()[-1]) - 1
        
        if 0 <= exercise_num < len(user_data['current_training']['exercises']):
            deleted_exercise = user_data['current_training']['exercises'].pop(exercise_num)
            save_user_data(user_id, user_data)
            
            await update.message.reply_text(
                f"✅ Упражнение '{deleted_exercise['name']}' удалено из тренировки!"
            )
        else:
            await update.message.reply_text("❌ Неверный номер упражнения.")
    
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Не удалось распознать упражнение.")
    
    return await finish_training(update, context)

async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение комментария и завершение тренировки"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    # Если мы в режиме подтверждения, пропускаем ввод комментария
    if update.message.text != '✅ Точно завершить':
        comment = update.message.text
        
        if comment.lower() != 'пропустить':
            user_data['current_training']['comment'] = comment
    
    # Сохраняем тренировку в историю
    user_data['trainings'].append(user_data['current_training'])
    
    # Обновляем статистику
    update_statistics(user_id, user_data['current_training'])
    
    # Формируем финальный отчет о тренировке
    training = user_data['current_training']
    
    report = "🏆 Тренировка завершена 🏆\n\n"
    report += f"📅 Дата: {training['date_start']}\n\n"
    
    if training['measurements'] and training['measurements'] != 'пропустить':
        report += f"📏 Замеры: {training['measurements']}\n\n"
    
    report += "💪 Выполненные упражнения:\n\n"
    
    total_exercises = len(training['exercises'])
    strength_count = 0
    cardio_count = 0
    
    for i, exercise in enumerate(training['exercises'], 1):
        if exercise.get('is_cardio'):
            cardio_count += 1
            report += f"🏃 {i}. {exercise['name']}\n"
            report += f"   Детали: {exercise['details']}\n\n"
        else:
            strength_count += 1
            report += f"💪 {i}. {exercise['name']}\n"
            for j, set_data in enumerate(exercise['sets'], 1):
                report += f"   {j}. {set_data['weight']}кг × {set_data['reps']}\n"
            report += "\n"
    
    report += f"📊 Всего упражнений: {total_exercises}\n"
    report += f"• Силовых: {strength_count}\n"
    report += f"• Кардио: {cardio_count}\n"
    
    if training['comment'] and training['comment'] != 'пропустить':
        report += f"\n💬 Комментарий: {training['comment']}\n"
    
    # Очищаем текущую тренировку
    user_data['current_training'] = None
    
    # Сохраняем финальные данные
    save_user_data(user_id, user_data)
    
    context.user_data.clear()
    
    await update.message.reply_text(
        report,
        reply_markup=ReplyKeyboardMarkup([
            ['💪 Начать тренировку', '📊 История тренировок'],
            ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
            ['📤 Выгрузка данных', '❓ Помощь']
        ], resize_keyboard=True)
    )
    return MAIN_MENU

async def show_measurements_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать историю замеров"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['measurements_history']:
        await update.message.reply_text(
            "📏 У вас пока нет сохраненных замеров.\n"
            "Замеры сохраняются автоматически при начале тренировки.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
        return MAIN_MENU
    
    measurements_text = "📏 История ваших замеров:\n\n"
    
    total_measurements = len(user_data['measurements_history'])
    start_index = max(0, total_measurements - 10)
    
    for i, measurement in enumerate(user_data['measurements_history'][start_index:], start_index + 1):
        measurements_text += f"📅 {measurement['date']}\n"
        measurements_text += f"   {measurement['measurements']}\n\n"
    
    await update.message.reply_text(
        measurements_text,
        reply_markup=ReplyKeyboardMarkup([
            ['💪 Начать тренировку', '📊 История тренировок'],
            ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
            ['📤 Выгрузка данных', '❓ Помощь']
        ], resize_keyboard=True)
    )
    return MAIN_MENU

async def show_statistics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню статистики"""
    keyboard = [
        ['📊 Общая статистика', '📅 Текущая неделя'],
        ['📅 Текущий месяц', '📅 Текущий год'],
        ['📋 Детальная статистика'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        "📈 Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return STATS_PERIOD

async def show_general_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать общую статистику"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    stats = user_data['statistics']
    stats_text = "📊 ВАША СТАТИСТИКА\n\n"
    stats_text += "🏆 ОБЩАЯ СТАТИСТИКА:\n"
    stats_text += f"• Тренировок: {stats['total_trainings']}\n"
    stats_text += f"• Упражнений: {stats['total_exercises']}\n"
    stats_text += f"• Силовых упражнений: {stats['total_strength_exercises']}\n"
    stats_text += f"• Кардио упражнений: {stats['total_cardio_exercises']}\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Детальная статистика'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_PERIOD

async def show_detailed_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать детальную статистику по упражнениям"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    stats = user_data['statistics']
    
    if not stats.get('exercise_stats'):
        await update.message.reply_text(
            "📊 У вас пока нет данных для детальной статистики.",
            reply_markup=ReplyKeyboardMarkup([
                ['📊 Общая статистика', '📅 Текущая неделя'],
                ['📅 Текущий месяц', '📅 Текущий год'],
                ['📋 Детальная статистика'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return STATS_PERIOD
    
    stats_text = "📊 ДЕТАЛЬНАЯ СТАТИСТИКА ПО УПРАЖНЕНИЯМ\n\n"
    
    for exercise_name, exercise_data in stats['exercise_stats'].items():
        stats_text += f"🎯 {exercise_name} ({exercise_data['type']})\n"
        stats_text += f"   Всего выполнено: {exercise_data['total_count']} раз\n"
        
        if exercise_data['type'] == 'strength' and exercise_data['history']:
            # Статистика по весам
            weights = [h.get('max_weight', 0) for h in exercise_data['history'] if h.get('max_weight')]
            if weights:
                stats_text += f"   Макс. вес: {max(weights)}кг\n"
                stats_text += f"   Мин. вес: {min(weights)}кг\n"
                stats_text += f"   Ср. вес: {sum(weights)/len(weights):.1f}кг\n"
        
        elif exercise_data['type'] == 'cardio' and exercise_data['history']:
            # Статистика по кардио
            times = [h.get('time_minutes', 0) for h in exercise_data['history'] if h.get('time_minutes')]
            if times:
                stats_text += f"   Макс. время: {max(times)}мин\n"
                stats_text += f"   Мин. время: {min(times)}мин\n"
                stats_text += f"   Ср. время: {sum(times)/len(times):.1f}мин\n"
        
        stats_text += "\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Детальная статистика'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_PERIOD

async def show_training_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать историю тренировок"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['trainings']:
        await update.message.reply_text("📝 У вас пока нет завершенных тренировок.")
        return MAIN_MENU
    
    history_text = "📊 Последние тренировки:\n\n"
    
    total_trainings = len(user_data['trainings'])
    start_index = max(0, total_trainings - 5)
    
    for i, training in enumerate(user_data['trainings'][start_index:], start_index + 1):
        history_text += f"🏋️ Тренировка #{i}\n"
        history_text += f"📅 {training['date_start']}\n"
        
        strength_count = sum(1 for ex in training['exercises'] if not ex.get('is_cardio'))
        cardio_count = sum(1 for ex in training['exercises'] if ex.get('is_cardio'))
        
        history_text += f"Упражнений: {len(training['exercises'])} (💪{strength_count} 🏃{cardio_count})\n"
        
        if training['comment'] and training['comment'] != 'пропустить':
            history_text += f"💬 {training['comment']}\n"
        
        history_text += "------\n"
    
    await update.message.reply_text(history_text)
    return MAIN_MENU

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Помощь"""
    help_text = """
🤖 **Фитнес-трекер - помощь**

💪 **Силовые упражнения:**
1. Выберите упражнение из списка
2. Добавляйте подходы в формате: "Вес Повторения"
3. Можно ввести несколько подходов сразу (каждый с новой строки)

🏃 **Кардио упражнения:**
1. Выберите кардио из списка
2. Выберите формат: Мин/Метры или Км/Час
3. Введите время и параметры

✏️ **Добавление упражнений:**
- Новые упражнения сохраняются в ваш список

📊 **История тренировок** - просмотр прошлых тренировок
📈 **Статистика** - общая статистика за неделю/месяц/год
📏 **Мои замеры** - история всех ваших замеров
📤 **Выгрузка данных** - скачивание CSV файла с данными
    """
    
    await update.message.reply_text(help_text)
    return MAIN_MENU

async def show_export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню выгрузки данных"""
    keyboard = [
        ['📅 Текущий месяц', '📅 Все время'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        "📤 Выберите период для выгрузки данных:\n\n"
        "Данные будут выгружены в CSV файл, который можно скачать",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return EXPORT_MENU

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выгрузка данных в CSV файл"""
    user_id = update.message.from_user.id
    period_type = update.message.text
    
    if period_type == '📅 Текущий месяц':
        export_type = "current_month"
        period_name = "текущий месяц"
    else:
        export_type = "all_time"
        period_name = "все время"
    
    csv_data = generate_csv_export(user_id, export_type)
    
    if not csv_data:
        await update.message.reply_text(
            f"❌ Нет данных для выгрузки за {period_name}.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
        return MAIN_MENU
    
    # Сохраняем CSV во временный файл
    filename = f"training_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(csv_data)
    
    # Отправляем файл
    with open(filename, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"📊 Выгрузка данных за {period_name}\n\n"
                   "Файл содержит все ваши тренировки в формате CSV",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
    
    # Удаляем временный файл
    os.remove(filename)
    
    return MAIN_MENU

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка главного меню"""
    text = update.message.text
    
    if text == '💪 Начать тренировку':
        return await start_training(update, context)
    elif text == '📊 История тренировок':
        return await show_training_history(update, context)
    elif text == '📝 Мои упражнения':
        return await show_exercises_management(update, context)
    elif text == '📈 Статистика':
        return await show_statistics_menu(update, context)
    elif text == '📏 Мои замеры':
        return await show_measurements_history(update, context)
    elif text == '📤 Выгрузка данных':
        return await show_export_menu(update, context)
    elif text == '❓ Помощь':
        return await help_command(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки меню")
        return MAIN_MENU

def main():
    print("🚀 ЗАПУСК БОТА...")
    
    # 🔧 БЫСТРАЯ ПРОВЕРКА БАЗЫ ДАННЫХ (не блокирующая)
    print("🔍 ТЕСТИРУЕМ ПОДКЛЮЧЕНИЕ К БАЗЕ...")
    
    def check_db_in_thread():
        global DB_AVAILABLE
        DB_AVAILABLE = test_db_connection_quick()
    
    # Запускаем проверку в отдельном потоке с таймаутом
    db_thread = threading.Thread(target=check_db_in_thread)
    db_thread.daemon = True
    db_thread.start()
    db_thread.join(timeout=8)  # Ждем максимум 8 секунд
    
    if DB_AVAILABLE:
        print("🎉 БАЗА ДАННЫХ РАБОТАЕТ!")
        # Инициализируем базу (быстро)
        init_database()
    else:
        print("⚠️ БАЗА ДАННЫХ НЕДОСТУПНА - работаем в режиме памяти")
        print("💡 Данные будут сохраняться только до перезапуска бота")

    # 🔧 ПРОВЕРКА ТОКЕНА
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не установлен!")
        print("💡 Убедитесь, что переменная BOT_TOKEN установлена в Railway")
        return

    print(f"✅ Токен получен, запускаем бота...")
    
    # СОЗДАЕМ И НАСТРАИВАЕМ БОТА
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
            ],
            INPUT_MEASUREMENTS_CHOICE: [
                MessageHandler(filters.Regex('^📝 Ввести замеры$'), handle_measurements_choice),
                MessageHandler(filters.Regex('^⏭️ Отказаться$'), handle_measurements_choice),
                MessageHandler(filters.Regex('^🔙 Главное меню$'), handle_measurements_choice),
            ],
            INPUT_MEASUREMENTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_measurements),
            ],
            TRAINING: [
                MessageHandler(filters.Regex('^💪 Силовые упражнения$'), show_strength_exercises),
                MessageHandler(filters.Regex('^🏃 Кардио$'), handle_cardio),
                MessageHandler(filters.Regex('^✏️ Добавить свое упражнение$'), choose_exercise_type),
                MessageHandler(filters.Regex('^🏁 Завершить тренировку$'), finish_training),
            ],
            CHOOSE_EXERCISE: [
                MessageHandler(filters.Regex('^🔙 Назад к тренировке$'), save_measurements),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_exercise_selection),
            ],
            INPUT_SETS: [
                MessageHandler(filters.Regex('^✅ Добавить еще подходы$'), add_another_set),
                MessageHandler(filters.Regex('^💾 Сохранить упражнение$'), save_exercise),
                MessageHandler(filters.Regex('^❌ Отменить упражнение$'), cancel_exercise),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_input),
            ],
            ADD_CUSTOM_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_exercise),
            ],
            ADD_CUSTOM_CARDIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_custom_cardio),
            ],
            INPUT_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment),
            ],
            STATS_PERIOD: [
                MessageHandler(filters.Regex('^📊 Общая статистика$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущая неделя$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущий месяц$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущий год$'), show_general_statistics),
                MessageHandler(filters.Regex('^📋 Детальная статистика$'), show_detailed_statistics),
                MessageHandler(filters.Regex('^🔙 Главное меню$'), start),
            ],
            EXPORT_MENU: [
                MessageHandler(filters.Regex('^📅 Текущий месяц$'), export_data),
                MessageHandler(filters.Regex('^📅 Все время$'), export_data),
                MessageHandler(filters.Regex('^🔙 Главное меню$'), start),
            ],
            EXERCISES_MANAGEMENT: [
                MessageHandler(filters.Regex('^➕ Добавить упражнение$'), choose_exercise_type),
                MessageHandler(filters.Regex('^🗑️ Удалить упражнение$'), show_delete_exercise_menu),
                MessageHandler(filters.Regex('^🔙 Главное меню$'), start),
            ],
            CHOOSE_EXERCISE_TYPE: [
                MessageHandler(filters.Regex('^💪 Силовое упражнение$'), add_custom_exercise),
                MessageHandler(filters.Regex('^🏃 Кардио упражнение$'), add_custom_exercise),
                MessageHandler(filters.Regex('^🔙 Назад к управлению упражнениями$'), add_custom_exercise),
            ],
            DELETE_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_exercise),
            ],
            CARDIO_TYPE_SELECTION: [
                MessageHandler(filters.Regex('^⏱️ Мин/Метры$'), handle_cardio_type_selection),
                MessageHandler(filters.Regex('^🚀 Км/Час$'), handle_cardio_type_selection),
                MessageHandler(filters.Regex('^🔙 Назад к кардио$'), handle_cardio),
            ],
            INPUT_CARDIO_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cardio_details_input),
            ],
            CONFIRM_FINISH: [
                MessageHandler(filters.Regex('^✅ Точно завершить$'), handle_finish_confirmation),
                MessageHandler(filters.Regex('^✏️ Скорректировать$'), handle_finish_confirmation),
                MessageHandler(filters.Regex('^🔙 Продолжить тренировку$'), handle_finish_confirmation),
            ],
            EDIT_TRAINING: [
                MessageHandler(filters.Regex('^📝 Добавить упражнение$'), handle_edit_training),
                MessageHandler(filters.Regex('^🗑️ Удалить упражнение$'), handle_edit_training),
                MessageHandler(filters.Regex('^🔙 Назад к сводке$'), handle_edit_training),
            ],
            EDIT_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_exercise_deletion),
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    application.add_handler(conv_handler)
    
    # ПРОСТЫЕ КОМАНДЫ ДЛЯ ТЕСТА
    async def test_cmd(update: Update, context):
        status = "с базой данных" if DB_AVAILABLE else "в режиме памяти (база недоступна)"
        await update.message.reply_text(f"🎉 Бот работает! Режим: {status}")

    application.add_handler(CommandHandler("test", test_cmd))
    application.add_handler(CommandHandler("status", test_cmd))

    # ЗАПУСКАЕМ БОТА
    print("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("💡 Используйте /test или /status для проверки")
    
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == '__main__':
    main()
