import os
import logging
import sys
import socket
import psycopg2
from psycopg2.extras import Json
import json
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
    CARDIO_TYPE_SELECTION, INPUT_CARDIO_DETAILS
) = range(16)

# Блокировка порта для гарантии одного процесса
try:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lock_socket.bind(('0.0.0.0', 17979))
    print("🔒 Запускаем единственный экземпляр бота")
except socket.error:
    print("❌ Уже запущен другой экземпляр! Завершаем...")
    sys.exit(1)

import threading
import requests
import time

def keep_railway_awake():
    """Фоновая задача для поддержания активности Railway"""
    def ping():
        while True:
            try:
                domain = os.getenv('RAILWAY_STATIC_URL') or os.getenv('RAILWAY_PUBLIC_DOMAIN')
                if domain:
                    # Добавляем таймаут чтобы не блокировать бота
                    requests.get(f"https://{domain}", timeout=5)
                    print(f"✅ Пинг отправлен")
            except:
                # Игнорируем ошибки пинга
                pass
            time.sleep(300)  # Каждые 5 минут
    
    thread = threading.Thread(target=ping, daemon=True)
    thread.start()

# Запускаем при импорте
keep_railway_awake()

import csv
import io
from datetime import datetime, timedelta

# База упражнений по умолчанию
DEFAULT_STRENGTH_EXERCISES = [
    "Румынская тяга",
    "Ягодичный мостик", 
    "Болгарский выпад",
    "Скручивания (пресс) в тренажере",
    "Воздушные выпады с отягощением на степе",
    "Отведения ноги назад в кроссовере",
    "Отведение ноги в сторону в кроссовере",
    "Скручивания и разгибание колен на полу"
]

DEFAULT_CARDIO_EXERCISES = [
    "Бег на дорожке"
]

# PostgreSQL подключение
def get_db_connection():
    """Получить соединение с PostgreSQL"""
    try:
        # Railway автоматически предоставляет DATABASE_URL
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            # Для локальной разработки
            database_url = "postgresql://postgres:postgres@localhost:5432/fitness_bot"
        
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
        return None

