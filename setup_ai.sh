#!/bin/bash

echo "=== Установка и запуск AI Agent в WSL ==="
echo ""

# 1. Установка Ollama
echo "[1/7] Устанавливаю Ollama..."
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Запуск Ollama в фоне (WSL без отдельного терминала)
echo "[2/7] Запускаю Ollama сервер в фоне..."
ollama serve &
OLLAMA_PID=$!
echo "Ollama PID: $OLLAMA_PID"
sleep 5  # Даем больше времени для запуска

# 3. Проверка запуска Ollama
echo "Проверяю запуск Ollama..."
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "⚠️  Ollama не отвечает, пробую перезапустить..."
    kill $OLLAMA_PID 2>/dev/null
    ollama serve &
    sleep 8
fi

# 4. Загрузка модели qwen3:0.6b
echo "[3/7] Загружаю модель qwen3:0.6b..."
ollama pull qwen3:0.6b

# 5. Установка необходимых пакетов для Python
echo "[5/7] Устанавливаю python3-venv..."
sudo apt update
sudo apt install -y python3-pip python3-venv python3-dev

# 6. Создание виртуального окружения
echo "[6/7] Создаю виртуальное окружение..."
python3 -m venv venv --without-pip

# Устанавливаем pip в виртуальное окружение
source venv/bin/activate
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python get-pip.py
rm get-pip.py

# 7. Установка зависимостей
echo "[7/7] Устанавливаю зависимости..."

pip install -r requirements.txt

# 8. Запуск AI Agent
echo ""
echo "=== Готово! AI Agent запущен ==="
echo "Модель: qwen3:0.6b"
echo "Ollama PID: $OLLAMA_PID"
echo ""
echo "Для остановки Ollama: kill $OLLAMA_PID"
echo ""

python src/aiask.py
