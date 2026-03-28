"""Общие утилиты без зависимостей от Telegram/openpyxl (импорт безопасен из любого handler)."""
import json
from datetime import datetime


def parse_training_datetime(date_str: str) -> datetime:
    """Разбор даты начала тренировки из формата БД/бота."""
    return datetime.strptime((date_str or "").strip(), "%d.%m.%Y %H:%M")


def normalize_exercise_sets(sets):
    """Подходы силового упражнения: list[dict] или JSON-строка из БД."""
    if sets is None:
        return []
    if isinstance(sets, list):
        return sets
    if isinstance(sets, str):
        try:
            data = json.loads(sets)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
    return []
