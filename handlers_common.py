import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from database import create_user, get_custom_exercises, get_user_trainings
from utils_constants import *

logger = logging.getLogger(__name__)

async def handle_unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений, когда бот не в активном состоянии"""
    if context.user_data.get('in_conversation'):
        return
    
    user = update.message.from_user
    user_id = user.id
    
    # Создаем пользователя в БД если его нет
    create_user(user_id, user.username, user.first_name)
    
    # Проверяем историю пользователя
    trainings = get_user_trainings(user_id, limit=1)
    custom_exercises = get_custom_exercises(user_id)
    
    has_history = (len(trainings) > 0 or 
                  len(custom_exercises['strength']) > 0 or 
                  len(custom_exercises['cardio']) > 0)
    
    if has_history:
        welcome_text = f"""
👋 С возвращением, {user.first_name}! 

Ваша история тренировок и все данные сохранены в базе данных.
Выберите действие:
        """
        
        keyboard = [
            ['🚀 Продолжить'],
            ['🗑️ Начать с чистого листа']
        ]
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
    else:
        welcome_text = f"""
👋 Привет, {user.first_name}! 

Я твой фитнес-трекер! Помогу тебе отслеживать тренировки, замеры и прогресс.

Нажми кнопку «🚀 Начать», чтобы начать работу!
        """
        
        keyboard = [['🚀 Начать']]
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
    
    return INACTIVE

async def start_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка нажатия кнопки старта"""
    context.user_data['in_conversation'] = True
    return await start(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало работы с ботом"""
    user = update.message.from_user
    user_id = user.id
    
    # Создаем/обновляем пользователя в БД
    create_user(user_id, user.username, user.first_name)
    
    # Устанавливаем флаг активной конверсации
    context.user_data['in_conversation'] = True
    
    # Проверяем историю пользователя
    trainings = get_user_trainings(user_id, limit=1)
    custom_exercises = get_custom_exercises(user_id)
    
    has_history = (len(trainings) > 0 or 
                  len(custom_exercises['strength']) > 0 or 
                  len(custom_exercises['cardio']) > 0)
    
    if has_history:
        welcome_text = f"""
🎉 Добро пожаловать назад, {user.first_name}! 

Продолжаем работу! 🏋️
        """
    else:
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

async def handle_clear_data_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора очистки данных"""
    choice = update.message.text
    user_id = update.message.from_user.id
    
    if choice == '🚀 Продолжить':
        return await start(update, context)
    
    elif choice == '🗑️ Начать с чистого листа':
        warning_text = """
⚠️ ВНИМАНИЕ: Вы собираетесь удалить все ваши данные!

Это действие:
• Удалит все тренировки и замеры
• Сбросит статистику
• Сохранит только ваши упражнения
• Нельзя будет отменить

Подтвердите действие:
        """
        
        keyboard = [
            ['✅ Да, удалить все данные'],
            ['❌ Отмена']
        ]
        
        await update.message.reply_text(
            warning_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CLEAR_DATA_CONFIRM
    
    else:
        # Обработка текстового ввода вместо кнопок
        trainings = get_user_trainings(user_id, limit=1)
        has_history = len(trainings) > 0
        
        if has_history:
            keyboard = [
                ['🚀 Продолжить'],
                ['🗑️ Начать с чистого листа']
            ]
        else:
            keyboard = [['🚀 Начать']]
            
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для выбора действия",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return INACTIVE

async def handle_clear_data_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения очистки данных"""
    choice = update.message.text
    user_id = update.message.from_user.id
    
    if choice == '❌ Отмена':
        return await start(update, context)
    
    elif choice == '✅ Да, удалить все данные':
        # TODO: Реализовать очистку данных в БД
        # Пока просто возвращаем в главное меню
        await update.message.reply_text(
            "✅ Функция очистки данных будет реализована в следующем обновлении!",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
        return MAIN_MENU
    
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для подтверждения",
            reply_markup=ReplyKeyboardMarkup([
                ['✅ Да, удалить все данные'],
                ['❌ Отмена']
            ], resize_keyboard=True)
        )
        return CLEAR_DATA_CONFIRM

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

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка главного меню"""
    text = update.message.text
    
    if text == '💪 Начать тренировку':
        from handlers.training import start_training
        return await start_training(update, context)
    elif text == '📊 История тренировок':
        from handlers.training import show_training_history
        return await show_training_history(update, context)
    elif text == '📝 Мои упражнения':
        from handlers.exercises import show_exercises_management
        return await show_exercises_management(update, context)
    elif text == '📈 Статистика':
        from handlers.statistics import show_statistics_menu
        return await show_statistics_menu(update, context)
    elif text == '📏 Мои замеры':
        from handlers.measurements import show_measurements_history
        return await show_measurements_history(update, context)
    elif text == '📤 Выгрузка данных':
        from handlers.export import show_export_menu
        return await show_export_menu(update, context)
    elif text == '❓ Помощь':
        return await help_command(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки меню")

        return MAIN_MENU