def init_database():
    """Инициализация базы данных"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Таблица пользователей
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                user_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индекс для быстрого поиска
        cur.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)')
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ База данных инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return False

def save_user_data(user_id, user_data):
    """Сохранить данные пользователя в PostgreSQL"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO users (user_id, user_data, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) 
            DO UPDATE SET user_data = %s, updated_at = CURRENT_TIMESTAMP
        ''', (user_id, Json(user_data), Json(user_data)))
        
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных пользователя {user_id}: {e}")
        return False

def load_user_data(user_id):
    """Загрузить данные пользователя из PostgreSQL"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        cur.execute('SELECT user_data FROM users WHERE user_id = %s', (user_id,))
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result:
            return result[0]
        else:
            # Создаем начальные данные для нового пользователя
            initial_data = {
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
                    'yearly_stats': {}
                }
            }
            return initial_data
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных пользователя {user_id}: {e}")
        return None

def get_user_data(user_id):
    """Получить данные пользователя (совместимость со старым кодом)"""
    return load_user_data(user_id)

def get_user_exercises(user_id):
    """Получить все упражнения пользователя"""
    user_data = get_user_data(user_id)
    if not user_data:
        user_data = load_user_data(user_id)
    
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
    
    # Сохраняем обновленные данные
    save_user_data(user_id, user_data)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало работы с ботом"""
    user = update.message.from_user
    
    # Инициализируем данные пользователя при первом старте
    user_data = load_user_data(user.id)
    if not user_data:
        # Создаем начальные данные
        initial_data = {
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
                'yearly_stats': {}
            }
        }
        save_user_data(user.id, initial_data)
    
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
    user_data = get_user_data(user_id)
    
    # Создаем новую тренировку
    current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    user_data['current_training'] = {
        'date_start': current_date,
        'exercises': [],
        'comment': '',
        'measurements': ''
    }
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    await update.message.reply_text(
        f"🎯 Отлично стартуем! Сегодня {current_date}\n\n"
        "📏 Перед началом тренировки введите ваши замеры:\n"
        "(например: вес 65кг, талия 70см, бедра 95см)\n"
        "Или напишите 'пропустить' чтобы продолжить без замеров",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_MEASUREMENTS

async def save_measurements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение замеров и переход к тренировке"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    measurements = update.message.text
    
    if measurements.lower() != 'пропустить':
        user_data['current_training']['measurements'] = measurements
        # Сохраняем замеры в историю
        user_data['measurements_history'].append({
            'date': datetime.now().strftime("%d.%m.%Y %H:%M"),
            'measurements': measurements
        })
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        "✅ Замеры сохранены! Выберите тип упражнения:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return TRAINING

# ... (все остальные функции остаются аналогичными, но с добавлением save_user_data после изменений)

async def save_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение упражнения с подходами"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if 'current_exercise' not in context.user_data or not context.user_data['current_exercise']['sets']:
        await update.message.reply_text("❌ Нет данных для сохранения.")
        return await show_strength_exercises(update, context)
    
    # Сохраняем упражнение
    exercise_data = context.user_data['current_exercise'].copy()
    exercise_data['timestamp'] = update.message.date.strftime("%H:%M")
    
    user_data['current_training']['exercises'].append(exercise_data)
    
    # Сохраняем данные
    save_user_data(user_id, user_data)
    
    # Формируем текст сохраненного упражнения
    exercise_text = f"💪 {exercise_data['name']}:\n"
    for i, set_data in enumerate(exercise_data['sets'], 1):
        exercise_text += f"{i}. {set_data['weight']}кг × {set_data['reps']} повторений\n"
    
    # Очищаем временные данные
    context.user_data.pop('current_exercise', None)
    
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
        exercise_data['timestamp'] = update.message.date.strftime("%H:%M")
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

async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение комментария и завершение тренировки"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    comment = update.message.text
    
    if comment.lower() != 'пропустить':
        user_data['current_training']['comment'] = comment
    
    # Сохраняем тренировку в историю
    user_data['trainings'].append(user_data['current_training'])
    
    # Обновляем статистику
    update_statistics(user_id, user_data['current_training'])
    
    # Формируем отчет о тренировке
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
            report += f"   Детали: {exercise['details']}\n"
            report += f"   Время: {exercise['timestamp']}\n\n"
        else:
            strength_count += 1
            report += f"💪 {i}. {exercise['name']}\n"
            for j, set_data in enumerate(exercise['sets'], 1):
                report += f"   {j}. {set_data['weight']}кг × {set_data['reps']}\n"
            report += f"   Время: {exercise['timestamp']}\n\n"
    
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

# ... (остальные функции остаются аналогичными с добавлением save_user_data где нужно)

def main():
    """Запуск бота"""
    # Инициализируем базу данных
    if not init_database():
        print("❌ Не удалось инициализировать базу данных")
        return
    
    TOKEN = os.getenv('BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Ошибка: BOT_TOKEN не установлен")
        return
    
    print(f"✅ Токен получен, запускаем бота...")
    
    application = Application.builder().token(TOKEN).build()
    
    # Настройка ConversationHandler (остается без изменений)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
            ],
            INPUT_MEASUREMENTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_measurements),
            ],
            TRAINING: [
                MessageHandler(filters.Regex('^💪 Силовые упражнения$'), show_strength_exercises),
                MessageHandler(filters.Regex('^🏃 Кардио$'), handle_cardio),
                MessageHandler(filters.Regex('^✏️ Добавить свое упражнение$'), add_custom_exercise),
                MessageHandler(filters.Regex('^🏁 Завершить тренировку$'), finish_training),
            ],
            CHOOSE_EXERCISE: [
                MessageHandler(filters.Regex('^🔙 Назад к тренировке$'), save_measurements),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_exercise_selection),
            ],
            INPUT_SETS: [
                MessageHandler(filters.Regex('^✅ Добавить еще подход$'), add_another_set),
                MessageHandler(filters.Regex('^💾 Сохранить упражнение$'), save_exercise),
                MessageHandler(filters.Regex('^❌ Отменить упражнение$'), cancel_exercise),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_input),
            ],
            ADD_CUSTOM_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_exercise),
            ],
            ADD_CUSTOM_CARDIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_cardio),
            ],
            INPUT_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment),
            ],
            STATS_PERIOD: [
                MessageHandler(filters.Regex('^📊 Общая статистика$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущая неделя$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущий месяц$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущий год$'), show_general_statistics),
                MessageHandler(filters.Regex('^📋 Детальная статистика$'), show_general_statistics),
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_custom_exercise),
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
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    application.add_handler(conv_handler)
    
    # Обработчик ошибок
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        error_msg = str(context.error)
        logger.error(f"Ошибка: {error_msg}")
        if "Conflict" in error_msg:
            print("💀 Конфликт обнаружен - экстренное завершение!")
            sys.exit(1)
    
    application.add_error_handler(error_handler)
    
    print("🚀 Бот запускается...")
    
    # Запускаем polling
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == '__main__':
    main()