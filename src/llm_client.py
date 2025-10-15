# llm_client.py — клиент для генерации команд через LLM

import requests
import re
import logging
from config import settings

logger = logging.getLogger(__name__)

API_URL = "http://localhost:11434/v1/chat/completions"

def generate_command(prompt: str) -> dict:
    """
    Отправляет запрос к локальному серверу Ollama с моделью Saiga Mistral Nemo 12B.
    Возвращает словарь {"command": <команда>, "explanation": <текст>}.
    """
    logger.info(f"Получен запрос: {prompt}")
    
    system_prompt = """Ты — AI ассистент для Linux систем. Пользователь описывает задачу на естественном языке, а ты должен предложить соответствующую bash команду.

Отвечай СТРОГО в формате:
Команда: <bash_команда>
Объяснение: <краткое объяснение на русском>

Примеры:
Пользователь: "Создать папку test"
Ты: "Команда: mkdir test
Объяснение: Создание директории с именем test"

Пользователь: "Показать скрытые файлы"
Ты: "Команда: ls -la  
Объяснение: Показ всех файлов включая скрытые с подробной информацией"

Отвечай только командой и объяснением, без дополнительного текста."""

    payload = {
        "model": settings.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": settings.temperature,
        "top_k": settings.top_k,
        "top_p": settings.top_p,
        "stream": False
    }

    try:
        logger.debug(f"Отправка запроса к LLM: {payload}")
        response = requests.post(
            API_URL, 
            json=payload, 
            timeout=settings.timeout + 5
        )
        response.raise_for_status()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        logger.info(f"Получен ответ от LLM: {content}")
        
        parsed = parse_response(content)
        logger.info(f"Разобранная команда: {parsed['command']}")
        
        return parsed
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка подключения к LLM: {e}")
        return {"command": "", "explanation": f"Ошибка подключения к LLM: {e}"}
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        return {"command": "", "explanation": f"Произошла ошибка: {e}"}

def parse_response(content: str) -> dict:
    """Парсит ответ модели и извлекает команду и объяснение."""
    logger.debug(f"Парсинг ответа: {content}")
    
    # Основной парсинг по ключевым словам
    command_match = re.search(r'(?:Команда:|Command:)\s*(.+?)(?:\n|$)', content, re.IGNORECASE)
    explanation_match = re.search(r'(?:Объяснение:|Explanation:)\s*(.+?)(?:\n|$)', content, re.IGNORECASE)
    
    if command_match:
        command = command_match.group(1).strip()
        explanation = explanation_match.group(1).strip() if explanation_match else ""
        
        # Убираем backticks если есть
        command = command.strip('`')
        
        # Проверяем валидность команды
        if is_valid_command(command):
            logger.debug(f"Успешно извлечена команда: {command}")
            return {"command": command, "explanation": explanation}
    
    # Fallback: попытка извлечь код в backticks
    code_match = re.search(r'```(?:bash|sh)?\n(.+?)\n```', content, re.DOTALL | re.IGNORECASE)
    if code_match:
        command = code_match.group(1).strip()
        if is_valid_command(command):
            logger.debug(f"Команда извлечена из блока кода: {command}")
            return {"command": command, "explanation": ""}
    
    # Fallback: первая строка, которая выглядит как команда
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith(('Команда:', 'Объяснение:', '#', '//')):
            if is_valid_command(line):
                logger.debug(f"Команда найдена в строке: {line}")
                return {"command": line, "explanation": ""}
    
    logger.warning(f"Не удалось извлечь команду из ответа: {content}")
    return {"command": "", "explanation": "Не удалось извлечь команду из ответа"}

def is_valid_command(command: str) -> bool:
    """Проверяет, является ли строка валидной bash командой."""
    command = command.strip()
    if not command:
        return False
    
    # Список известных команд Linux
    common_commands = [
        'ls', 'cd', 'pwd', 'mkdir', 'rmdir', 'rm', 'cp', 'mv', 'find', 'grep',
        'cat', 'less', 'more', 'head', 'tail', 'wc', 'sort', 'uniq', 'cut',
        'awk', 'sed', 'chmod', 'chown', 'ps', 'top', 'kill', 'jobs', 'nohup',
        'df', 'du', 'free', 'mount', 'umount', 'lsblk', 'fdisk', 'fsck',
        'tar', 'gzip', 'gunzip', 'zip', 'unzip', 'wget', 'curl', 'ssh', 'scp',
        'systemctl', 'service', 'crontab', 'at', 'history', 'alias', 'which',
        'whereis', 'locate', 'file', 'stat', 'ln', 'touch', 'date', 'cal',
        'whoami', 'id', 'groups', 'su', 'sudo', 'passwd', 'useradd', 'usermod',
        'userdel', 'groupadd', 'groupmod', 'groupdel', 'ping', 'traceroute',
        'netstat', 'ss', 'iptables', 'ufw', 'rsync', 'screen', 'tmux', 'nano',
        'vim', 'vi', 'emacs', 'git', 'docker', 'pip', 'python', 'node', 'npm'
    ]
    
    # Получаем первое слово команды
    first_word = command.split()[0]
    
    # Проверяем, начинается ли команда с известной утилиты
    if first_word in common_commands:
        return True
    
    # Проверяем относительные и абсолютные пути
    if first_word.startswith('./') or first_word.startswith('/'):
        return True
    
    logger.debug(f"Команда '{command}' не прошла валидацию")
    return False