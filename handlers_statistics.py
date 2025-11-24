import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_user_trainings, get_custom_exercises
from utils_constants import *

logger = logging.getLogger(__name__)

async def show_statistics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню статистики"""
    keyboard = [
        ['📊 Общая статистика', '📅 Текущая неделя'],
        ['📅 Текущий месяц', '📅 Текущий год'],
        ['📋 Статистика по упражнениям'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        "📈 Выберите тип статистики:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return STATS_MENU

async def show_general_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать общую статистику"""
    user_id = update.message.from_user.id
    trainings = get_user_trainings(user_id, limit=1000)  # Получаем все тренировки
    
    if not trainings:
        await update.message.reply_text(
            "📊 У вас пока нет данных для статистики.\n"
            "Завершите несколько тренировок, чтобы увидеть статистику.",
            reply_markup=ReplyKeyboardMarkup([
                ['📊 Общая статистика', '📅 Текущая неделя'],
                ['📅 Текущий месяц', '📅 Текущий год'],
                ['📋 Статистика по упражнениям'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return STATS_MENU
    
    # Вычисляем статистику
    total_trainings = len(trainings)
    total_exercises = 0
    total_strength_exercises = 0
    total_cardio_exercises = 0
    
    for training in trainings:
        total_exercises += len(training['exercises'])
        for exercise in training['exercises']:
            if exercise.get('is_cardio'):
                total_cardio_exercises += 1
            else:
                total_strength_exercises += 1
    
    stats_text = "📊 ВАША СТАТИСТИКА\n\n"
    stats_text += "🏆 ОБЩАЯ СТАТИСТИКА:\n"
    stats_text += f"• Тренировок: {total_trainings}\n"
    stats_text += f"• Упражнений: {total_exercises}\n"
    stats_text += f"• Силовых упражнений: {total_strength_exercises}\n"
    stats_text += f"• Кардио упражнений: {total_cardio_exercises}\n"
    
    # Статистика за текущую неделю
    week_stats = calculate_weekly_stats(trainings)
    if week_stats['trainings'] > 0:
        stats_text += f"\n📅 НА ЭТОЙ НЕДЕЛЕ:\n"
        stats_text += f"• Тренировок: {week_stats['trainings']}\n"
        stats_text += f"• Упражнений: {week_stats['exercises']}\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Статистика по упражнениям'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_MENU

async def show_weekly_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать статистику за текущую неделю"""
    user_id = update.message.from_user.id
    trainings = get_user_trainings(user_id, limit=1000)
    
    week_stats = calculate_weekly_stats(trainings)
    
    stats_text = "📅 СТАТИСТИКА ЗА ТЕКУЩУЮ НЕДЕЛЮ\n\n"
    
    if week_stats['trainings'] == 0:
        stats_text += "На этой неделе тренировок еще не было.\n"
        stats_text += "Самое время начать! 💪"
    else:
        stats_text += f"🏋️ Тренировок: {week_stats['trainings']}\n"
        stats_text += f"💪 Упражнений: {week_stats['exercises']}\n"
        stats_text += f"📈 Силовых: {week_stats['strength']}\n"
        stats_text += f"🏃 Кардио: {week_stats['cardio']}\n"
        
        if week_stats['trainings_list']:
            stats_text += f"\n📋 Тренировки этой недели:\n"
            for training in week_stats['trainings_list'][:5]:  # Показываем до 5 тренировок
                stats_text += f"• {training['date']}: {len(training['exercises'])} упражнений\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Статистика по упражнениям'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_MENU

async def show_monthly_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать статистику за текущий месяц"""
    user_id = update.message.from_user.id
    trainings = get_user_trainings(user_id, limit=1000)
    
    month_stats = calculate_monthly_stats(trainings)
    
    stats_text = "📅 СТАТИСТИКА ЗА ТЕКУЩИЙ МЕСЯЦ\n\n"
    
    if month_stats['trainings'] == 0:
        stats_text += "В этом месяце тренировок еще не было.\n"
        stats_text += "Самое время начать! 💪"
    else:
        stats_text += f"🏋️ Тренировок: {month_stats['trainings']}\n"
        stats_text += f"💪 Упражнений: {month_stats['exercises']}\n"
        stats_text += f"📈 Силовых: {month_stats['strength']}\n"
        stats_text += f"🏃 Кардио: {month_stats['cardio']}\n"
        
        # Самые популярные упражнения
        if month_stats['popular_exercises']:
            stats_text += f"\n🎯 Популярные упражнения:\n"
            for exercise, count in month_stats['popular_exercises'][:3]:  # Топ-3
                stats_text += f"• {exercise}: {count} раз\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Статистика по упражнениям'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_MENU

async def show_yearly_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать статистику за текущий год"""
    user_id = update.message.from_user.id
    trainings = get_user_trainings(user_id, limit=1000)
    
    year_stats = calculate_yearly_stats(trainings)
    
    stats_text = "📅 СТАТИСТИКА ЗА ТЕКУЩИЙ ГОД\n\n"
    
    if year_stats['trainings'] == 0:
        stats_text += "В этом году тренировок еще не было.\n"
        stats_text += "Самое время начать! 💪"
    else:
        stats_text += f"🏋️ Тренировок: {year_stats['trainings']}\n"
        stats_text += f"💪 Упражнений: {year_stats['exercises']}\n"
        stats_text += f"📈 Силовых: {year_stats['strength']}\n"
        stats_text += f"🏃 Кардио: {year_stats['cardio']}\n"
        
        # Статистика по месяцам
        if year_stats['monthly_stats']:
            stats_text += f"\n📊 По месяцам:\n"
            for month, count in year_stats['monthly_stats'].items():
                stats_text += f"• {month}: {count} тренировок\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Статистика по упражнениям'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_MENU

async def show_exercise_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать статистику по упражнениям"""
    user_id = update.message.from_user.id
    trainings = get_user_trainings(user_id, limit=1000)
    
    if not trainings:
        await update.message.reply_text(
            "📊 У вас пока нет данных для статистики по упражнениям.",
            reply_markup=ReplyKeyboardMarkup([
                ['📊 Общая статистика', '📅 Текущая неделя'],
                ['📅 Текущий месяц', '📅 Текущий год'],
                ['📋 Статистика по упражнениям'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return STATS_MENU
    
    # Собираем статистику по упражнениям
    exercise_stats = {}
    
    for training in trainings:
        for exercise in training['exercises']:
            name = exercise['name']
            if name not in exercise_stats:
                exercise_stats[name] = {
                    'count': 0,
                    'type': 'cardio' if exercise.get('is_cardio') else 'strength',
                    'max_weight': 0,
                    'total_reps': 0,
                    'total_sets': 0
                }
            
            exercise_stats[name]['count'] += 1
            
            if not exercise.get('is_cardio') and exercise.get('sets'):
                # Статистика для силовых упражнений
                weights = [s['weight'] for s in exercise['sets']]
                reps = [s['reps'] for s in exercise['sets']]
                
                exercise_stats[name]['max_weight'] = max(
                    exercise_stats[name]['max_weight'], 
                    max(weights) if weights else 0
                )
                exercise_stats[name]['total_reps'] += sum(reps)
                exercise_stats[name]['total_sets'] += len(exercise['sets'])
    
    if not exercise_stats:
        await update.message.reply_text(
            "❌ Нет данных по упражнениям.",
            reply_markup=ReplyKeyboardMarkup([
                ['📊 Общая статистика', '📅 Текущая неделя'],
                ['📅 Текущий месяц', '📅 Текущий год'],
                ['📋 Статистика по упражнениям'],
                ['🔙 Главное меню']
            ], resize_keyboard=True)
        )
        return STATS_MENU
    
    stats_text = "📊 СТАТИСТИКА ПО УПРАЖНЕНИЯМ\n\n"
    
    # Сортируем по популярности
    sorted_exercises = sorted(exercise_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    
    for exercise_name, stats in sorted_exercises[:10]:  # Показываем топ-10
        emoji = "🏃" if stats['type'] == 'cardio' else "💪"
        stats_text += f"{emoji} {exercise_name}\n"
        stats_text += f"   Выполнено: {stats['count']} раз\n"
        
        if stats['type'] == 'strength' and stats['max_weight'] > 0:
            stats_text += f"   Макс. вес: {stats['max_weight']}кг\n"
            if stats['total_sets'] > 0:
                avg_reps = stats['total_reps'] / stats['total_sets']
                stats_text += f"   Ср. повторений: {avg_reps:.1f}\n"
        
        stats_text += "\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=ReplyKeyboardMarkup([
            ['📊 Общая статистика', '📅 Текущая неделя'],
            ['📅 Текущий месяц', '📅 Текущий год'],
            ['📋 Статистика по упражнениям'],
            ['🔙 Главное меню']
        ], resize_keyboard=True)
    )
    return STATS_MENU

# Вспомогательные функции для расчетов статистики
def calculate_weekly_stats(trainings):
    """Рассчитать статистику за текущую неделю"""
    now = datetime.now()
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    
    weekly_trainings = []
    total_exercises = 0
    strength_count = 0
    cardio_count = 0
    
    for training in trainings:
        training_date = datetime.strptime(training['date_start'], "%d.%m.%Y %H:%M")
        if training_date >= start_of_week:
            weekly_trainings.append(training)
            total_exercises += len(training['exercises'])
            
            for exercise in training['exercises']:
                if exercise.get('is_cardio'):
                    cardio_count += 1
                else:
                    strength_count += 1
    
    return {
        'trainings': len(weekly_trainings),
        'exercises': total_exercises,
        'strength': strength_count,
        'cardio': cardio_count,
        'trainings_list': weekly_trainings
    }

def calculate_monthly_stats(trainings):
    """Рассчитать статистику за текущий месяц"""
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    monthly_trainings = []
    total_exercises = 0
    strength_count = 0
    cardio_count = 0
    exercise_counts = {}
    
    for training in trainings:
        training_date = datetime.strptime(training['date_start'], "%d.%m.%Y %H:%M")
        if training_date >= start_of_month:
            monthly_trainings.append(training)
            total_exercises += len(training['exercises'])
            
            for exercise in training['exercises']:
                # Считаем популярность упражнений
                name = exercise['name']
                exercise_counts[name] = exercise_counts.get(name, 0) + 1
                
                if exercise.get('is_cardio'):
                    cardio_count += 1
                else:
                    strength_count += 1
    
    # Сортируем упражнения по популярности
    popular_exercises = sorted(exercise_counts.items(), key=lambda x: x[1], reverse=True)
    
    return {
        'trainings': len(monthly_trainings),
        'exercises': total_exercises,
        'strength': strength_count,
        'cardio': cardio_count,
        'popular_exercises': popular_exercises
    }

def calculate_yearly_stats(trainings):
    """Рассчитать статистику за текущий год"""
    now = datetime.now()
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    yearly_trainings = []
    total_exercises = 0
    strength_count = 0
    cardio_count = 0
    monthly_stats = {}
    
    for training in trainings:
        training_date = datetime.strptime(training['date_start'], "%d.%m.%Y %H:%M")
        if training_date >= start_of_year:
            yearly_trainings.append(training)
            total_exercises += len(training['exercises'])
            
            # Статистика по месяцам
            month_key = training_date.strftime("%B")  # Название месяца
            monthly_stats[month_key] = monthly_stats.get(month_key, 0) + 1
            
            for exercise in training['exercises']:
                if exercise.get('is_cardio'):
                    cardio_count += 1
                else:
                    strength_count += 1
    
    return {
        'trainings': len(yearly_trainings),
        'exercises': total_exercises,
        'strength': strength_count,
        'cardio': cardio_count,
        'monthly_stats': monthly_stats
    }