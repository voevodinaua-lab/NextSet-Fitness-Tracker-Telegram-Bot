import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from handlers_common import start

from database import get_custom_exercises, add_custom_exercise, delete_custom_exercise
from utils_constants import *
from utils_constants import DEFAULT_STRENGTH_EXERCISES, DEFAULT_CARDIO_EXERCISES

logger = logging.getLogger(__name__)

async def show_exercises_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать управление упражнениями"""
    user_id = update.message.from_user.id
    exercises = get_custom_exercises(user_id)
    
    # Получаем все упражнения пользователя (стандартные + пользовательские)
    all_strength = DEFAULT_STRENGTH_EXERCISES + exercises['strength']
    all_cardio = DEFAULT_CARDIO_EXERCISES + exercises['cardio']
    
    exercises_text = "📝 Ваши упражнения:\n\n"
    exercises_text += "💪 Силовые:\n"
    for ex in all_strength:
        exercises_text += f"• {ex}\n"
    
    exercises_text += "\n🏃 Кардио:\n"
    for ex in all_cardio:
        exercises_text += f"• {ex}\n"
    
    keyboard = [
        ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        exercises_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return EXERCISES_MANAGEMENT

async def handle_exercises_management_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора в управлении упражнениями"""
    text = update.message.text
    
    print(f"\n=== DEBUG handle_exercises_management_choice ===")
    print(f"Получен текст: '{text}'")
    
    if text == '➕ Добавить упражнение':
        print("-> choose_exercise_type_mgmt")
        return await choose_exercise_type_mgmt(update, context)
    
    elif text == '🗑️ Удалить упражнение':
        print("-> show_delete_exercise_menu")
        return await show_delete_exercise_menu(update, context)
    
    elif text == '🔙 Главное меню':
        print("-> start")
        return await start(update, context)
    
    else:
        print("-> show_exercises_management (fallback)")
        return await show_exercises_management(update, context
                                              
async def choose_exercise_type_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор типа упражнения для добавления (из управления)"""
    keyboard = [
        ['💪 Силовое упражнение', '🏃 Кардио упражнение'],
        ['🔙 Назад к управлению упражнениями']
    ]
    
    await update.message.reply_text(
        "Выберите тип упражнения для добавления:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ADD_EXERCISE_TYPE_MGMT

async def add_custom_exercise_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора типа упражнения в управлении"""
    choice = update.message.text
    
    if choice == '🔙 Назад к управлению упражнениями':
        return await show_exercises_management(update, context)
    
    if '💪 Силовое' in choice:
        context.user_data['adding_exercise_type'] = STRENGTH_TYPE
        await update.message.reply_text(
            "Введите название нового силового упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_NEW_STRENGTH_EXERCISE_MGMT
    elif '🏃 Кардио' in choice:
        context.user_data['adding_exercise_type'] = CARDIO_TYPE
        await update.message.reply_text(
            "Введите название нового кардио упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_NEW_CARDIO_EXERCISE_MGMT
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для выбора типа упражнения",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Силовое упражнение', '🏃 Кардио упражнение'],
                ['🔙 Назад к управлению упражнениями']
            ], resize_keyboard=True)
        )
        return ADD_EXERCISE_TYPE_MGMT

async def save_new_strength_exercise_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение нового силового упражнения из управления"""
    return await save_new_exercise_mgmt(update, context, STRENGTH_TYPE)

async def save_new_cardio_exercise_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение нового кардио упражнения из управления"""
    return await save_new_exercise_mgmt(update, context, CARDIO_TYPE)

async def save_new_exercise_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE, exercise_type: str) -> int:
    """Сохранение нового упражнения из управления"""
    user_id = update.message.from_user.id
    exercise_name = update.message.text
    
    # Проверяем, не является ли это стандартным упражнением
    if exercise_type == STRENGTH_TYPE and exercise_name in DEFAULT_STRENGTH_EXERCISES:
        await update.message.reply_text(
            f"❌ Упражнение '{exercise_name}' уже есть в стандартном списке!",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return EXERCISES_MANAGEMENT
    
    if exercise_type == CARDIO_TYPE and exercise_name in DEFAULT_CARDIO_EXERCISES:
        await update.message.reply_text(
            f"❌ Упражнение '{exercise_name}' уже есть в стандартном списке!",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return EXERCISES_MANAGEMENT
    
    # Добавляем упражнение в БД
    success = add_custom_exercise(user_id, exercise_name, exercise_type)
    
    if success:
        await update.message.reply_text(
            f"✅ Упражнение '{exercise_name}' добавлено в ваш список!",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось добавить упражнение.",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
    
    # Очищаем временные данные
    context.user_data.pop('adding_exercise_type', None)
    
    return EXERCISES_MANAGEMENT

async def show_delete_exercise_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню удаления упражнений"""
    user_id = update.message.from_user.id
    custom_exercises = get_custom_exercises(user_id)
    
    # Показываем только пользовательские упражнения для удаления
    if not custom_exercises['strength'] and not custom_exercises['cardio']:
        await update.message.reply_text(
            "❌ У вас нет пользовательских упражнений для удаления.\n"
            "Вы можете удалять только те упражнения, которые добавили сами.",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return EXERCISES_MANAGEMENT
    
    # Создаем клавиатуру с пользовательскими упражнениями
    keyboard = []
    
    # Пользовательские силовые упражнения
    for ex in custom_exercises['strength']:
        keyboard.append([f"💪 {ex}"])
    
    # Пользовательские кардио упражнения
    for ex in custom_exercises['cardio']:
        keyboard.append([f"🏃 {ex}"])
    
    keyboard.append(['🔙 Назад к управлению упражнениями'])
    
    await update.message.reply_text(
        "🗑️ Выберите упражнение для удаления:\n"
        "(отображаются только ваши пользовательские упражнения)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return DELETE_EXERCISE_MENU

async def delete_exercise_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Удаление выбранного упражнения"""
    user_id = update.message.from_user.id
    exercise_with_emoji = update.message.text
    
    if exercise_with_emoji == '🔙 Назад к управлению упражнениями':
        return await show_exercises_management(update, context)
    
    # Извлекаем название упражнения и тип из текста
    if exercise_with_emoji.startswith('💪 '):
        exercise_name = exercise_with_emoji[3:]  # Убираем "💪 "
        exercise_type = STRENGTH_TYPE
    elif exercise_with_emoji.startswith('🏃 '):
        exercise_name = exercise_with_emoji[3:]  # Убираем "🏃 "
        exercise_type = CARDIO_TYPE
    else:
        await update.message.reply_text(
            "❌ Не удалось распознать упражнение.",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return EXERCISES_MANAGEMENT
    
    # Удаляем упражнение из БД
    success = delete_custom_exercise(user_id, exercise_name, exercise_type)
    
    if success:
        await update.message.reply_text(
            f"✅ Упражнение '{exercise_name}' удалено!",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
    else:
        await update.message.reply_text(
            f"❌ Не удалось удалить упражнение '{exercise_name}'.",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
    

    return EXERCISES_MANAGEMENT

