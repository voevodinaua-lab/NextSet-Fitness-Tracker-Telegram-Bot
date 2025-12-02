import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update

# БАЗОВЫЕ ИМПОРТЫ
from utils_constants import *
from handlers_common import start, start_from_button, handle_main_menu
from handlers_training import (
    start_training, show_training_menu, handle_training_menu_choice,
    handle_training_menu_fallback, show_strength_exercises,
    show_cardio_exercises, choose_exercise_type, finish_training,
    handle_strength_exercise_selection, handle_set_input,
    handle_cardio_exercise_selection, handle_finish_confirmation,
    save_exercise, cancel_exercise
)

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
    print("ЗАПУСК FITNESS TRACKER BOT - МИНИМАЛЬНАЯ ВЕРСИЯ")
    print("=" * 50)
    
    # Проверка токена
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("ОШИБКА: BOT_TOKEN не установлен!")
        return None

    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # СОЗДАЕМ ПРОСТУЮ ВЕРСИЮ handle_input_sets_choice
        async def handle_input_sets_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
            """Обработка выбора при вводе подходов"""
            text = update.message.text
            print(f"DEBUG handle_input_sets_choice: получено '{text}'")
            
            if text == '✅ Добавить еще подходы':
                await update.message.reply_text("Введите следующие подходы...")
                return INPUT_SETS
            elif text == '💾 Сохранить упражнение':
                # Сохраняем упражнение в БД
                return await save_exercise(update, context)
            elif text == '❌ Отменить упражнение':
                # Отменяем упражнение
                return await cancel_exercise(update, context)
            else:
                return await handle_set_input(update, context)
        
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
                    MessageHandler(filters.Regex('^(💪 Силовые упражнения|🏃 Кардио|✏️ Добавить свое упражнение|🏁 Завершить тренировку)$'), handle_training_menu_choice),
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
            await update.message.reply_text("✅ Бот работает! Используйте кнопки меню.")
        
        application.add_handler(CommandHandler("test", test))
        
        print("✅ Приложение настроено успешно!")
        return application
        
    except Exception as e:
        logger.error(f"Ошибка при создании приложения: {e}")
        import traceback
        traceback.print_exc()
        print(f"Критическая ошибка: {e}")
        return None

if __name__ == '__main__':
    app = main()
    if app:
        print("🚀 Бот запущен и готов к работе!")
        print("📱 Отправьте /start в Telegram")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
    else:
        print("❌ Не удалось запустить бота")
