import os
import logging
import sys
import signal
import threading
from dotenv import load_dotenv

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
from telegram import Update

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

class BotManager:
    def __init__(self):
        self.application = None
        self.shutdown_requested = False
        
    def signal_handler(self, signum, frame):
        """Обработчик сигналов для graceful shutdown"""
        print(f"Получен сигнал {signum}, останавливаем бота...")
        self.shutdown_requested = True
        if self.application:
            print("Завершаем работу бота...")
            # Используем асинхронную остановку
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._shutdown())
                else:
                    asyncio.run(self._shutdown())
            except:
                # Если возникли проблемы с event loop, просто выходим
                sys.exit(0)
    
    async def _shutdown(self):
        """Асинхронное завершение работы"""
        await self.application.stop()
        await self.application.shutdown()

def test_db_connection_quick():
    """Быстрая проверка подключения к базе с подробным логированием"""
    try:
        print("Пытаемся подключиться к базе данных...")
        conn = get_db_connection()
        if conn:
            print("Соединение с БД установлено, выполняем тестовый запрос...")
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
                result = cur.fetchone()
                print(f"Тестовый запрос выполнен успешно: {result}")
            conn.close()
            print("База данных полностью доступна!")
            return True
        else:
            print("Не удалось получить соединение с БД")
            return False
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return False

def setup_application():
    """Настройка и создание приложения"""
    print("НАСТРОЙКА ПРИЛОЖЕНИЯ БОТА...")
    
    # Проверка токена
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("ОШИБКА: BOT_TOKEN не установлен!")
        print("Убедитесь, что переменная BOT_TOKEN установлена в Render")
        return None

    print("Токен получен, создаем приложение...")
    
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
             
        # ДЕБАГ обработчик для логирования всех сообщений
        async def debug_message_handler(update, context):
            print(f"🔍 DEBUG: Получено сообщение: '{update.message.text}' от пользователя {update.effective_user.id}")
            # Пропускаем сообщение дальше к ConversationHandler
            return None

        # Добавляем дебаг handler ПЕРВЫМ (group=1)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, debug_message_handler), group=1)

        # Создаем ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_message)
            ],
            states={
                INACTIVE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_clear_data_choice),
                ],
                MAIN_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
                ],
                TRAINING_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_training_menu_simple),
                ],
                CLEAR_DATA_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_clear_data_confirmation),
                ],
            },
            fallbacks=[
                CommandHandler('start', start),
            ],
            allow_reentry=True
        )
        
        application.add_handler(conv_handler)

        # Простые команды для теста
        async def test_cmd(update, context):
            await update.message.reply_text("Бот работает! Используйте кнопки меню для навигации.")

        async def status_cmd(update, context):
            conn = get_db_connection()
            if conn:
                status = "База данных доступна"
                conn.close()
            else:
                status = "База данных недоступна"
            
            await update.message.reply_text(f"Статус бота:\n{status}")

        application.add_handler(CommandHandler("test", test_cmd))
        application.add_handler(CommandHandler("status", status_cmd))

        print("Приложение настроено успешно!")
        return application
        
    except Exception as e:
        logger.error(f"Ошибка при создании приложения: {e}")
        print(f"Критическая ошибка: {e}")
        return None

def main():
    """Основная функция запуска"""
    print("=" * 50)
    print("ЗАПУСК FITNESS TRACKER BOT")
    print("=" * 50)
    
    print("ПРЯМАЯ ПРОВЕРКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ...")
    db_available = test_db_connection_quick()
    if not db_available:
        print("ВНИМАНИЕ: РАБОТАЕМ БЕЗ БАЗЫ ДАННЫХ - некоторые функции могут быть недоступны")
    else:
        print("Все функции бота доступны")
    
    
    # Создаем менеджер бота
    bot_manager = BotManager()
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGTERM, bot_manager.signal_handler)
    signal.signal(signal.SIGINT, bot_manager.signal_handler)
    
    # ПРЯМАЯ проверка БД (без потока)
    print("ПРЯМАЯ ПРОВЕРКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ...")
    db_available = test_db_connection_quick()
    if not db_available:
        print("ВНИМАНИЕ: РАБОТАЕМ БЕЗ БАЗЫ ДАННЫХ - некоторые функции могут быть недоступны")
    else:
        print("Все функции бота доступны")

    # Настраиваем приложение
    application = setup_application()
    if not application:
        print("Не удалось создать приложение")
        return None
        
    bot_manager.application = application
    return application

if __name__ == '__main__':
    app = main()
    if app:
        try:
            print("ЗАПУСКАЕМ БОТА...")
            print("Используйте /test или /status для проверки")
            print("Бот готов к работе!")
            
            # Запускаем polling с улучшенными настройками
            app.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                close_loop=False
            )
            
        except Exception as e:
            print(f"Ошибка при запуске бота: {e}")
            print("Попытка перезапуска через 30 секунд...")
            import time
            time.sleep(30)
            # Попытка перезапуска
            os.execv(sys.executable, ['python'] + sys.argv)
    else:
        print("Не удалось запустить бота")
        sys.exit(1)






