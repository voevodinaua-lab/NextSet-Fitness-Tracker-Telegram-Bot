import os
import logging
import sys
import threading
from dotenv import load_dotenv

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler

# Импортируем наши модули
from database import get_db_connection
from utils_constants import *
from handlers_common import *
from handlers_training import *
from handlers_exercises import *
from handlers_statistics import *
from handlers_measurements import *
from handlers_export import *

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

def test_db_connection_quick():
    """Быстрая проверка подключения к базе"""
    try:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
            conn.close()
            print("🎉 База данных доступна!")
            return True
        else:
            print("❌ База данных недоступна")
            return False
    except Exception as e:
        print(f"⚠️ База данных недоступна: {e}")
        return False

def main():
    print("🚀 ЗАПУСК БОТА...")
    
    # Проверка подключения к базе данных
    print("🔍 ПРОВЕРКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ...")
    
    def check_db_in_thread():
        db_available = test_db_connection_quick()
        if not db_available:
            print("⚠️ РАБОТАЕМ БЕЗ БАЗЫ ДАННЫХ - некоторые функции могут быть недоступны")
    
    db_thread = threading.Thread(target=check_db_in_thread)
    db_thread.daemon = True
    db_thread.start()
    db_thread.join(timeout=5)

    # Проверка токена
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не установлен!")
        print("💡 Убедитесь, что переменная BOT_TOKEN установлена в Render")
        return

    print("✅ Токен получен, запускаем бота...")
    
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # Создаем ConversationHandler
    conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('start', start),
        MessageHandler(filters.Regex('^(🚀 Начать|🚀 Продолжить)$'), start_from_button),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_message)
    ],
    states={
        INACTIVE: [
            MessageHandler(filters.Regex('^(🚀 Начать|🚀 Продолжить|🗑️ Начать с чистого листа)$'), handle_clear_data_choice),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_message),
        ],
        MAIN_MENU: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
        ],
        CLEAR_DATA_CONFIRM: [
            MessageHandler(filters.Regex('^(✅ Да, удалить все данные|❌ Отмена)$'), handle_clear_data_confirmation),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_clear_data_confirmation),
        ],
        
        # 🏋️ Модуль тренировки
        INPUT_MEASUREMENTS_CHOICE: [
            MessageHandler(filters.Regex('^(📝 Ввести замеры|⏭️ Пропустить замеры|🔙 Главное меню)$'), handle_measurements_choice),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_measurements_choice),
        ],
        INPUT_MEASUREMENTS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_measurements),
        ],
        TRAINING_MENU: [
            MessageHandler(filters.Regex('^(💪 Силовые упражнения|🏃 Кардио|✏️ Добавить свое упражнение|🏁 Завершить тренировку)$'), 
                          lambda u, c: (show_strength_exercises(u, c) if u.message.text == '💪 Силовые упражнения' else
                                       show_cardio_exercises(u, c) if u.message.text == '🏃 Кардио' else
                                       choose_exercise_type(u, c) if u.message.text == '✏️ Добавить свое упражнение' else
                                       finish_training(u, c))),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
        ],
        # ... остальные состояния остаются без изменений
    },
    fallbacks=[
        CommandHandler('start', start),
        MessageHandler(filters.Regex('^(🚀 Начать|🚀 Продолжить)$'), start_from_button),
    ],
    allow_reentry=True
)
        
        application.add_handler(conv_handler)

        # Простые команды для теста
        async def test_cmd(update, context):
            await update.message.reply_text("🎉 Бот работает! Используйте кнопки меню для навигации.")

        async def status_cmd(update, context):
            conn = get_db_connection()
            if conn:
                status = "✅ База данных доступна"
                conn.close()
            else:
                status = "⚠️ База данных недоступна"
            
            await update.message.reply_text(f"🤖 Статус бота:\n{status}")

        application.add_handler(CommandHandler("test", test_cmd))
        application.add_handler(CommandHandler("status", status_cmd))

        # Запускаем бота
        print("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
        print("💡 Используйте /test или /status для проверки")
        
        return application
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании приложения: {e}")
        print(f"❌ Критическая ошибка: {e}")
        return None

if __name__ == '__main__':
    app = main()
    if app:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )


