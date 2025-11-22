import logging
import re
import csv
import io
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния бота
(
    MAIN_MENU, TRAINING, CHOOSE_EXERCISE, INPUT_SETS,
    ADD_CUSTOM_EXERCISE, ADD_CUSTOM_CARDIO, INPUT_MEASUREMENTS, 
    INPUT_COMMENT, STATS_PERIOD, EXPORT_MENU, EXPORT_PERIOD
) = range(11)

# База упражнений по умолчанию
DEFAULT_STRENGTH_EXERCISES = [
    "Румынская тяга",
    "Ягодичный мостик", 
    "Болгарский выпад",
    "Скручивания (пресс) в тренажере",
    "Воздушные выпады с отягощением на степе",
    "Отведения ноги назад в кроссовере",
    "Отведение ноги в сторону в кроссовере",
    "Скручивания и разгибание колен на полу"
]

DEFAULT_CARDIO_EXERCISES = [
    "Бег на дорожке"
]

# Глобальное хранилище
user_data_storage = {}

def get_user_data(user_id):
    if user_id not in user_data_storage:
        user_data_storage[user_id] = {
            'trainings': [],
            'current_training': None,
            'measurements_history': [],
            'custom_exercises': {
                'strength': [],
                'cardio': []
            },
            'statistics': {
                'total_trainings': 0,
                'total_exercises': 0,
                'total_strength_exercises': 0,
                'total_cardio_exercises': 0,
                'weekly_stats': {},
                'monthly_stats': {},
                'yearly_stats': {}
            }
        }
    return user_data_storage[user_id]

def get_user_exercises(user_id):
    """Получить все упражнения пользователя"""
    user_data = get_user_data(user_id)
    return {
        'strength': DEFAULT_STRENGTH_EXERCISES + user_data['custom_exercises']['strength'],
        'cardio': DEFAULT_CARDIO_EXERCISES + user_data['custom_exercises']['cardio']
    }

def generate_csv_export(user_id, period_type="current_month"):
    """Генерация CSV выгрузки данных"""
    user_data = get_user_data(user_id)
    
    if not user_data['trainings']:
        return None
    
    # Определяем период
    today = datetime.now()
    if period_type == "current_month":
        target_month = today.month
        target_year = today.year
        trainings = [t for t in user_data['trainings'] 
                    if datetime.strptime(t['date_start'], "%d.%m.%Y %H:%M").month == target_month
                    and datetime.strptime(t['date_start'], "%d.%m.%Y %H:%M").year == target_year]
    elif period_type == "all_time":
        trainings = user_data['trainings']
    else:
        trainings = user_data['trainings']
    
    if not trainings:
        return None
    
    # Собираем все уникальные даты тренировок
    dates = sorted(set(training['date_start'].split()[0] for training in trainings))
    
    # Собираем все уникальные упражнения
    all_exercises = {}
    for training in trainings:
        for exercise in training['exercises']:
            if 'is_cardio' not in exercise:  # Только силовые упражнения
                if exercise['name'] not in all_exercises:
                    all_exercises[exercise['name']] = {}
    
    # Заполняем данные по упражнениям и датам
    for training in trainings:
        training_date = training['date_start'].split()[0]
        for exercise in training['exercises']:
            if 'is_cardio' not in exercise:  # Только силовые упражнения
                exercise_name = exercise['name']
                if training_date not in all_exercises[exercise_name]:
                    all_exercises[exercise_name][training_date] = []
                
                for set_data in exercise.get('sets', []):
                    all_exercises[exercise_name][training_date].append(
                        f"{set_data['weight']}\t{set_data['reps']}"
                    )
    
    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовок таблицы
    header = ['Упражнение']
    for date in dates:
        header.extend([date, ''])  # Дата и пустая ячейка для пары вес/количество
    writer.writerow(header)
    
    # Второй заголовок с названиями столбцов
    subheader = ['']  # Пустая ячейка над "Упражнение"
    for date in dates:
        subheader.extend(['Вес', 'Количество'])
    writer.writerow(subheader)
    
    # Данные упражнений
    max_sets = 0
    for exercise_data in all_exercises.values():
        for date_data in exercise_data.values():
            max_sets = max(max_sets, len(date_data))
    
    # Для каждого упражнения создаем строки по количеству подходов
    for exercise_name, date_data in all_exercises.items():
        for set_index in range(max_sets):
            row = [exercise_name if set_index == 0 else '']  # Название упражнения только в первой строке
            
            for date in dates:
                if date in date_data and set_index < len(date_data[date]):
                    weight, reps = date_data[date][set_index].split('\t')
                    row.extend([weight, reps])
                else:
                    row.extend(['', ''])  # Пустые ячейки если подхода нет
            
            writer.writerow(row)
        # Добавляем пустую строку между упражнениями для читаемости
        writer.writerow([''] * (1 + len(dates) * 2))
    
    return output.getvalue()

