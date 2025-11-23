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
    CARDIO_TYPE_SELECTION, INPUT_CARDIO_DETAILS
) = range(16)

# База упражнений по умолчанию
DEFAULT_STRENGTH_EXERCISES = [
    "Румынская тяга", "Ягодичный мостик", "Болгарский выпад",
    "Скручивания (пресс) в тренажере", "Воздушные выпады с отягощением на степе",
    "Отведения ноги назад в кроссовере", "Отведение ноги в сторону в кроссовере",
    "Скручивания и разгибание колен на полу"
]

DEFAULT_CARDIO_EXERCISES = ["Бег на дорожке"]

# 🔍 ДЕТАЛЬНАЯ ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ К БАЗЕ
def test_db_connection():
    """Тестовое подключение к PostgreSQL - УЛЬТРА-ДИАГНОСТИКА"""
    try:
        database_url = os.getenv('DATABASE_URL')
        print(f"🔍 DATABASE_URL: {database_url}")
        
        if not database_url:
            print("❌ DATABASE_URL не установлен")
            return None
        
        from urllib.parse import urlparse
        url = urlparse(database_url)
        
        print("🔧 Детальные параметры:")
        print(f"   Хост: {url.hostname}")
        print(f"   Порт: {url.port}")
        print(f"   Пользователь: {url.username}")
        print(f"   База: {url.path[1:]}")
        print(f"   Пароль длина: {len(url.password) if url.password else 0} символов")
        
        # Пробуем разные варианты подключения
        print("🔧 Тест 1: Подключение с SSL...")
        try:
            conn = pg8000.connect(
                host=url.hostname,
                port=url.port or 5432,
                user=url.username,
                password=url.password,
                database=url.path[1:],
                ssl_context=True,
                timeout=10
            )
            print("🎉 УСПЕХ с SSL!")
            return conn
        except Exception as e1:
            print(f"💥 Не удалось с SSL: {e1}")
            
            print("🔧 Тест 2: Подключение без SSL...")
            try:
                conn = pg8000.connect(
                    host=url.hostname,
                    port=url.port or 5432,
                    user=url.username,
                    password=url.password,
                    database=url.path[1:],
                    timeout=10
                )
                print("🎉 УСПЕХ без SSL!")
                return conn
            except Exception as e2:
                print(f"💥 Не удалось без SSL: {e2}")
                return None
                
    except Exception as e:
        print(f"💥 Общая ошибка: {e}")
        return None

# 📋 ОСНОВНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ
def get_db_connection():
    """Получить соединение с PostgreSQL"""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("❌ DATABASE_URL не установлен")
            return None
        
        # Парсим DATABASE_URL
        from urllib.parse import urlparse
        url = urlparse(database_url)
        
        # Пробуем подключиться с SSL (требуется для Supabase)
        conn = pg8000.connect(
            host=url.hostname,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            database=url.path[1:],  # Убираем первый слэш
            ssl_context=True,
            timeout=10
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
        
        # Пробуем без SSL как запасной вариант
        try:
            conn = pg8000.connect(
                host=url.hostname,
                port=url.port or 5432,
                user=url.username,
                password=url.password,
                database=url.path[1:],
                timeout=10
            )
            logger.info("✅ Подключение без SSL успешно")
            return conn
        except Exception as e2:
            logger.error(f"❌ Ошибка подключения без SSL: {e2}")
            return None

def init_database():
    """Инициализация базы данных"""
    conn = get_db_connection()
    if not conn:
        print("❌ Не удалось подключиться к базе для инициализации")
        return False
    
    try:
        with conn.cursor() as cur:
            # Таблица пользователей
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

def save_user_data(user_id, user_data):
    """Сохранить данные пользователя в PostgreSQL"""
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Нет подключения к БД для сохранения")
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
        logger.error(f"❌ Ошибка сохранения данных пользователя {user_id}: {e}")
        return False

def load_user_data(user_id):
    """Загрузить данные пользователя из PostgreSQL"""
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Нет подключения к БД для загрузки")
        return get_default_user_data()
    
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT user_data FROM users WHERE user_id = %s', (user_id,))
            result = cur.fetchone()
        
        conn.close()
        
        if result and result[0]:
            return json.loads(result[0])
        else:
            return get_default_user_data()
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных пользователя {user_id}: {e}")
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
            'yearly_stats': {}
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

# ... остальные функции остаются без изменений ...

def main():
    print("🔍 ТЕСТИРУЕМ ПОДКЛЮЧЕНИЕ К БАЗЕ...")
    test_conn = test_db_connection()  # Используем диагностическую функцию
    if test_conn:
        print("🎉 БАЗА ДАННЫХ РАБОТАЕТ!")
        test_conn.close()
    else:
        print("💥 НЕ УДАЛОСЬ ПОДКЛЮЧИТЬСЯ К БАЗЕ")
        # Не прерываем выполнение - бот может работать в режиме только памяти
        print("⚠️ Бот будет работать в режиме памяти (данные не сохранятся после перезапуска)")

    print("✅ ШАГ 1: Продолжаем запуск бота...")
    
    print("✅ ШАГ 2: Инициализируем базу данных...")
    if init_database():
        print("✅ ШАГ 3: База данных инициализирована")
    else:
        print("⚠️ ШАГ 3: База данных не инициализирована, но бот запустится")

    print("✅ ШАГ 4: Проверяем токен...")
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("❌ Ошибка: BOT_TOKEN не установлен")
        return

    print(f"✅ ШАГ 5: Токен получен, запускаем бота...")
    
    print("✅ ШАГ 6: Создаем application...")
    application = Application.builder().token(TOKEN).build()
    
    print("✅ ШАГ 7: Добавляем обработчики...")
    
    # Настройка ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            # ... состояния остаются без изменений ...
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
                MessageHandler(filters.Regex('^✅ Добавить еще подходы$'), add_another_set),
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
    
    # ПРОСТЫЕ КОМАНДЫ ДЛЯ ТЕСТА
    async def test_start(update: Update, context):
        await update.message.reply_text("🎉 Тест! Бот работает!")

    async def test_help(update: Update, context):
        await update.message.reply_text("ℹ️ Тестовая помощь")

    # ДОБАВЛЯЕМ ПРОСТЫЕ ОБРАБОТЧИКИ
    application.add_handler(CommandHandler("test", test_start))
    application.add_handler(CommandHandler("help", test_help))

    print("✅ Добавлены тестовые команды: /test, /help")

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
