from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Fitness Bot is running!"

def run_bot():
    from fitness_bot import main
    main()

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем веб-сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)