def update_statistics(user_id, training):
    """Обновление статистики пользователя"""
    user_data = get_user_data(user_id)
    stats = user_data['statistics']
    
    # Подсчет упражнений по типам
    strength_count = 0
    cardio_count = 0
    
    for exercise in training['exercises']:
        if 'is_cardio' in exercise:
            cardio_count += 1
        else:
            strength_count += 1
    
    # Общая статистика
    stats['total_trainings'] += 1
    stats['total_exercises'] += len(training['exercises'])
    stats['total_strength_exercises'] += strength_count
    stats['total_cardio_exercises'] += cardio_count
    
    # Статистика по датам
    training_date = datetime.strptime(training['date_start'], "%d.%m.%Y %H:%M")
    week_key = training_date.strftime("%Y-%W")
    month_key = training_date.strftime("%Y-%m")
    year_key = training_date.strftime("%Y")
    
    # Недельная статистика
    if week_key not in stats['weekly_stats']:
        stats['weekly_stats'][week_key] = {
            'trainings': 0, 
            'exercises': 0,
            'strength_exercises': 0,
            'cardio_exercises': 0,
            'period_name': f"Неделя {training_date.strftime('%W')} ({training_date.strftime('%d.%m')})"
        }
    stats['weekly_stats'][week_key]['trainings'] += 1
    stats['weekly_stats'][week_key]['exercises'] += len(training['exercises'])
    stats['weekly_stats'][week_key]['strength_exercises'] += strength_count
    stats['weekly_stats'][week_key]['cardio_exercises'] += cardio_count
    
    # Месячная статистика
    if month_key not in stats['monthly_stats']:
        stats['monthly_stats'][month_key] = {
            'trainings': 0, 
            'exercises': 0,
            'strength_exercises': 0,
            'cardio_exercises': 0,
            'period_name': f"{training_date.strftime('%B %Y')}"
        }
    stats['monthly_stats'][month_key]['trainings'] += 1
    stats['monthly_stats'][month_key]['exercises'] += len(training['exercises'])
    stats['monthly_stats'][month_key]['strength_exercises'] += strength_count
    stats['monthly_stats'][month_key]['cardio_exercises'] += cardio_count
    
    # Годовая статистика
    if year_key not in stats['yearly_stats']:
        stats['yearly_stats'][year_key] = {
            'trainings': 0, 
            'exercises': 0,
            'strength_exercises': 0,
            'cardio_exercises': 0,
            'period_name': f"{training_date.strftime('%Y')} год"
        }
    stats['yearly_stats'][year_key]['trainings'] += 1
    stats['yearly_stats'][year_key]['exercises'] += len(training['exercises'])
    stats['yearly_stats'][year_key]['strength_exercises'] += strength_count
    stats['yearly_stats'][year_key]['cardio_exercises'] += cardio_count

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало работы с ботом"""
    user = update.message.from_user
    
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

async def start_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало тренировки"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    # Создаем новую тренировку
    current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    user_data['current_training'] = {
        'date_start': current_date,
        'exercises': [],
        'comment': '',
        'measurements': ''
    }
    
    await update.message.reply_text(
        f"🎯 Отлично стартуем! Сегодня {current_date}\n\n"
        "📏 Перед началом тренировки введите ваши замеры:\n"
        "(например: вес 65кг, талия 70см, бедра 95см)\n"
        "Или напишите 'пропустить' чтобы продолжить без замеров",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_MEASUREMENTS

async def save_measurements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение замеров и переход к тренировке"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    measurements = update.message.text
    
    if measurements.lower() != 'пропустить':
        user_data['current_training']['measurements'] = measurements
        # Сохраняем замеры в историю
        user_data['measurements_history'].append({
            'date': datetime.now().strftime("%d.%m.%Y %H:%M"),
            'measurements': measurements
        })
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        "✅ Замеры сохранены! Выберите тип упражнения:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return TRAINING

async def show_strength_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать силовые упражнения в виде кнопок"""
    user_id = update.message.from_user.id
    exercises = get_user_exercises(user_id)['strength']
    
    # Создаем клавиатуру с упражнениями
    keyboard = []
    for i in range(0, len(exercises), 2):
        row = exercises[i:i+2]
        keyboard.append(row)
    
    keyboard.append(['🔙 Назад к тренировке'])
    
    await update.message.reply_text(
        "💪 Выберите силовое упражнение:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_EXERCISE

async def handle_exercise_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора упражнения"""
    exercise_name = update.message.text
    user_id = update.message.from_user.id
    
    # Сохраняем выбранное упражнение
    context.user_data['current_exercise'] = {
        'name': exercise_name,
        'sets': []
    }
    
    await update.message.reply_text(
        f"💪 Выбрано: {exercise_name}\n\n"
        "Введите первый подход в формате:\n"
        "**Вес Количество_повторений**\n"
        "Например: 50 12\n"
        "Или: 50/12",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_SETS

async def handle_set_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода подхода"""
    user_id = update.message.from_user.id
    text = update.message.text
    
    # Парсим ввод: поддерживаем разные форматы
    text = text.replace(',', '.').replace('/', ' ').replace('х', ' ').replace('x', ' ')
    parts = text.split()
    
    if len(parts) >= 2:
        try:
            weight = float(parts[0])
            reps = int(parts[1])
            
            # Добавляем подход
            context.user_data['current_exercise']['sets'].append({
                'weight': weight,
                'reps': reps
            })
            
            sets_count = len(context.user_data['current_exercise']['sets'])
            
            # Формируем текст с текущими подходами
            sets_text = "✅ Текущие подходы:\n"
            for i, set_data in enumerate(context.user_data['current_exercise']['sets'], 1):
                sets_text += f"{i}. {set_data['weight']}кг × {set_data['reps']} повторений\n"
            
            keyboard = [['✅ Добавить еще подход', '💾 Сохранить упражнение'], ['❌ Отменить упражнение']]
            
            await update.message.reply_text(
                f"{sets_text}\n"
                f"Всего подходов: {sets_count}\n\n"
                "Выберите действие:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            
            return INPUT_SETS
            
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Неверный формат. Введите подход в формате:\n"
                "**Вес Количество_повторений**\n"
                "Например: 50 12\n"
                "Или: 50/12"
            )
            return INPUT_SETS
    else:
        await update.message.reply_text(
            "❌ Неверный формат. Введите два числа:\n"
            "**Вес Количество_повторений**\n"
            "Например: 50 12"
        )
        return INPUT_SETS

async def add_another_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление еще одного подхода"""
    await update.message.reply_text(
        "Введите следующий подход в формате:\n"
        "**Вес Количество_повторений**\n"
        "Например: 50 12\n"
        "Или: 50/12",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_SETS

async def save_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение упражнения с подходами"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if 'current_exercise' not in context.user_data or not context.user_data['current_exercise']['sets']:
        await update.message.reply_text("❌ Нет данных для сохранения.")
        return await show_strength_exercises(update, context)
    
    # Сохраняем упражнение
    exercise_data = context.user_data['current_exercise'].copy()
    exercise_data['timestamp'] = update.message.date.strftime("%H:%M")
    
    user_data['current_training']['exercises'].append(exercise_data)
    
    # Формируем текст сохраненного упражнения
    exercise_text = f"💪 {exercise_data['name']}:\n"
    for i, set_data in enumerate(exercise_data['sets'], 1):
        exercise_text += f"{i}. {set_data['weight']}кг × {set_data['reps']} повторений\n"
    
    # Очищаем временные данные
    context.user_data.pop('current_exercise', None)
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        f"✅ Упражнение сохранено!\n\n{exercise_text}\n"
        "Выберите следующее упражнение или завершите тренировку:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    return TRAINING

async def add_custom_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление пользовательского упражнения"""
    await update.message.reply_text(
        "Введите название нового силового упражнения:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_CUSTOM_EXERCISE

async def save_custom_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение пользовательского упражнения"""
    user_id = update.message.from_user.id
    exercise_name = update.message.text
    
    user_data = get_user_data(user_id)
    if exercise_name not in user_data['custom_exercises']['strength']:
        user_data['custom_exercises']['strength'].append(exercise_name)
    
    await update.message.reply_text(f"✅ Упражнение '{exercise_name}' добавлено в ваш список!")
    
    return await show_strength_exercises(update, context)

async def handle_cardio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кардио упражнений"""
    user_id = update.message.from_user.id
    exercises = get_user_exercises(user_id)['cardio']
    
    keyboard = [[exercise] for exercise in exercises]
    keyboard.append(['✏️ Добавить кардио упражнение'])
    keyboard.append(['🔙 Назад к тренировке'])
    
    await update.message.reply_text(
        "🏃 Выберите кардио упражнение:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CHOOSE_EXERCISE

async def handle_cardio_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора кардио упражнения"""
    exercise_name = update.message.text
    
    if exercise_name == '✏️ Добавить кардио упражнение':
        await update.message.reply_text(
            "Введите название нового кардио упражнения:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_CUSTOM_CARDIO
    
    context.user_data['current_exercise'] = {
        'name': exercise_name,
        'is_cardio': True
    }
    
    await update.message.reply_text(
        f"🏃 Выбрано: {exercise_name}\n\n"
        "Введите детали (например: '30 минут, 5 км' или 'интервалы: 10×1 мин'):",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_SETS

async def add_custom_cardio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление пользовательского кардио упражнения"""
    await update.message.reply_text(
        "Введите название нового кардио упражнения:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_CUSTOM_CARDIO

async def save_custom_cardio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение пользовательского кардио упражнения"""
    user_id = update.message.from_user.id
    exercise_name = update.message.text
    
    user_data = get_user_data(user_id)
    if exercise_name not in user_data['custom_exercises']['cardio']:
        user_data['custom_exercises']['cardio'].append(exercise_name)
    
    await update.message.reply_text(f"✅ Кардио упражнение '{exercise_name}' добавлено!")
    return await handle_cardio(update, context)

async def save_cardio_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение деталей кардио упражнения"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    details = update.message.text
    
    # Сохраняем кардио в тренировку
    exercise_data = context.user_data['current_exercise'].copy()
    exercise_data['details'] = details
    exercise_data['timestamp'] = update.message.date.strftime("%H:%M")
    
    user_data['current_training']['exercises'].append(exercise_data)
    
    context.user_data.pop('current_exercise', None)
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        f"✅ Кардио сохранено!\n{exercise_data['name']}: {details}\n\n"
        "Выберите следующее упражнение или завершите тренировку:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    return TRAINING

async def cancel_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущего упражнения"""
    exercise_name = context.user_data.get('current_exercise', {}).get('name', 'упражнение')
    context.user_data.pop('current_exercise', None)
    
    keyboard = [
        ['💪 Силовые упражнения', '🏃 Кардио'],
        ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
    ]
    
    await update.message.reply_text(
        f"❌ {exercise_name} - удалено",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    return TRAINING

async def finish_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершение тренировки"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['current_training']['exercises']:
        await update.message.reply_text(
            "❌ В тренировке нет упражнений. Добавьте хотя бы одно упражнение перед завершением.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Силовые упражнения', '🏃 Кардио'],
                ['✏️ Добавить свое упражнение', '🏁 Завершить тренировку']
            ], resize_keyboard=True)
        )
        return TRAINING
    
    await update.message.reply_text(
        "💬 Хотите добавить комментарий к тренировке?\n"
        "(например: 'Отличное самочувствие, увеличил веса')\n"
        "Или напишите 'пропустить'",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_COMMENT

async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение комментария и завершение тренировки"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    comment = update.message.text
    
    if comment.lower() != 'пропустить':
        user_data['current_training']['comment'] = comment
    
    # Сохраняем тренировку в историю
    user_data['trainings'].append(user_data['current_training'])
    
    # Обновляем статистику
    update_statistics(user_id, user_data['current_training'])
    
    # Формируем УПРОЩЕННЫЙ отчет о тренировке
    training = user_data['current_training']
    
    # Создаем форматированный отчет
    report = "🏆 Тренировка завершена 🏆\n\n"
    report += f"📅 Дата: {training['date_start']}\n\n"
    
    if training['measurements'] and training['measurements'] != 'пропустить':
        report += f"📏 Замеры: {training['measurements']}\n\n"
    
    report += "💪 Выполненные упражнения:\n\n"
    
    total_exercises = len(training['exercises'])
    strength_count = 0
    cardio_count = 0
    
    for i, exercise in enumerate(training['exercises'], 1):
        if 'is_cardio' in exercise:
            cardio_count += 1
            report += f"🏃 {i}. {exercise['name']}\n"
            report += f"   Детали: {exercise['details']}\n"
            report += f"   Время: {exercise['timestamp']}\n\n"
        else:
            strength_count += 1
            report += f"💪 {i}. {exercise['name']}\n"
            for j, set_data in enumerate(exercise['sets'], 1):
                report += f"   {j}. {set_data['weight']}кг × {set_data['reps']}\n"
            report += f"   Время: {exercise['timestamp']}\n\n"
    
    report += f"📊 Всего упражнений: {total_exercises}\n"
    report += f"• Силовых: {strength_count}\n"
    report += f"• Кардио: {cardio_count}\n"
    
    if training['comment'] and training['comment'] != 'пропустить':
        report += f"\n💬 Комментарий: {training['comment']}\n"
    
    # Очищаем текущую тренировку
    user_data['current_training'] = None
    context.user_data.clear()
    
    await update.message.reply_text(
        report,
        reply_markup=ReplyKeyboardMarkup([
            ['💪 Начать тренировку', '📊 История тренировок'],
            ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
            ['📤 Выгрузка данных', '❓ Помощь']
        ], resize_keyboard=True)
    )
    return MAIN_MENU

async def show_measurements_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать историю замеров"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['measurements_history']:
        await update.message.reply_text(
            "📏 У вас пока нет сохраненных замеров.\n"
            "Замеры сохраняются автоматически при начале тренировки.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
        return MAIN_MENU
    
    measurements_text = "📏 История ваших замеров:\n\n"
    
    for i, measurement in enumerate(user_data['measurements_history'][-10:], 1):  # Последние 10 замеров
        measurements_text += f"📅 {measurement['date']}\n"
        measurements_text += f"   {measurement['measurements']}\n\n"
    
    await update.message.reply_text(
        measurements_text,
        reply_markup=ReplyKeyboardMarkup([
            ['💪 Начать тренировку', '📊 История тренировок'],
            ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
            ['📤 Выгрузка данных', '❓ Помощь']
        ], resize_keyboard=True)
    )
    return MAIN_MENU

async def show_statistics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню статистики"""
    keyboard = [
        ['📊 Общая статистика', '📅 Текущая неделя'],
        ['📅 Текущий месяц', '📅 Текущий год'],
        ['📋 Детальная статистика'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        "📈 Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return STATS_PERIOD

async def show_general_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать общую статистику"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    stats = user_data['statistics']
    stats_text = "📊 ВАША СТАТИСТИКА\n\n"
    stats_text += "🏆 ОБЩАЯ СТАТИСТИКА:\n"
    stats_text += f"• Тренировок: {stats['total_trainings']}\n"
    stats_text += f"• Упражнений: {stats['total_exercises']}\n"
    stats_text += f"• Силовых упражнений: {stats['total_strength_exercises']}\n"
    stats_text += f"• Кардио упражнений: {stats['total_cardio_exercises']}\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Детальная статистика'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_PERIOD

async def show_training_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать историю тренировок"""
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['trainings']:
        await update.message.reply_text("📝 У вас пока нет завершенных тренировок.")
        return MAIN_MENU
    
    history_text = "📊 Последние тренировки:\n\n"
    for i, training in enumerate(user_data['trainings'][-5:], 1):
        history_text += f"🏋️ Тренировка #{len(user_data['trainings']) - 5 + i}\n"
        history_text += f"📅 {training['date_start']}\n"
        history_text += f"Упражнений: {len(training['exercises'])}\n"
        
        if training['comment'] and training['comment'] != 'пропустить':
            history_text += f"💬 {training['comment']}\n"
        
        history_text += "------\n"
    
    await update.message.reply_text(history_text)
    return MAIN_MENU

async def show_my_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать все упражнения пользователя"""
    user_id = update.message.from_user.id
    exercises = get_user_exercises(user_id)
    
    exercises_text = "📝 Ваши упражнения:\n\n"
    exercises_text += "💪 Силовые:\n"
    for ex in exercises['strength']:
        exercises_text += f"• {ex}\n"
    
    exercises_text += "\n🏃 Кардио:\n"
    for ex in exercises['cardio']:
        exercises_text += f"• {ex}\n"
    
    await update.message.reply_text(exercises_text)
    return MAIN_MENU

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Помощь"""
    help_text = """
🤖 **Фитнес-трекер - помощь**

💪 **Силовые упражнения:**
1. Выберите упражнение из списка
2. Добавляйте подходы в формате: "Вес Повторения"
3. Пример: "50 12" (50кг на 12 повторений)
4. Или: "50/12", "50,12"

🏃 **Кардио упражнения:**
1. Выберите кардио из списка
2. Введите детали (время, дистанция и т.д.)

✏️ **Добавление упражнений:**
- Новые упражнения сохраняются в ваш список

📊 **История тренировок** - просмотр прошлых тренировок
📈 **Статистика** - общая статистика за неделю/месяц/год
📏 **Мои замеры** - история всех ваших замеров
📤 **Выгрузка данных** - экспорт в CSV для Google Sheets
    """
    
    await update.message.reply_text(help_text)
    return MAIN_MENU

async def show_export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню выгрузки данных"""
    keyboard = [
        ['📅 Текущий месяц', '📅 Все время'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        "📤 Выберите период для выгрузки данных:\n\n"
        "Данные будут выгружены в формате CSV, который можно скопировать в Google Sheets",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return EXPORT_MENU

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выгрузка данных в CSV"""
    user_id = update.message.from_user.id
    period_type = update.message.text
    
    if period_type == '📅 Текущий месяц':
        export_type = "current_month"
        period_name = "текущий месяц"
    else:
        export_type = "all_time"
        period_name = "все время"
    
    csv_data = generate_csv_export(user_id, export_type)
    
    if not csv_data:
        await update.message.reply_text(
            f"❌ Нет данных для выгрузки за {period_name}.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
        return MAIN_MENU
    
    # Отправляем CSV как текстовое сообщение
    await update.message.reply_text(
        f"📊 Выгрузка данных за {period_name}:\n\n"
        "📋 **Как использовать:**\n"
        "1. Скопируйте текст ниже\n"
        "2. Откройте Google Sheets\n"
        "3. Вставьте скопированный текст\n"
        "4. Данные автоматически форматируются в таблицу\n\n"
        "📎 Формат: Упражнение | Дата | Вес | Количество повторений",
        reply_markup=ReplyKeyboardMarkup([
            ['💪 Начать тренировку', '📊 История тренировок'],
            ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
            ['📤 Выгрузка данных', '❓ Помощь']
        ], resize_keyboard=True)
    )
    
    # Отправляем сам CSV
    await update.message.reply_text(
        f"```csv\n{csv_data}\n```",
        parse_mode='MarkdownV2'
    )
    
    return MAIN_MENU

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка главного меню"""
    text = update.message.text
    
    if text == '💪 Начать тренировку':
        return await start_training(update, context)
    elif text == '📊 История тренировок':
        return await show_training_history(update, context)
    elif text == '📝 Мои упражнения':
        return await show_my_exercises(update, context)
    elif text == '📈 Статистика':
        return await show_statistics_menu(update, context)
    elif text == '📏 Мои замеры':
        return await show_measurements_history(update, context)
    elif text == '📤 Выгрузка данных':
        return await show_export_menu(update, context)
    elif text == '❓ Помощь':
        return await help_command(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки меню")
        return MAIN_MENU

def main():
    """Запуск бота"""
    TOKEN = "8384190310:AAEoICi82t_exSBCYwI1a22NvoXUxU_ATeY"
    
    application = Application.builder().token(TOKEN).build()
    
    # Настройка ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
            ],
            INPUT_MEASUREMENTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_measurements),
            ],
            TRAINING: [
                MessageHandler(filters.Regex('^💪 Силовые упражнения$'), show_strength_exercises),
                MessageHandler(filters.Regex('^🏃 Кардио$'), handle_cardio),
                MessageHandler(filters.Regex('^✏️ Добавить свое упражнение$'), add_custom_exercise),
                MessageHandler(filters.Regex('^🏁 Завершить тренировку$'), finish_training),
            ],
            CHOOSE_EXERCISE: [
                MessageHandler(filters.Regex('^🔙 Назад к тренировке$'), save_measurements),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_exercise_selection),
            ],
            INPUT_SETS: [
                MessageHandler(filters.Regex('^✅ Добавить еще подход$'), add_another_set),
                MessageHandler(filters.Regex('^💾 Сохранить упражнение$'), save_exercise),
                MessageHandler(filters.Regex('^❌ Отменить упражнение$'), cancel_exercise),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_input),
            ],
            ADD_CUSTOM_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_exercise),
            ],
            ADD_CUSTOM_CARDIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_cardio),
            ],
            INPUT_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment),
            ],
            STATS_PERIOD: [
                MessageHandler(filters.Regex('^📊 Общая статистика$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущая неделя$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущий месяц$'), show_general_statistics),
                MessageHandler(filters.Regex('^📅 Текущий год$'), show_general_statistics),
                MessageHandler(filters.Regex('^📋 Детальная статистика$'), show_general_statistics),
                MessageHandler(filters.Regex('^🔙 Главное меню$'), start),
            ],
            EXPORT_MENU: [
                MessageHandler(filters.Regex('^📅 Текущий месяц$'), export_data),
                MessageHandler(filters.Regex('^📅 Все время$'), export_data),
                MessageHandler(filters.Regex('^🔙 Главное меню$'), start),
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    application.add_handler(conv_handler)
    
    print("Бот запускается...")
    application.run_polling()

if __name__ == '__main__':
    main()