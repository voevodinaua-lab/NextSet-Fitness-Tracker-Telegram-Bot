import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from database import (
    create_user, get_current_training, create_training, save_training_measurements,
    add_exercise_to_training, get_training_exercises, finish_training, get_user_trainings,
    save_measurement, get_custom_exercises, add_custom_exercise
)
from utils_constants import *

logger = logging.getLogger(__name__)

async def start_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало тренировки"""
    user = update.message.from_user
    user_id = user.id
    
    # Создаем пользователя если его нет
    create_user(user_id, user.username, user.first_name)
    
    # Проверяем есть ли текущая тренировка
    current_training = get_current_training(user_id)
    
    if current_training:
        # Продолжаем существующую тренировку
        context.user_data['current_training'] = current_training
        context.user_data['training_id'] = current_training['training_id']
        
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        
        await update.message.reply_text(
            f"🎯 Продолжаем тренировку от {current_training['date_start']}!\n\n"
            "Выберите тип упражнения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING_MENU
    else:
        # Создаем новую тренировку
        new_training = create_training(user_id)
        if not new_training:
            await update.message.reply_text("❌ Не удалось создать тренировку. Попробуйте позже.")
            return MAIN_MENU
        
        context.user_data['current_training'] = new_training
        context.user_data['training_id'] = new_training['training_id']
        
        keyboard = [
            ['📝 Ввести замеры', '⏭️ Пропустить замеры'],
            ['🔙 Главное меню']
        ]
        
        await update.message.reply_text(
            f"🎯 Отлично стартуем! Сегодня {new_training['date_start']}\n\n"
            "📏 Хотите ли ввести замеры перед тренировкой?\n"
            "(например: вес 65кг, талия 70см, бедра 95см)",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return INPUT_MEASUREMENTS_CHOICE

async def handle_measurements_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора ввода замеров"""
    choice = update.message.text
    print(f"DEBUG: handle_measurements_choice получил: '{choice}'")
    
    if choice == '🔙 Главное меню':
        # Очищаем данные тренировки при выходе
        context.user_data.pop('current_training', None)
        context.user_data.pop('training_id', None)
        return await start(update, context)
    
    elif choice == '⏭️ Пропустить замеры':
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        
        await update.message.reply_text(
            "✅ Начинаем тренировку! Выберите тип упражнения:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING_MENU
    
    elif choice == '📝 Ввести замеры':
        await update.message.reply_text(
            "Введите ваши замеры:\n"
            "(например: вес 65кг, талия 70см, бедра 95см)\n",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_MEASUREMENTS
    
    else:
        # Этот блок теперь не должен вызываться, но на всякий случай
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для выбора действия",
            reply_markup=ReplyKeyboardMarkup([
                ['📝 Ввести замеры', '⏭️ Пропустить замеры'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return INPUT_MEASUREMENTS_CHOICE

async def save_measurements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение замеров и переход к тренировке"""
    user_id = update.message.from_user.id
    measurements = update.message.text
    
    training_id = context.user_data.get('training_id')
    
    if measurements.lower() != 'пропустить' and training_id:
        # Сохраняем замеры в тренировку
        save_training_measurements(training_id, measurements)
        
        # Сохраняем замеры в историю
        save_measurement(user_id, measurements)
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        "✅ Продолжаем тренировку! Выберите тип упражнения:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return TRAINING_MENU

async def show_strength_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать силовые упражнения"""
    user_id = update.message.from_user.id
    
    # Получаем все упражнения пользователя
    custom_exercises = get_custom_exercises(user_id)
    all_strength_exercises = DEFAULT_STRENGTH_EXERCISES + custom_exercises['strength']
    
    # Создаем клавиатуру с упражнениями
    keyboard = []
    for i in range(0, len(all_strength_exercises), 2):
        row = all_strength_exercises[i:i+2]
        keyboard.append(row)
    
    keyboard.append(['🔙 Назад к тренировке'])
    
    await update.message.reply_text(
        "💪 Выберите силовое упражнение:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_STRENGTH_EXERCISE

async def handle_strength_exercise_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора силового упражнения"""
    exercise_name = update.message.text
    
    if exercise_name == '🔙 Назад к тренировке':
        return await show_training_menu(update, context)
    
    # Сохраняем выбранное упражнение
    context.user_data['current_exercise'] = {
        'name': exercise_name,
        'type': STRENGTH_TYPE,
        'sets': []
    }
    
    await update.message.reply_text(
        f"💪 Выбрано: {exercise_name}\n\n"
        "Введите подходы в формате (каждый подход с новой строки):\n"
        "**Вес Количество_повторений**\n\n"
        "📝 Пример:\n"
        "50 12\n"
        "55 10\n"
        "60 8\n\n"
        "Или введите один подход: 50 12",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_SETS

async def handle_set_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода подходов"""
    text = update.message.text
    
    # Разбиваем на строки для обработки нескольких подходов
    lines = text.strip().split('\n')
    valid_sets = []
    errors = []
    
    for line_num, line in enumerate(lines, 1):
        if not line.strip():
            continue
            
        line_clean = line.replace(',', '.').replace('/', ' ').replace('х', ' ').replace('x', ' ')
        parts = line_clean.split()
        
        if len(parts) >= 2:
            try:
                weight = float(parts[0])
                reps = int(parts[1])
                
                valid_sets.append({
                    'weight': weight,
                    'reps': reps
                })
                
            except (ValueError, IndexError):
                errors.append(f"Строка {line_num}: неверный формат '{line}'")
        else:
            errors.append(f"Строка {line_num}: недостаточно данных '{line}'")
    
    if valid_sets:
        if 'current_exercise' not in context.user_data:
            context.user_data['current_exercise'] = {'sets': []}
        
        context.user_data['current_exercise']['sets'].extend(valid_sets)
        
        sets_count = len(context.user_data['current_exercise']['sets'])
        sets_text = "✅ Текущие подходы:\n"
        for i, set_data in enumerate(context.user_data['current_exercise']['sets'], 1):
            sets_text += f"{i}. {set_data['weight']}кг × {set_data['reps']} повторений\n"
        
        error_text = ""
        if errors:
            error_text = "\n❌ Ошибки:\n" + "\n".join(errors) + "\n"
        
        keyboard = [['✅ Добавить еще подходы', '💾 Сохранить упражнение'], ['❌ Отменить упражнение']]
        
        await update.message.reply_text(
            f"{sets_text}\n"
            f"Всего подходов: {sets_count}\n"
            f"{error_text}\n"
            "Выберите действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return INPUT_SETS
    else:
        await update.message.reply_text(
            "❌ Не удалось распознать подходы.\n\n"
            "Введите подходы в формате (каждый подход с новой строки):\n"
            "**Вес Количество_повторений**\n\n"
            "📝 Пример:\n"
            "50 12\n"
            "55 10\n"
            "60 8\n\n"
            "Или введите один подход: 50 12"
        )
        return INPUT_SETS

async def add_another_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление еще подходов"""
    await update.message.reply_text(
        "Введите следующие подходы в формате (каждый подход с новой строки):\n"
        "**Вес Количество_повторений**\n\n"
        "📝 Пример:\n"
        "65 6\n"
        "70 4\n\n"
        "Или введите один подход: 65 6",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_SETS

async def save_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение упражнения с подходами"""
    training_id = context.user_data.get('training_id')
    
    if 'current_exercise' not in context.user_data or not training_id:
        await update.message.reply_text("❌ Нет данных для сохранения.")
        return await show_training_menu(update, context)
    
    exercise_data = context.user_data['current_exercise']
    
    # Сохраняем упражнение в БД
    success = add_exercise_to_training(training_id, exercise_data)
    
    if success:
        # Формируем текст сохраненного упражнения
        exercise_text = f"💪 {exercise_data['name']}:\n"
        for i, set_data in enumerate(exercise_data['sets'], 1):
            exercise_text += f"{i}. {set_data['weight']}кг × {set_data['reps']} повторений\n"
        
        # Очищаем временные данные
        context.user_data.pop('current_exercise', None)
        
        await update.message.reply_text(
            f"✅ Упражнение сохранено!\n\n{exercise_text}",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Силовые упражнения', '🏃 Кардио'],
                ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
            ], resize_keyboard=True)
        )
    else:
        await update.message.reply_text("❌ Не удалось сохранить упражнение.")
    
    return TRAINING_MENU

async def show_cardio_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать кардио упражнения"""
    user_id = update.message.from_user.id
    
    custom_exercises = get_custom_exercises(user_id)
    all_cardio_exercises = DEFAULT_CARDIO_EXERCISES + custom_exercises['cardio']
    
    keyboard = [[exercise] for exercise in all_cardio_exercises]
    keyboard.append(['✏️ Добавить кардио упражнение'])
    keyboard.append(['🔙 Назад к тренировке'])
    
    await update.message.reply_text(
        "🏃 Выберите кардио упражнение:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_CARDIO_EXERCISE

async def handle_cardio_exercise_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора кардио упражнения"""
    exercise_name = update.message.text
    
    if exercise_name == '✏️ Добавить кардио упражнение':
        await update.message.reply_text(
            "Введите название нового кардио упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_NEW_CARDIO_EXERCISE
    
    if exercise_name == '🔙 Назад к тренировке':
        return await show_training_menu(update, context)
    
    # Сохраняем выбранное кардио упражнение
    context.user_data['current_exercise'] = {
        'name': exercise_name,
        'type': CARDIO_TYPE
    }
    
    keyboard = [
        ['⏱️ Мин/Метры', '🚀 Км/Час'],
        ['🔙 Назад к кардио']
    ]
    
    await update.message.reply_text(
        f"🏃 Выбрано: {exercise_name}\n\n"
        "Выберите формат ввода:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CARDIO_TYPE_SELECTION

async def handle_cardio_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора формата кардио"""
    choice = update.message.text
    
    if choice == '🔙 Назад к кардио':
        return await show_cardio_exercises(update, context)
    
    if choice not in ['⏱️ Мин/Метры', '🚀 Км/Час']:
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для выбора формата",
            reply_markup=ReplyKeyboardMarkup([
                ['⏱️ Мин/Метры', '🚀 Км/Час'],
                ['🔙 Назад к кардио']
            ], resize_keyboard=True)
        )
        return CARDIO_TYPE_SELECTION
    
    context.user_data['cardio_format'] = choice
    
    if choice == '⏱️ Мин/Метры':
        await update.message.reply_text(
            "Введите время и дистанцию в формате:\n"
            "**Время_в_минутах Дистанция_в_метрах**\n\n"
            "📝 Пример: 30 5000 (30 минут, 5000 метров)",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_CARDIO_MIN_METERS
    elif choice == '🚀 Км/Час':
        await update.message.reply_text(
            "Введите время и скорость в формате:\n"
            "**Время_в_минутах Скорость_км/ч**\n\n"
            "📝 Пример: 30 10 (30 минут, 10 км/ч)",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_CARDIO_KM_H

async def handle_cardio_min_meters_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода кардио в формате минуты/метры"""
    return await save_cardio_exercise(update, context, 'min_meters')

async def handle_cardio_km_h_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода кардио в формате км/ч"""
    return await save_cardio_exercise(update, context, 'km_h')

async def save_cardio_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE, format_type: str):
    """Сохранение кардио упражнения"""
    training_id = context.user_data.get('training_id')
    text = update.message.text
    
    if 'current_exercise' not in context.user_data or not training_id:
        await update.message.reply_text("❌ Нет данных для сохранения.")
        return await show_training_menu(update, context)
    
    try:
        parts = text.split()
        if len(parts) != 2:
            raise ValueError("Нужно ввести два числа")
        
        time_minutes = int(parts[0])
        value = float(parts[1])
        
        exercise_data = context.user_data['current_exercise'].copy()
        
        if format_type == 'min_meters':
            exercise_data.update({
                'time_minutes': time_minutes,
                'distance_meters': value,
                'details': f"{time_minutes} минут, {value} метров"
            })
        else:  # km_h
            exercise_data.update({
                'time_minutes': time_minutes,
                'speed_kmh': value,
                'details': f"{time_minutes} минут, {value} км/ч"
            })
        
        # Сохраняем упражнение в БД
        success = add_exercise_to_training(training_id, exercise_data)
        
        if success:
            # Очищаем временные данные
            context.user_data.pop('current_exercise', None)
            context.user_data.pop('cardio_format', None)
            
            await update.message.reply_text(
                f"✅ Кардио сохранено!\n{exercise_data['name']}: {exercise_data['details']}",
                reply_markup=ReplyKeyboardMarkup([
                    ['💪 Силовые упражнения', '🏃 Кардио'],
                    ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
                ], resize_keyboard=True)
            )
        else:
            await update.message.reply_text("❌ Не удалось сохранить кардио.")
        
        return TRAINING_MENU
        
    except (ValueError, IndexError):
        if format_type == 'min_meters':
            await update.message.reply_text(
                "❌ Неверный формат. Введите два числа:\n"
                "**Время_в_минутах Дистанция_в_метрах**\n\n"
                "📝 Пример: 30 5000"
            )
            return INPUT_CARDIO_MIN_METERS
        else:
            await update.message.reply_text(
                "❌ Неверный формат. Введите два числа:\n"
                "**Время_в_минутах Скорость_км/ч**\n\n"
                "📝 Пример: 30 10"
            )
            return INPUT_CARDIO_KM_H

async def show_training_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню тренировки"""
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        "Выберите тип упражнения:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return TRAINING_MENU

async def finish_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершение тренировки - показ сводки"""
    training_id = context.user_data.get('training_id')
    
    if not training_id:
        await update.message.reply_text("❌ Нет активной тренировки.")
        return MAIN_MENU
    
    # Получаем текущую тренировку с упражнениями
    current_training = get_current_training(update.message.from_user.id)
    
    if not current_training or not current_training['exercises']:
        await update.message.reply_text(
            "❌ В тренировке нет упражнений. Добавьте хотя бы одно упражнение перед завершением.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Силовые упражнения', '🏃 Кардио'],
                ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
            ], resize_keyboard=True)
        )
        return TRAINING_MENU
    
    # Формируем сводку по тренировке
    report = "📊 СВОДКА ПО ТРЕНИРОВКЕ\n\n"
    report += f"📅 Дата: {current_training['date_start']}\n\n"
    
    if current_training['measurements']:
        report += f"📏 Замеры: {current_training['measurements']}\n\n"
    
    report += "💪 Выполненные упражнения:\n\n"
    
    total_exercises = len(current_training['exercises'])
    strength_count = 0
    cardio_count = 0
    
    for i, exercise in enumerate(current_training['exercises'], 1):
        if exercise.get('is_cardio'):
            cardio_count += 1
            report += f"🏃 {i}. {exercise['name']}\n"
            report += f"   Детали: {exercise['details']}\n\n"
        else:
            strength_count += 1
            report += f"💪 {i}. {exercise['name']}\n"
            for j, set_data in enumerate(exercise['sets'], 1):
                report += f"   {j}. {set_data['weight']}кг × {set_data['reps']}\n"
            report += "\n"
    
    report += f"📊 Всего упражнений: {total_exercises}\n"
    report += f"• Силовых: {strength_count}\n"
    report += f"• Кардио: {cardio_count}\n"
    
    keyboard = [
        ['✅ Точно завершить', '✏️ Скорректировать'],
        ['🔙 Продолжить тренировку']
    ]
    
    await update.message.reply_text(
        report,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CONFIRM_FINISH

async def handle_finish_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения завершения тренировки"""
    choice = update.message.text
    training_id = context.user_data.get('training_id')
    user_id = update.message.from_user.id
    
    if choice == '🔙 Продолжить тренировку':
        return await show_training_menu(update, context)
    
    elif choice == '✏️ Скорректировать':
        # TODO: Реализовать редактирование тренировки
        await update.message.reply_text(
            "Функция редактирования будет реализована в следующем обновлении.",
            reply_markup=ReplyKeyboardMarkup([
                ['✅ Точно завершить'],
                ['🔙 Продолжить тренировку']
            ], resize_keyboard=True)
        )
        return CONFIRM_FINISH
    
    elif choice == '✅ Точно завершить':
        # Завершаем тренировку
        success = finish_training(training_id)
        
        if success:
            # Очищаем данные тренировки
            context.user_data.pop('current_training', None)
            context.user_data.pop('training_id', None)
            context.user_data.pop('current_exercise', None)
            context.user_data.pop('cardio_format', None)
            
            await update.message.reply_text(
                "🏆 Тренировка завершена и сохранена! 🏆",
                reply_markup=ReplyKeyboardMarkup([
                    ['💪 Начать тренировку', '📊 История тренировок'],
                    ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                    ['📤 Выгрузка данных', '❓ Помощь']
                ], resize_keyboard=True)
            )
        else:
            await update.message.reply_text("❌ Не удалось завершить тренировку.")
        
        return MAIN_MENU
    
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для выбора действия",
            reply_markup=ReplyKeyboardMarkup([
                ['✅ Точно завершить', '✏️ Скорректировать'],
                ['🔙 Продолжить тренировку']
            ], resize_keyboard=True)
        )
        return CONFIRM_FINISH

async def show_training_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать историю тренировок"""
    user_id = update.message.from_user.id
    trainings = get_user_trainings(user_id, limit=5)
    
    if not trainings:
        info_text = "💾 Все ваши будущие тренировки будут автоматически сохраняться в базе данных."
        await update.message.reply_text(
            f"📝 У вас пока нет завершенных тренировок.\n\n{info_text}",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
        return MAIN_MENU
    
    history_text = "📊 Последние тренировки:\n\n"
    
    for i, training in enumerate(trainings, 1):
        history_text += f"🏋️ Тренировка #{i}\n"
        history_text += f"📅 {training['date_start']}\n"
        
        strength_count = sum(1 for ex in training['exercises'] if not ex.get('is_cardio'))
        cardio_count = sum(1 for ex in training['exercises'] if ex.get('is_cardio'))
        
        history_text += f"Упражнений: {len(training['exercises'])} (💪{strength_count} 🏃{cardio_count})\n"
        
        if training['comment']:
            history_text += f"💬 {training['comment']}\n"
        
        history_text += "------\n"
    
    history_text += f"\n💾 Всего тренировок сохранено: {len(trainings)}\n"
    
    await update.message.reply_text(history_text)
    return MAIN_MENU

async def cancel_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущего упражнения"""
    exercise_name = context.user_data.get('current_exercise', {}).get('name', 'упражнение')
    context.user_data.pop('current_exercise', None)
    context.user_data.pop('cardio_format', None)
    
    await update.message.reply_text(
        f"❌ {exercise_name} - удалено",
        reply_markup=ReplyKeyboardMarkup([
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ], resize_keyboard=True)
    )
    
    return TRAINING_MENU

# Функции для добавления упражнений в режиме тренировки
async def choose_exercise_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор типа упражнения для добавления"""
    keyboard = [
        ['💪 Силовое упражнение', '🏃 Кардио упражнение'],
        ['🔙 Назад к тренировке']
    ]
    
    await update.message.reply_text(
        "Выберите тип упражнения для добавления:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ADD_EXERCISE_TYPE

async def add_custom_exercise_from_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление пользовательского упражнения из тренировки"""
    choice = update.message.text
    
    if choice == '🔙 Назад к тренировке':
        return await show_training_menu(update, context)
    
    if '💪 Силовое' in choice:
        context.user_data['adding_exercise_type'] = STRENGTH_TYPE
        await update.message.reply_text(
            "Введите название нового силового упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_NEW_STRENGTH_EXERCISE
    elif '🏃 Кардио' in choice:
        context.user_data['adding_exercise_type'] = CARDIO_TYPE
        await update.message.reply_text(
            "Введите название нового кардио упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
        return INPUT_NEW_CARDIO_EXERCISE
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для выбора типа упражнения",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Силовое упражнение', '🏃 Кардио упражнение'],
                ['🔙 Назад к тренировке']
            ], resize_keyboard=True)
        )
        return ADD_EXERCISE_TYPE

async def save_new_exercise_from_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение нового упражнения из тренировки"""
    user_id = update.message.from_user.id
    exercise_name = update.message.text
    exercise_type = context.user_data.get('adding_exercise_type', STRENGTH_TYPE)
    
    # Добавляем упражнение в БД
    success = add_custom_exercise(user_id, exercise_name, exercise_type)
    
    if success:
        await update.message.reply_text(f"✅ Упражнение '{exercise_name}' добавлено в ваш список!")
    else:
        await update.message.reply_text("❌ Не удалось добавить упражнение.")
    
    # Очищаем временные данные
    context.user_data.pop('adding_exercise_type', None)
    
    # Возвращаемся к соответствующему выбору упражнений
    if exercise_type == STRENGTH_TYPE:
        return await show_strength_exercises(update, context)
    else:

        return await show_cardio_exercises(update, context)
        
async def continue_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Продолжение текущей тренировки"""
    user_id = update.message.from_user.id
    current_training = get_current_training(user_id)
    
    if not current_training:
        await update.message.reply_text(
            "❌ Текущая тренировка не найдена. Начинаем новую.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Силовые упражнения', '🏃 Кардио'],
                ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
            ], resize_keyboard=True)
        )
        return TRAINING_MENU
    
    # Сохраняем training_id в context для использования в других функциях
    context.user_data['current_training_id'] = current_training['training_id']
    
    training_info = f"""
🏃‍♂️ Продолжаем тренировку от {current_training['date_start']}

Уже добавлено упражнений: {len(current_training['exercises'])}
    """
    
    await update.message.reply_text(
        training_info,
        reply_markup=ReplyKeyboardMarkup([
            ['💪 Силовые упражнения', '🏃 Кардиo'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ], resize_keyboard=True)
    )
    return TRAINING_MENU
    
async def handle_training_menu_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нераспознанных сообщений в меню тренировки"""
    print(f"DEBUG: handle_training_menu_fallback получил: '{update.message.text}'")
    
    # Просто показываем меню тренировки снова
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        "❌ Пожалуйста, используйте кнопки меню тренировки:\n\n"
        "Выберите тип упражнения:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return TRAINING_MENU
    
async def handle_training_menu_simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Упрощенный обработчик меню тренировки"""
    text = update.message.text
    print(f"🚨 TRAINING_MENU получил: '{text}'")
    
    if text == '💪 Силовые упражнения':
        await update.message.reply_text("✅ Переходим к силовым упражнениям!")
        return await show_strength_exercises(update, context)
    elif text == '🏃 Кардио':
        await update.message.reply_text("✅ Переходим к кардио!")
        return await show_cardio_exercises(update, context)
    elif text == '✏️ Добавить свое упражнение':
        await update.message.reply_text("✅ Добавляем упражнение!")
        return await choose_exercise_type(update, context)
    elif text == '🏁 Завершить тренировку':
        await update.message.reply_text("✅ Завершаем тренировку!")
        return await finish_training(update, context)
    else:
        # Показываем меню снова
        keyboard = [
            ['💪 Силовые упражнения', '🏃 Кардио'],
            ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
        ]
        
        await update.message.reply_text(
            f"Получено: '{text}'. Используйте кнопки тренировки:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return TRAINING_MENU
