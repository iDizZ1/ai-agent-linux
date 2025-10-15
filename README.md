# AI Assistant для управления Linux
🤖 Интеллектуальный ассистент для генерации и выполнения bash-команд на основе описания задач на естественном языке.

✨ Особенности
🧠 Использует локальную LLM модель IlyaGusev/saiga_nemo_12b

🔒 Безопасное выполнение с проверкой опасных команд

💬 Интерактивный и одноразовый режимы работы

📝 Подробное логирование всех операций

🚀 Быстрый старт
Требования
Python 3.11+

Ollama с загруженной моделью IlyaGusev/saiga_nemo_12b

8+ GB RAM

Установка Ollama и модели
bash
# Установка Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Запуск Ollama
ollama serve

# В другом терминале: загрузка модели
ollama pull IlyaGusev/saiga_nemo_12b
Запуск из исходников
bash
# Клонирование репозитория
git clone https://github.com/your-username/ai-assistant.git
cd ai-assistant

# Установка зависимостей
pip install -r requirements.txt

# Одиночный запрос
python src/aiask.py ask "создать папку test"

# Интерактивный режим
python src/aiask.py
Запуск в Docker
bash
# Сборка образа
docker build -t ai-assistant .

# Запуск интерактивного режима
docker run -it --rm \
  --network host \
  -v $(pwd)/logs:/app/logs \
  ai-assistant

# Одиночный запрос
docker run --rm \
  --network host \
  ai-assistant ask "показать процессы"
📖 Использование
Интерактивный режим
bash
$ python src/aiask.py
🤖 Запущен интерактивный режим AI-ассистента
💬 Введите 'exit' или 'quit' для выхода
📝 Введите 'help' для получения помощи
--------------------------------------------------
AIask> создать папку documents
🤖 Команда: mkdir documents
💡 Объяснение: Создание директории с именем documents
Выполнить? [y/N]: y
✅ Команда выполнена успешно
Одиночные запросы
bash
# Примеры использования
python src/aiask.py ask "показать свободное место на диске"
python src/aiask.py ask "найти все файлы .log в текущей папке"
python src/aiask.py ask "запустить nginx"
🔧 Конфигурация
Настройки находятся в src/config.py:

python
class Settings(BaseSettings):
    model_name: str = "IlyaGusev/saiga_nemo_12b"
    temperature: float = 0.3
    top_k: int = 40
    top_p: float = 0.9
    timeout: int = 30
    log_level: str = "INFO"
    log_file: str = "aiask.log"
🛡️ Безопасность
Встроенная защита от опасных команд:

rm -rf / - удаление корневой системы

dd if= - прямая запись на диск

:(){ :|:& };: - fork bombs

И другие потенциально разрушительные операции

📁 Структура проекта
text
ai-assistant/
├── src/
│   ├── aiask.py          # Точка входа
│   ├── config.py         # Конфигурация
│   ├── llm_client.py     # Клиент для LLM
│   ├── executor.py       # Выполнение команд
│   └── interactive.py    # Интерактивный режим
├── logs/                 # Файлы логов
├── tests/                # Тесты
├── Dockerfile            # Docker образ
├── requirements.txt      # Зависимости Python
└── README.md
🧪 Тестирование
bash
# Запуск тестов
pytest tests/

# Линтинг кода
black src/
flake8 src/
📊 Логирование
Логи сохраняются в файл logs/aiask.log и выводятся в консоль. Уровни логирования:

DEBUG - подробная отладочная информация

INFO - основные операции

WARNING - предупреждения о потенциальных проблемах

ERROR - ошибки выполнения

🤝 Разработка
Локальная разработка
bash
# Установка зависимостей разработки
pip install -r requirements.txt

# Запуск в режиме разработки
python -m src.aiask
Сборка Docker образа
bash
# Сборка
docker build -t ai-assistant:latest .

# Тестирование
docker run --rm ai-assistant ask "pwd"
📋 TODO
 Добавление истории команд в SQLite

 Визуализация через LangGraph

 Веб-интерфейс

 Поддержка плагинов

 Расширенная система безопасности

🐛 Известные проблемы
Модель может генерировать неточные команды для сложных задач

Требуется активное подключение к Ollama

Высокое потребление памяти (6-8 GB)

📄 Лицензия
MIT License - см. файл LICENSE

👥 Участники
@your-username - автор и сопровождающий

🙏 Благодарности
IlyaGusev за модель Saiga

Ollama за локальный LLM сервер

Сообществу Open Source за вклад в развитие
