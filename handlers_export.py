import logging
import io
import csv
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_user_trainings
from utils_constants import *

logger = logging.getLogger(__name__)

async def show_export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню выгрузки данных"""
    user_id = update.message.from_user.id
    trainings = get_user_trainings(user_id, limit=1)
    
    # Добавляем информацию о сохраненных данных
    stats_text = ""
    if trainings:
        stats_text = f"\n💾 Ваши данные сохранены в базе:\n• Тренировок: {len(trainings)}"
    
    keyboard = [
        ['📅 Текущий месяц', '📅 Все время'],
        ['🔙 Главное меню']
    ]
    
    await update.message.reply_text(
        f"📤 Выберите период для выгрузки данных:{stats_text}\n\n"
        "Данные будут выгружены в CSV файл, который можно скачать",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return EXPORT_MENU

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выгрузка данных в CSV файл"""
    user_id = update.message.from_user.id
    period_type = update.message.text

    if period_type == "📅 Текущий месяц":
        export_type = "current_month"
        period_name = "текущий месяц"
    elif period_type == "📅 Все время":
        export_type = "all_time"
        period_name = "все время"
    else:
        await update.message.reply_text(
            "❌ Используйте кнопки меню.",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["📅 Текущий месяц", "📅 Все время"],
                    ["🔙 Главное меню"],
                ],
                resize_keyboard=True,
            ),
        )
        return EXPORT_MENU
    
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
    
    # Создаем временный файл
    filename = f"training_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(csv_data)
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📊 Выгрузка данных за {period_name}\n\n"
                       "Файл содержит все ваши тренировки в формате CSV",
                reply_markup=ReplyKeyboardMarkup([
                    ['💪 Начать тренировку', '📊 История тренировок'],
                    ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                    ['📤 Выгрузка данных', '❓ Помощь']
                ], resize_keyboard=True)
            )
    except Exception as e:
        logger.error(f"❌ Ошибка при выгрузке данных: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при создании файла выгрузки.",
            reply_markup=ReplyKeyboardMarkup([
                ['💪 Начать тренировку', '📊 История тренировок'],
                ['📝 Мои упражнения', '📈 Статистика', '📏 Мои замеры'],
                ['📤 Выгрузка данных', '❓ Помощь']
            ], resize_keyboard=True)
        )
    finally:
        # Удаляем временный файл
        import os
        if os.path.exists(filename):
            os.remove(filename)
    
    return MAIN_MENU


async def handle_export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор периода выгрузки или возврат в главное меню."""
    text = (update.message.text or "").strip()

    if text == "🔙 Главное меню":
        from handlers_common import start

        return await start(update, context)
    if text in ("📅 Текущий месяц", "📅 Все время"):
        return await export_data(update, context)

    await update.message.reply_text(
        "❌ Пожалуйста, используйте кнопки меню.",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["📅 Текущий месяц", "📅 Все время"],
                ["🔙 Главное меню"],
            ],
            resize_keyboard=True,
        ),
    )
    return EXPORT_MENU


def generate_csv_export(user_id, period_type="all_time"):
    """Генерация CSV файла для скачивания"""
    if period_type == "current_month":
        # TODO: Реализовать фильтрацию по текущему месяцу
        trainings = get_user_trainings(user_id, limit=1000)
    else:
        trainings = get_user_trainings(user_id, limit=1000)
    
    if not trainings:
        return None
    
    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовок таблицы
    writer.writerow(['Дата тренировки', 'Тип упражнения', 'Название упражнения', 'Вес (кг)', 'Повторения', 'Время (мин)', 'Дистанция (м)', 'Скорость (км/ч)', 'Детали'])
    
    # Данные тренировок
    for training in trainings:
        training_date = training['date_start']
        
        for exercise in training['exercises']:
            if exercise.get('is_cardio'):
                # Кардио упражнение
                writer.writerow([
                    training_date,
                    'Кардио',
                    exercise['name'],
                    '',  # Вес
                    '',  # Повторения
                    exercise.get('time_minutes', ''),
                    exercise.get('distance_meters', ''),
                    exercise.get('speed_kmh', ''),
                    exercise.get('details', '')
                ])
            else:
                # Силовое упражнение
                for set_data in exercise.get('sets', []):
                    writer.writerow([
                        training_date,
                        'Силовое',
                        exercise['name'],
                        set_data['weight'],
                        set_data['reps'],
                        '',  # Время
                        '',  # Дистанция
                        '',  # Скорость
                        ''   # Детали
                    ])
    
    return output.getvalue()