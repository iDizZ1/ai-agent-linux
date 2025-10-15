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
```bash
# Установка Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Запуск Ollama
ollama serve

# Загрузка модели
ollama pull IlyaGusev/saiga_nemo_12b
```

Запуск из исходников
```bash
# Клонирование репозитория
git clone https://github.com/iDizZ1/ai-agent-linux
cd ai-agent-linux

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Одиночный запрос
python src/aiask.py ask "создать папку test"

# Интерактивный режим
python src/aiask.py
```

📖 Использование
Интерактивный режим
```bash
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
```


