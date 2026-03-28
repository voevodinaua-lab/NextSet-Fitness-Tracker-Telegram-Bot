import os

# Функции которые пытаемся импортировать в main.py
required_functions = {
    'handlers_training': [
        'handle_measurements_choice', 'save_measurements', 'show_strength_exercises', 
        'show_cardio_exercises', 'choose_exercise_type', 'finish_training', 
        'handle_training_menu_fallback', 'handle_strength_exercise_selection', 
        'handle_set_input', 'handle_cardio_exercise_selection', 
        'handle_cardio_type_selection', 'handle_cardio_min_meters_input', 
        'handle_cardio_km_h_input', 'add_custom_exercise_from_training', 
        'save_new_exercise_from_training', 'handle_finish_confirmation', 
        'add_another_set', 'save_exercise', 'cancel_exercise'
    ],
    'handlers_common': [
        'start', 'start_from_button', 'handle_unknown_message', 'handle_main_menu', 
        'handle_clear_data_choice', 'handle_clear_data_confirmation'
    ],
    'handlers_exercises': [
        'choose_exercise_type_mgmt', 'show_delete_exercise_menu', 
        'add_custom_exercise_mgmt', 'save_new_strength_exercise_mgmt', 
        'save_new_cardio_exercise_mgmt', 'delete_exercise_handler'
    ],
    'handlers_statistics': [
        'show_general_statistics', 'show_weekly_stats', 'show_monthly_stats', 
        'show_yearly_stats', 'show_exercise_stats'
    ],
    'handlers_measurements': [
        'show_measurements_history'
    ],
    'handlers_export': [
        'export_data'
    ]
}

def check_module_functions(module_name, function_list):
    """Проверить какие функции есть в модуле"""
    filename = f"{module_name}.py"
    
    if not os.path.exists(filename):
        print(f"❌ Файл {filename} не существует!")
        return []
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    found_functions = []
    missing_functions = []
    
    for func in function_list:
        if f'def {func}' in content or f'async def {func}' in content:
            found_functions.append(func)
        else:
            missing_functions.append(func)
    
    print(f"\n📁 {module_name}.py:")
    print(f"✅ Найдено: {len(found_functions)}/{len(function_list)}")
    for func in found_functions:
        print(f"   ✓ {func}")
    
    if missing_functions:
        print(f"❌ Отсутствуют: {len(missing_functions)}")
        for func in missing_functions:
            print(f"   ✗ {func}")
    
    return found_functions, missing_functions

print("🔍 ПРОВЕРКА ВСЕХ ИМПОРТОВ...")
print("=" * 50)

all_found = {}
all_missing = {}

for module, functions in required_functions.items():
    found, missing = check_module_functions(module, functions)
    all_found[module] = found
    all_missing[module] = missing

print("\n" + "=" * 50)
print("📊 ИТОГО:")
total_required = sum(len(funcs) for funcs in required_functions.values())
total_found = sum(len(funcs) for funcs in all_found.values())
total_missing = sum(len(funcs) for funcs in all_missing.values())

print(f"Всего функций требуется: {total_required}")
print(f"Найдено: {total_found}")
print(f"Отсутствует: {total_missing}")

if total_missing > 0:
    print("\n🚨 РЕКОМЕНДАЦИИ:")
    for module, missing in all_missing.items():
        if missing:
            print(f"В {module}.py отсутствуют: {', '.join(missing)}")
