import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
from telegram import Update

# Импорты состояний и обработчиков
from utils_constants import *
from handlers_common import *
from handlers_training import *
from handlers_exercises import *
from handlers_statistics import *
from handlers_measurements import show_measurements_history
from handlers_export import *

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

def main():
    """Основная функция запуска"""
    print("=" * 50)
    print("ЗАПУСК FITNESS TRACKER BOT")
    print("=" * 50)
    
    # Проверка токена
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("ОШИБКА: BOT_TOKEN не установлен!")
        return None

    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # Создаем УПРОЩЕННЫЙ ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', start),
                MessageHandler(filters.Regex('^(🚀 Начать|🚀 Продолжить|🏃‍♂️ Продолжить тренировку|🆕 Начать новую тренировку)$'), start_from_button),
            ],
            states={
                MAIN_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
                ],
                
                # Модуль тренировки - ОСНОВНОЙ FLOW
                TRAINING_MENU: [
                    MessageHandler(filters.Regex('^(💪 Силовые упражнения)$'), handle_training_menu_choice),
                    MessageHandler(filters.Regex('^(🏃 Кардио)$'), handle_training_menu_choice),
                    MessageHandler(filters.Regex('^(✏️ Добавить свое упражнение)$'), handle_training_menu_choice),
                    MessageHandler(filters.Regex('^(🏁 Завершить тренировку)$'), handle_training_menu_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_training_menu_fallback),
                ],
                
                CHOOSE_STRENGTH_EXERCISE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_strength_exercise_selection),
                ],
                
                INPUT_SETS: [
                    MessageHandler(filters.Regex('^(✅ Добавить еще подходы|💾 Сохранить упражнение|❌ Отменить упражнение)$'), handle_input_sets_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_input),
                ],
                
                CHOOSE_CARDIO_EXERCISE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cardio_exercise_selection),
                ],
                
                # ОСТАЛЬНЫЕ СОСТОЯНИЯ ПОКА УПРОЩАЕМ
                CONFIRM_FINISH: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_finish_confirmation),
                ],
            },
            fallbacks=[
                CommandHandler('start', start),
                MessageHandler(filters.Regex('^🚀 Начать$'), start_from_button),
            ],
            allow_reentry=True
        )
        
        application.add_handler(conv_handler)
        
        # Простые команды
        async def test(update, context):
            await update.message.reply_text("Бот работает!")
        
        application.add_handler(CommandHandler("test", test))
        
        print("Приложение настроено успешно!")
        return application
        
    except Exception as e:
        logger.error(f"Ошибка при создании приложения: {e}")
        print(f"Критическая ошибка: {e}")
        return None

if __name__ == '__main__':
    app = main()
    if app:
        print("Бот запущен и готов к работе!")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
    else:
        print("Не удалось запустить бота")
