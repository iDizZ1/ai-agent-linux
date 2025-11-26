# llm_client.py 

import requests
import re
import shlex
import logging
from config import settings

logger = logging.getLogger(__name__)

API_URL = "http://localhost:11434/v1/chat/completions"


# Whitelist утилит
COMMON_COMMANDS = {
    'ls', 'cd', 'pwd', 'mkdir', 'rmdir', 'rm', 'cp', 'mv', 'find', 'grep', 'cat',
    'less', 'more', 'head', 'tail', 'wc', 'sort', 'uniq', 'cut', 'awk', 'sed',
    'chmod', 'chown', 'ps', 'top', 'kill', 'jobs', 'df', 'du', 'free', 'tar',
    'gzip', 'gunzip', 'zip', 'unzip', 'wget', 'curl', 'ssh', 'scp', 'docker', 'git',
    'python', 'node', 'npm', 'pip', 'sudo', 'touch', 'echo', 'man', 'export', 'history'
}


def generate_command(prompt: str) -> dict:
    """
    Отправляет запрос к локальному серверу Ollama.
    Возвращает словарь с командой/командами.
    """
    default_response = {'command': '', 'explanation': 'Не удалось сгенерировать команду'}

    system_prompt = (
        "Ты — AI ассистент для Linux. Ты получаешь запрос пользователя и ДОЛЖЕН сгенерировать команды ДЛЯ ЭТОГО КОНКРЕТНОГО ЗАПРОСА.\n\n"
        "=== ФОРМАТЫ ОТВЕТОВ ===\n\n"
        "НЕСКОЛЬКО КОМАНД (если нужна последовательность):\n"
        "Команда: <cmd1>\n"
        "Команда: <cmd2>\n"
        "Команда: <cmd3>\n"
        "Объяснение: <общее объяснение>\n\n"
        "ОДНА КОМАНДА:\n"
        "Команда: <cmd>\n"
        "Объяснение: <объяснение>\n\n"
        "=== КРИТИЧЕСКИ ВАЖНО ===\n\n"
        "✅ ВСЕГДА используй ИМЕ­НА И АРГУМЕНТЫ ИЗ ТЕКУЩЕГО ЗАПРОСА!\n"
        "❌ НЕ генерируй команды из предыдущих запросов!\n"
        "✅ Команда ДОЛЖНА быть полной с ВСЕ АРГУМЕНТАМИ\n"
        "✅ Не используй markdown, только простой текст\n\n"
        "=== ПРИМЕРЫ ===\n\n"
        "Запрос: Создай директорию mynewdir\n"
        "Ответ:\n"
        "Команда: mkdir mynewdir\n"
        "Объяснение: Создание директории mynewdir\n\n"
        "Запрос: Создай папку data, перейди в нее, создай файл config.json\n"
        "Ответ:\n"
        "Команда: mkdir data\n"
        "Команда: cd data\n"
        "Команда: touch config.json\n"
        "Объяснение: Создание папки data, переход в нее и создание файла config.json\n\n"
        "=== ОСНОВНЫЕ ПРАВИЛА ===\n"
        "- Генерируй ТОЛЬКО валидные bash команды\n"
        "- ВСЕГДА используй параметры ИЗ ЗАПРОСА\n"
        "- Для многошаговых задач: создание → переход → работа\n"
        "- Не спрашивай подтверждение, просто генерируй"
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
        
        # Пробуем парсить как многошаговые команды
        result = parse_multiple_commands(content)
        
        # Если есть несколько команд - вернём как список
        if result.get('commands') and len(result['commands']) > 1:
            logger.info(f"✅ Найдено {len(result['commands'])} команд")
            return result
        
        # Если одна команда или не удалось - пробуем парсить как одиночную
        single_result = parse_response(content)
        if single_result.get('command'):
            logger.info(f"✅ Найдена одиночная команда: {single_result['command']}")
            return single_result
        
        # Если ничего не получилось - возвращаем результат из parse_multiple_commands
        if result['commands']:
            return result
            
        return default_response

    except requests.RequestException as e:
        logger.error(f"Ошибка запроса к LLM: {e}")
        return {'command': '', 'explanation': f'Ошибка подключения к AI: {e}'}
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return {'command': '', 'explanation': f'Ошибка генерации команды: {e}'}


def parse_multiple_commands(content: str) -> dict:
    """
    Парсит ответ LLM и извлекает все команды если их несколько.
    Возвращает {'commands': [...], 'explanations': [...]}
    или {'command': '...', 'explanation': '...'} если одна
    """
    if not content or not isinstance(content, str):
        return {'commands': [], 'explanations': []}

    # Удаляем ANSI-escape коды
    clean = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', content).strip()
    
    lines = clean.split('\n')
    commands = []
    explanations = []

    logger.debug(f"Парсинг {len(lines)} строк для многошаговых команд")

    for i, line in enumerate(lines):
        l = line.strip()
        
        if not l:
            continue

        # Извлекаем команды - ПОЛНУЮ строку после "Команда:"
        if l.lower().startswith(('команда:', 'command:')):
            # ✅ ИСПРАВЛЕНИЕ: берем ВСЮ строку после "Команда:" с аргументами
            candidate = l.split(':', 1)[1].strip('` \t')
            logger.debug(f"  [{i}] Извлечена полная строка: '{candidate}'")
            
            if is_valid_command(candidate):
                commands.append(candidate)
                logger.debug(f"  [{i}] ✅ Добавлена команда: {candidate}")
            else:
                logger.debug(f"  [{i}] ❌ Невалидная команда: {candidate}")

        # Извлекаем объяснения
        elif l.lower().startswith(('объяснение:', 'explanation:')):
            expl = l.split(':', 1)[1].strip()
            if expl:
                explanations.append(expl)
                logger.debug(f"  [{i}] Объяснение: {expl}")

    logger.info(f"✅ Парсинг завершён: найдено {len(commands)} команд")

    if commands:
        if len(commands) > 1:
            # Несколько команд - возвращаем как список
            logger.info(f"📋 Многошаговые команды: {commands}")
            return {
                'commands': commands,
                'explanations': explanations if explanations else [''] * len(commands)
            }
        else:
            # Одна команда - вернём в стандартном формате
            logger.info(f"🔧 Одиночная команда: {commands[0]}")
            return {
                'command': commands[0],
                'explanation': explanations[0] if explanations else ''
            }

    logger.warning(f"⚠️ Команды не найдены в ответе")
    return {'commands': [], 'explanations': []}


def parse_response(content: str) -> dict:
    """
    Парсит ответ LLM для одиночной команды.
    Всегда возвращает словарь с ожидаемыми ключами.
    """
    default_response = {'command': '', 'explanation': 'Не удалось обработать ответ AI'}

    if not content or not isinstance(content, str):
        logger.error(f"Пустой или некорректный ответ от LLM: {content}")
        return default_response

    try:
        # Удаляем ANSI-escape коды
        clean = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', content).strip()

        cmd = ''
        expl = ''

        logger.debug(f"Парсинг одиночной команды из: {clean[:100]}...")

        # 1. Извлекаем объяснение
        expl_match = re.search(
            r'(?:Объяснение:|Explanation:)\s*(.+?)(?:\n\n|\n(?:Команда:|Command:)|$)',
            clean, re.IGNORECASE | re.DOTALL
        )
        if expl_match:
            expl = expl_match.group(1).strip()[:200]
            logger.debug(f"  Объяснение: {expl[:50]}...")

        # 2. Пробуем извлечь команду разными способами

        # Способ 1: Стандартный формат "Команда: " - ✅ ИСПРАВЛЕНО
        # Берем ВСЮ строку до конца (включая аргументы)
        cmd_match = re.search(r'(?:Команда:|Command:)\s*(.+?)(?:\n|$)', clean, re.IGNORECASE)
        if cmd_match:
            candidate = cmd_match.group(1).strip()
            # Убираем только backticks если есть, но СОХРАНЯЕМ аргументы
            candidate = re.sub(r'^`|`$', '', candidate).strip()
            logger.debug(f"  [1] Попытка 1: '{candidate}'")
            
            if is_valid_command(candidate):
                cmd = candidate
                logger.debug(f"  ✅ Способ 1: {cmd}")
            else:
                logger.debug(f"  ❌ Способ 1 не подходит: {candidate}")

        # Способ 2: Markdown блок ```bash\n\n```
        if not cmd:
            bash_match = re.search(r'```(?:bash|sh)\s*\n(.+?)\n```', clean, re.DOTALL | re.IGNORECASE)
            if bash_match:
                candidate = bash_match.group(1).strip()
                # Берем только первую строку если многострочный блок
                candidate = candidate.split('\n')[0].strip()
                logger.debug(f"  [2] Попытка 2: '{candidate}'")
                
                if is_valid_command(candidate):
                    cmd = candidate
                    logger.debug(f"  ✅ Способ 2: {cmd}")

        # Способ 3: Просто в backticks
        if not cmd:
            tick_match = re.search(r'`([^`]+)`', clean)
            if tick_match:
                candidate = tick_match.group(1).strip()
                logger.debug(f"  [3] Попытка 3: '{candidate}'")
                
                if is_valid_command(candidate):
                    cmd = candidate
                    logger.debug(f"  ✅ Способ 3: {cmd}")

        # Способ 4: Первая валидная строка
        if not cmd:
            lines = clean.split('\n')
            for line_num, line in enumerate(lines):
                line = line.strip()
                if not line or line.startswith(('Команда:', 'Command:', 'Объяснение:',
                                               'Explanation:', '#', '//', '---')):
                    continue
                logger.debug(f"  [4] Попытка 4 (строка {line_num}): '{line}'")
                
                if is_valid_command(line):
                    cmd = line
                    logger.debug(f"  ✅ Способ 4: {cmd}")
                    break

        # Если команда не найдена
        if not cmd:
            logger.warning(f"❌ Не удалось извлечь команду из: {clean[:200]}...")
            return {'command': '', 'explanation': 'Не удалось извлечь валидную команду из ответа'}

        logger.info(f"✅ Финальная команда: '{cmd}'")
        return {'command': cmd, 'explanation': expl}

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга ответа LLM: {e}")
        return default_response


def is_valid_command(command: str) -> bool:
    """
    Проверяет, что команда начинается с известной утилиты или пути.
    ВАЖНО: Проверяет ПЕРВОЕ СЛОВО (до пробела), но не отбрасывает аргументы!
    """
    if not command or len(command) < 2:
        logger.debug(f"    is_valid_command: ❌ слишком короткая: '{command}'")
        return False

    try:
        # ✅ ИСПРАВЛЕНИЕ: используем shlex для правильного парсинга
        # но проверяем только первую часть
        parts = shlex.split(command)
    except Exception as e:
        logger.debug(f"    is_valid_command: ❌ ошибка shlex: {e}")
        return False

    if not parts:
        logger.debug(f"    is_valid_command: ❌ пусто после парсинга: '{command}'")
        return False

    tool = parts[0]

    # Относительный или абсолютный путь
    if tool.startswith('/') or tool.startswith('./') or tool.startswith('../'):
        logger.debug(f"    is_valid_command: ✅ путь: {tool}")
        return True

    # Чистое имя утилиты
    if tool in COMMON_COMMANDS:
        logger.debug(f"    is_valid_command: ✅ утилита: {tool}")
        return True

    logger.debug(f"    is_valid_command: ❌ неизвестная утилита: {tool}")
    return False
