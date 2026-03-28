import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update

# БАЗОВЫЕ ИМПОРТЫ
from utils_constants import *
from database import ensure_bot_schema
from handlers_common import (
    start,
    start_from_button,
    handle_main_menu,
    handle_clear_data_choice,
    handle_clear_data_confirmation,
)
from handlers_statistics import handle_statistics_menu
from handlers_export import handle_export_menu
from handlers_training import (
    start_training, 
    handle_training_menu_choice,
    handle_training_menu_fallback, 
    show_strength_exercises,
    show_cardio_exercises, 
    choose_exercise_type,
    handle_strength_exercise_selection, 
    handle_set_input,
    handle_cardio_exercise_selection, 
    show_finish_summary,           # ← ДОБАВИТЬ эту функцию
    handle_finish_confirmation,
    save_exercise, 
    cancel_exercise, 
    save_new_exercise_from_training, 
    handle_cardio_type_selection,
    handle_cardio_min_meters_input,
    handle_cardio_km_h_input,
    handle_measurements_choice,
    save_measurements,
    add_custom_exercise_from_training,
)
from handlers_exercises import (
    show_exercises_management,
    handle_exercises_management_choice,
    choose_exercise_type_mgmt,
    add_custom_exercise_mgmt,
    save_new_strength_exercise_mgmt,
    save_new_cardio_exercise_mgmt,
    show_delete_exercise_menu,
    delete_exercise_handler
)
# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def _log_errors(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует необработанные исключения в хендлерах (важно для Render и отладки кнопок)."""
    logger.error("Ошибка в обработчике Telegram:", exc_info=context.error)


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

    ensure_bot_schema()

    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # СОЗДАЕМ ПРОСТУЮ ВЕРСИЮ handle_input_sets_choice
        async def handle_input_sets_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
            """Обработка выбора при вводе подходов"""
            text = update.message.text
            
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
                INACTIVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_clear_data_choice),
                ],
                MAIN_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
                ],
                STATS_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_statistics_menu),
                ],
                EXPORT_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_export_menu),
                ],
                CLEAR_DATA_CONFIRM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_clear_data_confirmation),
                ],
                
                # Модуль тренировки - ОСНОВНОЙ FLOW
                TRAINING_MENU: [
                    MessageHandler(filters.Regex('^(💪 Силовые упражнения|🏃 Кардио|✏️ Добавить свое упражнение|🏁 Завершить тренировку)$'), handle_training_menu_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_training_menu_fallback),
                ],

                ADD_EXERCISE_TYPE: [
                    MessageHandler(filters.Regex('^(💪 Силовое упражнение|🏃 Кардио упражнение|🔙 Назад к тренировке)$'), add_custom_exercise_from_training),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_custom_exercise_from_training),
                ],
                
                INPUT_MEASUREMENTS_CHOICE: [
                    MessageHandler(filters.Regex('^(📝 Ввести замеры|⏭️ Пропустить замеры|🔙 Главное меню)$'), handle_measurements_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_measurements_choice),
                ],

                INPUT_MEASUREMENTS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_measurements),  
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
                
                INPUT_NEW_CARDIO_EXERCISE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_exercise_from_training),
                ],
                
                INPUT_NEW_STRENGTH_EXERCISE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_exercise_from_training),
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

                DELETE_EXERCISE_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, delete_exercise_handler),
                ],

                EXERCISES_MANAGEMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_exercises_management_choice),
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
                
                CONFIRM_FINISH: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_finish_confirmation),
                ],
            },
            fallbacks=[
                CommandHandler('start', start),
                MessageHandler(
                    filters.Regex('^(🚀 Начать|🚀 Продолжить)$'),
                    start_from_button,
                ),
            ],
            allow_reentry=True
        )
        
        application.add_handler(conv_handler)
        application.add_error_handler(_log_errors)
        
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











