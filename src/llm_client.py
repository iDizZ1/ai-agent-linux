# llm_client.py - Клиент для генерации команд 

import requests
import re
import shlex
import logging
from config import settings

logger = logging.getLogger(__name__)
API_URL = "http://localhost:11434/v1/chat/completions"

# Регулярные шаблоны для парсинга
COMMAND_PATTERNS = [
    # Стандартный формат: "Команда: <команда>"
    r'(?:Команда:|Command:)\s*`?(.+?)`?(?:\n|$)',

    # Markdown блоки с bash/sh
    r'```(?:bash|sh)\s*\n(.+?)\n```',

    # Просто команда в backticks
    r'`([^`]+)`',

    # Первая непустая строка (fallback)
    r'^(.+)$'
]

# Whitelist утилит
COMMON_COMMANDS = {
    'ls', 'cd', 'pwd', 'mkdir', 'rmdir', 'rm', 'cp', 'mv', 'find', 'grep', 'cat',
    'less', 'more', 'head', 'tail', 'wc', 'sort', 'uniq', 'cut', 'awk', 'sed',
    'chmod', 'chown', 'ps', 'top', 'kill', 'jobs', 'df', 'du', 'free', 'tar',
    'gzip', 'gunzip', 'zip', 'unzip', 'wget', 'curl', 'ssh', 'scp', 'docker', 'git',
    'python', 'node', 'npm', 'pip', 'sudo', 'touch', 'echo', 'man'
}


def generate_command(prompt: str) -> dict:
    """
    Отправляет запрос к локальному серверу Ollama.
    Гарантированно возвращает словарь с ожидаемыми ключами.
    """
    # Гарантируем, что функция всегда возвращает dict
    default_response = {'command': '', 'explanation': 'Не удалось сгенерировать команду'}

    system_prompt = (
        "Ты — AI ассистент для Linux. Ты получаешь контекст системы и запрос пользователя.\n"
        "Формат ответа:\n"
        "Команда: <bash_команда>\n"
        "Объяснение: <короткое объяснение на русском>\n\n"
        "Правила:\n"
        "- Генерируй только валидные bash команды\n"
        "- Учитывай текущую рабочую директорию из контекста\n"
        "- Учитывай уровень пользователя (новичку - простые команды)\n"
        "- Избегай опасных операций\n"
        "- Не используй markdown, только простой текст"
    )

    payload = {
        'model': settings.model_name,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt}
        ],
        'temperature': settings.temperature,
        'top_k': settings.top_k,
        'top_p': settings.top_p,
        'stream': False
    }

    try:
        resp = requests.post(API_URL, json=payload, timeout=settings.timeout)
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        logger.info(f"LLM ответ: {content}")
        return parse_response(content)
    except requests.RequestException as e:
        logger.error(f"Ошибка запроса к LLM: {e}")
        return {'command': '', 'explanation': f'Ошибка подключения к AI: {e}'}
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return {'command': '', 'explanation': f'Ошибка генерации команды: {e}'}


def parse_response(content: str) -> dict:
    """
    Парсит ответ LLM с улучшенной обработкой ошибок.
    Всегда возвращает словарь с ожидаемыми ключами.
    """
    # Гарантируем возврат словаря даже при ошибках
    default_response = {'command': '', 'explanation': 'Не удалось обработать ответ AI'}

    if not content or not isinstance(content, str):
        logger.error(f"Пустой или некорректный ответ от LLM: {content}")
        return default_response

    try:
        # Удаляем ANSI-escape коды
        clean = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', content).strip()

        cmd = ''
        expl = ''

        logger.debug(f"Парсинг контента: {clean[:100]}...")

        # 1. Извлекаем объяснение
        expl_match = re.search(r'(?:Объяснение:|Explanation:)\s*(.+?)(?:\n\n|\n(?:Команда:|Command:)|$)',
                               clean, re.IGNORECASE | re.DOTALL)
        if expl_match:
            expl = expl_match.group(1).strip()[:200]
            logger.debug(f"Найдено объяснение: {expl[:50]}...")

        # 2. Пробуем извлечь команду разными способами

        # Способ 1: Стандартный формат "Команда: <cmd>"
        cmd_match = re.search(r'(?:Команда:|Command:)\s*(.+?)(?:\n|$)', clean, re.IGNORECASE)
        if cmd_match:
            candidate = cmd_match.group(1).strip()
            # Убираем backticks и пробелы
            candidate = candidate.strip('`').strip()
            if is_valid_command(candidate):
                cmd = candidate
                logger.debug(f"Извлечена команда (способ 1): {cmd}")

        # Способ 2: Markdown блок ```bash\n<cmd>\n```
        if not cmd:
            bash_match = re.search(r'```(?:bash|sh)\s*\n(.+?)\n```', clean, re.DOTALL | re.IGNORECASE)
            if bash_match:
                candidate = bash_match.group(1).strip()
                # Берём только первую строку если многострочный блок
                candidate = candidate.split('\n')[0].strip()
                if is_valid_command(candidate):
                    cmd = candidate
                    logger.debug(f"Извлечена команда (способ 2): {cmd}")

        # Способ 3: Просто в backticks `<cmd>`
        if not cmd:
            tick_match = re.search(r'`([^`]+)`', clean)
            if tick_match:
                candidate = tick_match.group(1).strip()
                if is_valid_command(candidate):
                    cmd = candidate
                    logger.debug(f"Извлечена команда (способ 3): {cmd}")

        # Способ 4: Первая валидная строка
        if not cmd:
            lines = clean.split('\n')
            for line in lines:
                line = line.strip()
                # Пропускаем заголовки и пустые строки
                if not line or line.startswith(('Команда:', 'Command:', 'Объяснение:',
                                                'Explanation:', '#', '//', '---')):
                    continue
                if is_valid_command(line):
                    cmd = line
                    logger.debug(f"Извлечена команда (способ 4): {cmd}")
                    break

        # Если команда не найдена
        if not cmd:
            logger.warning(f"Не удалось извлечь команду из: {clean[:200]}...")
            return {'command': '', 'explanation': 'Не удалось извлечь валидную команду из ответа'}

        return {'command': cmd, 'explanation': expl}

    except Exception as e:
        logger.error(f"Ошибка парсинга ответа LLM: {e}")
        return default_response


def is_valid_command(command: str) -> bool:
    """
    Проверяет, что команда начинается с известной утилиты или пути.
    """
    if not command or len(command) < 2:
        return False

    try:
        parts = shlex.split(command)
    except Exception:
        # Если не удалось распарсить - считаем невалидной
        return False

    if not parts:
        return False

    tool = parts[0]

    # Относительный или абсолютный путь
    if tool.startswith('/') or tool.startswith('./'):
        return True

    # Чистое имя утилиты
    if tool in COMMON_COMMANDS:
        return True

    logger.debug(f"Невалидная команда: {command}")
    return False