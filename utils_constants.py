# Состояния бота для ConversationHandler
(
    # Основные состояния
    INACTIVE, MAIN_MENU,
    
    # 🏋️ Модуль тренировки
    START_TRAINING, INPUT_MEASUREMENTS_CHOICE, INPUT_MEASUREMENTS, TRAINING_MENU,
    STRENGTH_EXERCISES, CHOOSE_STRENGTH_EXERCISE, INPUT_SETS, SAVE_EXERCISE,
    CARDIO_EXERCISES, CHOOSE_CARDIO_EXERCISE, CARDIO_TYPE_SELECTION,
    INPUT_CARDIO_MIN_METERS, INPUT_CARDIO_KM_H, SAVE_CARDIO,
    ADD_EXERCISE_TYPE, INPUT_NEW_STRENGTH_EXERCISE, INPUT_NEW_CARDIO_EXERCISE, SAVE_NEW_EXERCISE,
    FINISH_TRAINING, CONFIRM_FINISH, EDIT_TRAINING, DELETE_EXERCISE_FROM_TRAINING,
    
    # 📝 Модуль управления упражнениями
    EXERCISES_MANAGEMENT, 
    ADD_EXERCISE_TYPE_MGMT, INPUT_NEW_STRENGTH_EXERCISE_MGMT, INPUT_NEW_CARDIO_EXERCISE_MGMT, SAVE_NEW_EXERCISE_MGMT,
    DELETE_EXERCISE_MENU, CHOOSE_EXERCISE_TO_DELETE, CONFIRM_DELETE,
    
    # 📊 Модуль статистики
    STATS_MENU, STATS_PERIOD_SELECTION, 
    SHOW_GENERAL_STATS, SHOW_WEEKLY_STATS, SHOW_MONTHLY_STATS, SHOW_YEARLY_STATS,
    EXERCISE_STATS_SELECTION, SHOW_EXERCISE_STATS,
    
    # 📏 Модуль замеров
    MEASUREMENTS_HISTORY,
    
    # 📤 Модуль экспорта
    EXPORT_MENU, SELECT_EXPORT_PERIOD, GENERATE_EXPORT, DOWNLOAD_EXPORT,
    
    # Очистка данных
    CLEAR_DATA_CONFIRM
) = range(45)

# Типы упражнений
STRENGTH_TYPE = 'strength'
CARDIO_TYPE = 'cardio'

# Стандартные упражнения
DEFAULT_STRENGTH_EXERCISES = [
    "Румынская тяга", "Ягодичный мостик", "Болгарский выпад",
    "Скручивания (пресс) в тренажере", "Воздушные выпады с отягощением на степе",
    "Отведения ноги назад в кроссовере", "Отведение ноги в сторону в кроссовере",
    "Скручивания и разгибание колен на полу"
]

DEFAULT_CARDIO_EXERCISES = ["Бег на дорожке"]

# Форматы кардио
CARDIO_FORMAT_MIN_METERS = 'min_meters'
CARDIO_FORMAT_KM_H = 'km_h'

# Периоды для статистики и экспорта
PERIOD_CURRENT_WEEK = 'current_week'
PERIOD_CURRENT_MONTH = 'current_month'
PERIOD_CURRENT_YEAR = 'current_year'
PERIOD_ALL_TIME = 'all_time'