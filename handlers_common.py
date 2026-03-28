import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from database import (
    create_user, get_custom_exercises, get_user_trainings, 
    get_current_training, finish_training, create_training,
    delete_all_user_data
)
from utils_constants import *

logger = logging.getLogger(__name__)

def is_new_user(user_id):
    """Определяет новый ли пользователь (нет никаких записей в БД)"""
    # Проверяем есть ли ЛЮБЫЕ записи пользователя
    trainings = get_user_trainings(user_id, limit=1)
    current_training = get_current_training(user_id)
    custom_exercises = get_custom_exercises(user_id)
    
    has_any_data = (
        len(trainings) > 0 or 
        current_training is not None or
        len(custom_exercises['strength']) > 0 or 
        len(custom_exercises['cardio']) > 0
    )
    
    return not has_any_data

async def handle_unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений, когда бот не в активном состоянии"""
    if context.user_data.get('in_conversation'):
        return await handle_main_menu(update, context)
    
    user = update.message.from_user
    user_id = user.id
    
    # Создаем пользователя в БД если его нет
    create_user(user_id, user.username, user.first_name)
    
    # Определяем тип пользователя
    if is_new_user(user_id):
        return await show_welcome_new_user(update, context)
    else:
        return await show_welcome_existing_user(update, context)

async def show_welcome_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие для нового пользователя"""
    user = update.message.from_user
    
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

async def show_welcome_existing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие для существующего пользователя"""
    user = update.message.from_user
    user_id = user.id
    
    # Проверяем есть ли текущая тренировка
    current_training = get_current_training(user_id)
    
    if current_training:
        return await show_welcome_with_current_training(update, context, current_training)
    else:
        return await show_welcome_without_current_training(update, context)

async def show_welcome_with_current_training(update: Update, context: ContextTypes.DEFAULT_TYPE, current_training):
    """Приветствие когда есть текущая тренировка"""
    user = update.message.from_user
    
    welcome_text = f"""
👋 С возвращением, {user.first_name}! 

У вас есть незавершенная тренировка от {current_training['date_start']}.

Выберите действие:
    """
    
    keyboard = [
        ['🏃‍♂️ Продолжить тренировку'],
        ['🆕 Начать новую тренировку'],
        ['🗑️ Очистить историю']
    ]
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return INACTIVE

async def show_welcome_without_current_training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие когда нет текущей тренировки"""
    user = update.message.from_user
    
    welcome_text = f"""
👋 С возвращением, {user.first_name}! 

Ваша история тренировок сохранена.

Выберите действие:
    """
    
    keyboard = [
        ['🚀 Продолжить'],
        ['🗑️ Очистить историю']
    ]
    
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
    """Начало работы с ботом - переход в главное меню"""
    user = update.message.from_user
    user_id = user.id
    
    # Создаем/обновляем пользователя в БД
    create_user(user_id, user.username, user.first_name)
    
    # Устанавливаем флаг активной конверсации
    context.user_data['in_conversation'] = True
    
    welcome_text = f"""
🎉 Добро пожаловать, {user.first_name}! 

Выберите действие:
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
    """Обработка выбора в неактивном состоянии"""
    choice = update.message.text
    user_id = update.message.from_user.id
    
    if choice == '🚀 Начать':
        return await start(update, context)
    
    elif choice == '🚀 Продолжить':
        return await start(update, context)
    
    elif choice == '🏃‍♂️ Продолжить тренировку':
        from handlers_training import continue_training
        return await continue_training(update, context)
    
    elif choice == '🆕 Начать новую тренировку':
        # Завершаем текущую тренировку и начинаем новую
        current_training = get_current_training(user_id)
        if current_training:
            finish_training(current_training['training_id'], "Автозавершена")
        
        from handlers_training import start_training
        return await start_training(update, context)
    
    elif choice == '🗑️ Очистить историю':
        return await show_clear_data_confirmation(update, context)
    
    else:
        # Показываем соответствующие кнопки
        if is_new_user(user_id):
            return await show_welcome_new_user(update, context)
        else:
            current_training = get_current_training(user_id)
            if current_training:
                return await show_welcome_with_current_training(update, context, current_training)
            else:
                return await show_welcome_without_current_training(update, context)

async def show_clear_data_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ подтверждения очистки данных"""
    warning_text = """
⚠️ ВНИМАНИЕ: Вы собираетесь удалить все ваши данные!

Это действие:
• Удалит все тренировки и замеры
• Удалит все ваши пользовательские упражнения
• Стандартные упражнения останутся
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

async def handle_clear_data_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения очистки данных"""
    choice = update.message.text
    user_id = update.message.from_user.id
    
    if choice == '❌ Отмена':
        return await start(update, context)
    
    elif choice == '✅ Да, удалить все данные':
        # Удаляем все данные пользователя
        success = delete_all_user_data(user_id)
        
        if success:
            await update.message.reply_text(
                "✅ Все ваши данные успешно удалены!",
                reply_markup=ReplyKeyboardRemove()
            )
            # Показываем приветствие для нового пользователя
            return await show_welcome_new_user(update, context)
        else:
            await update.message.reply_text(
                "❌ Ошибка при удалении данных. Попробуйте позже.",
                reply_markup=ReplyKeyboardMarkup([['🚀 Продолжить']], resize_keyboard=True)
            )
            return INACTIVE
    
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
    user_id = update.message.from_user.id
    
    print(f"DEBUG: Получено сообщение: {text} от пользователя {user_id}")
    
    if text == '💪 Начать тренировку':
        from handlers_training import start_training
        return await start_training(update, context)
    elif text == '📊 История тренировок':
        from handlers_training import show_training_history
        return await show_training_history(update, context)
    elif text == '📝 Мои упражнения':
        from handlers_exercises import show_exercises_management
        return await show_exercises_management(update, context)
    elif text == '📈 Статистика':
        from handlers_statistics import show_statistics_menu
        return await show_statistics_menu(update, context)
    elif text == '📏 Мои замеры':
        from handlers_measurements import show_measurements_history
        return await show_measurements_history(update, context)
    elif text == '📤 Выгрузка данных':
        from handlers_export import show_export_menu
        return await show_export_menu(update, context)
    elif text == '❓ Помощь':
        return await help_command(update, context)
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки меню",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
        return MAIN_MENU
