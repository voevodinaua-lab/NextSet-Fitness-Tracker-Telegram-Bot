import re
import ast

def extract_handlers_from_main():
    """Извлечь все обработчики из main.py"""
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Найти все MessageHandler вызовы
    handlers = []
    pattern = r'MessageHandler\([^)]+,\s*([^),]+)\)'
    matches = re.findall(pattern, content)
    
    for match in matches:
        if match not in handlers:
            handlers.append(match)
    
    return handlers

def extract_imports_from_main():
    """Извлечь все импорты из main.py"""
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Найти импорты
    imports = []
    
    # from ... import ...
    from_imports = re.findall(r'from\s+(\w+)\s+import\s+([^#\n]+)', content)
    for module, imported in from_imports:
        if imported.strip() == '*':
            imports.append(f"{module}.*")
        else:
            functions = [f.strip() for f in imported.split(',')]
            imports.extend([f"{module}.{func}" for func in functions])
    
    return imports

def check_handler_imports():
    """Проверить что все обработчики импортированы"""
    handlers = extract_handlers_from_main()
    imports = extract_imports_from_main()
    
    print("🔍 ПРОВЕРКА ОБРАБОТЧИКОВ:")
    print("=" * 50)
    
    missing = []
    found = []
    
    for handler in handlers:
        handler_clean = handler.strip()
        
        # Проверить разные варианты импорта
        is_imported = False
        
        # Вариант 1: Прямой импорт (from module import function)
        for imp in imports:
            if f".{handler_clean}" in imp:
                is_imported = True
                break
        
        # Вариант 2: Импорт через * (from module import *)
        if any(imp.endswith('.*') for imp in imports):
            is_imported = True
        
        # Вариант 3: Функция определена в main.py
        if f"def {handler_clean}" in open('main.py').read():
            is_imported = True
        
        if is_imported:
            found.append(handler_clean)
            print(f"✅ {handler_clean}")
        else:
            missing.append(handler_clean)
            print(f"❌ {handler_clean}")
    
    print("=" * 50)
    if missing:
        print(f"🚨 Отсутствуют импорты для: {', '.join(missing)}")
    else:
        print("🎉 Все обработчики корректно импортированы!")
    
    return missing

if __name__ == '__main__':
    check_handler_imports()
