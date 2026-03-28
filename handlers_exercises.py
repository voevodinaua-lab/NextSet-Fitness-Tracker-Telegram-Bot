import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from handlers_common import start

from database import (
    get_custom_exercises,
    add_custom_exercise,
    get_visible_exercise_lists,
    remove_exercise_from_user_catalog,
)
from utils_constants import *

logger = logging.getLogger(__name__)

async def show_exercises_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать управление упражнениями"""
    user_id = update.message.from_user.id
    visible = get_visible_exercise_lists(user_id)
    all_strength = visible["strength"]
    all_cardio = visible["cardio"]
    
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
    
    if text == '➕ Добавить упражнение':
        return await choose_exercise_type_mgmt(update, context)
    
    elif text == '🗑️ Удалить упражнение':
        return await show_delete_exercise_menu(update, context)
    
    elif text == '🔙 Главное меню':
        return await start(update, context)
    
    else:
        return await show_exercises_management(update, context)
                                              
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
    
    visible = get_visible_exercise_lists(user_id)
    key = "strength" if exercise_type == STRENGTH_TYPE else "cardio"
    if exercise_name in visible[key]:
        await update.message.reply_text(
            f"❌ Упражнение «{exercise_name}» уже есть в вашем списке.",
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
    visible = get_visible_exercise_lists(user_id)

    if not visible["strength"] and not visible["cardio"]:
        await update.message.reply_text(
            "❌ В списке нет упражнений. Добавьте своё или сбросьте скрытые через поддержку.",
            reply_markup=ReplyKeyboardMarkup([
                ['➕ Добавить упражнение', '🗑️ Удалить упражнение'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return EXERCISES_MANAGEMENT
    
    keyboard = []
    for ex in visible["strength"]:
        keyboard.append([f"💪 {ex}"])
    for ex in visible["cardio"]:
        keyboard.append([f"🏃 {ex}"])
    
    keyboard.append(['🔙 Назад к управлению упражнениями'])
    
    await update.message.reply_text(
        "🗑️ Выберите упражнение, чтобы убрать его из списка:\n"
        "(свои — удаляются из базы, стандартные — скрываются для вас)",
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
    
    success = remove_exercise_from_user_catalog(user_id, exercise_name, exercise_type)
    
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


