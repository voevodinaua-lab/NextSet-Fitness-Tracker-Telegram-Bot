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
        print("💡 Убедитесь, что переменная BOT_TOKEN установлена в Railway")
        return

    print("✅ Токен получен, запускаем бота...")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Создаем ConversationHandler с новой архитектурой
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
            CHOOSE_STRENGTH_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_strength_exercise_selection),
            ],
            INPUT_SETS: [
                MessageHandler(filters.Regex('^(✅ Добавить еще подходы|💾 Сохранить упражнение|❌ Отменить упражнение)$'), 
                              lambda u, c: (add_another_set(u, c) if u.message.text == '✅ Добавить еще подходы' else
                                           save_exercise(u, c) if u.message.text == '💾 Сохранить упражнение' else
                                           cancel_exercise(u, c))),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_input),
            ],
            CHOOSE_CARDIO_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cardio_exercise_selection),
            ],
            CARDIO_TYPE_SELECTION: [
                MessageHandler(filters.Regex('^(⏱️ Мин/Метры|🚀 Км/Час|🔙 Назад к кардио)$'), handle_cardio_type_selection),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cardio_type_selection),
            ],
            INPUT_CARDIO_MIN_METERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cardio_min_meters_input),
            ],
            INPUT_CARDIO_KM_H: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cardio_km_h_input),
            ],
            ADD_EXERCISE_TYPE: [
                MessageHandler(filters.Regex('^(💪 Силовое упражнение|🏃 Кардио упражнение|🔙 Назад к тренировке)$'), add_custom_exercise_from_training),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_custom_exercise_from_training),
            ],
            INPUT_NEW_STRENGTH_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_exercise_from_training),
            ],
            INPUT_NEW_CARDIO_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_exercise_from_training),
            ],
            CONFIRM_FINISH: [
                MessageHandler(filters.Regex('^(✅ Точно завершить|✏️ Скорректировать|🔙 Продолжить тренировку)$'), handle_finish_confirmation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_finish_confirmation),
            ],
            
            # 📝 Модуль управления упражнениями
            EXERCISES_MANAGEMENT: [
                MessageHandler(filters.Regex('^(➕ Добавить упражнение|🗑️ Удалить упражнение|🔙 Главное меню)$'), 
                              lambda u, c: (choose_exercise_type_mgmt(u, c) if u.message.text == '➕ Добавить упражнение' else
                                           show_delete_exercise_menu(u, c) if u.message.text == '🗑️ Удалить упражнение' else
                                           start(u, c))),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
            ],
            ADD_EXERCISE_TYPE_MGMT: [
                MessageHandler(filters.Regex('^(💪 Силовое упражнение|🏃 Кардио упражнение|🔙 Назад к управлению упражнениями)$'), add_custom_exercise_mgmt),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_custom_exercise_mgmt),
            ],
            INPUT_NEW_STRENGTH_EXERCISE_MGMT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_strength_exercise_mgmt),
            ],
            INPUT_NEW_CARDIO_EXERCISE_MGMT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_cardio_exercise_mgmt),
            ],
            DELETE_EXERCISE_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_exercise_handler),
            ],
            
            # 📊 Модуль статистики
            STATS_MENU: [
                MessageHandler(filters.Regex('^(📊 Общая статистика|📅 Текущая неделя|📅 Текущий месяц|📅 Текущий год|📋 Статистика по упражнениям|🔙 Главное меню)$'), 
                              lambda u, c: (show_general_statistics(u, c) if u.message.text == '📊 Общая статистика' else
                                           show_weekly_stats(u, c) if u.message.text == '📅 Текущая неделя' else
                                           show_monthly_stats(u, c) if u.message.text == '📅 Текущий месяц' else
                                           show_yearly_stats(u, c) if u.message.text == '📅 Текущий год' else
                                           show_exercise_stats(u, c) if u.message.text == '📋 Статистика по упражнениям' else
                                           start(u, c))),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
            ],
            
            # 📏 Модуль замеров
            MEASUREMENTS_HISTORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, show_measurements_history),
            ],
            
            # 📤 Модуль экспорта
            EXPORT_MENU: [
                MessageHandler(filters.Regex('^(📅 Текущий месяц|📅 Все время|🔙 Главное меню)$'), 
                              lambda u, c: (export_data(u, c) if u.message.text in ['📅 Текущий месяц', '📅 Все время'] else
                                           start(u, c))),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
            ],
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
    
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == '__main__':
    main()