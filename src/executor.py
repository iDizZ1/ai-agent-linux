# executor.py 

import subprocess
import logging
import os
from typing import Tuple, Optional, Dict, Any
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class CommandCategory(Enum):
    """Категории команд по уровню опасности"""
    SAFE = "safe"              # read-only команды
    WRITE = "write"            # команды изменяющие файлы
    DANGEROUS = "dangerous"    # потенциально опасные
    CRITICAL = "critical"      # критически опасные
    BUILTIN = "builtin"        # встроенные команды (cd, export, etc)


# Встроенные команды bash (не могут быть запущены через subprocess отдельно)
BUILTIN_COMMANDS = {
    'cd', 'export', 'alias', 'unalias', 'set', 'unset',
    'source', '.', 'history', 'pwd'
}


# Расширенный список опасных паттернов
DANGEROUS_PATTERNS = [
    'rm -rf /',
    'rm -rf /*',
    'rm -rf ~',
    'rm -rf *',
    'rm -r /',
    'dd if=',
    'mkfs',
    'fdisk',
    ':(){',          # fork bomb
    ':())',
    '> /dev/sd',
    'format',
    'deltree',
    'chmod -R 777 /',
    'chown -R',
    '> /dev/null &',
    'wget http',     # скачивание
    'curl http',
    '| sh',          # pipe в shell
    '| bash',
    '; rm',
    '&& rm',
    'shred',
    'kill -9',       # массовое убийство процессов
    'pkill',
    'shutdown',
    'reboot',
    'init 0',
    'init 6',
]
 

# Whitelist безопасных команд
SAFE_COMMANDS = {
    'ls', 'cat', 'less', 'more', 'head', 'tail', 'pwd', 'echo',
    'whoami', 'id', 'date', 'cal', 'which', 'whereis', 'locate',
    'find', 'grep', 'wc', 'sort', 'uniq', 'cut', 'awk', 'sed',
    'df', 'du', 'free', 'ps', 'top', 'history', 'file', 'stat',
    'lsof', 'netstat', 'ss', 'ifconfig', 'ip', 'ping', 'curl', 'wget'
}


class CommandExecutor:
    """Расширенный класс для выполнения команд с сохранением состояния"""

    def __init__(self, initial_cwd: str = None):
        """
        Инициализирует executor с начальной рабочей директорией
        
        Args:
            initial_cwd: Начальная рабочая директория. Если None - использует текущую.
        """
        self.current_directory = initial_cwd or os.getcwd()
        self.environment_vars: Dict[str, str] = {}
        self.command_history: list = []
        
        # Загружаем переменные окружения родительского процесса
        self.environment_vars.update(os.environ)
        
        logger.info(f"Инициализирован CommandExecutor с рабочей директорией: {self.current_directory}")

    def get_current_directory(self) -> str:
        """Возвращает текущую рабочую директорию"""
        return self.current_directory

    def set_current_directory(self, path: str) -> bool:
        """
        Установить новую рабочую директорию
        
        Args:
            path: Путь для перехода
            
        Returns:
            True если успешно, False если директория не существует
        """
        # Обработка специальных путей
        if path == '~':
            path = os.path.expanduser('~')
        elif path == '-':
            # Последняя директория (как в bash)
            return False  # Пока не реализуем
        elif path == '..':
            path = os.path.dirname(self.current_directory)
        elif path == '.':
            return True  # Остаёмся в текущей директории
        elif not os.path.isabs(path):
            # Относительный путь
            path = os.path.join(self.current_directory, path)

        # Нормализуем путь
        path = os.path.abspath(path)

        # Проверяем существование
        if not os.path.isdir(path):
            logger.warning(f"Директория не найдена: {path}")
            return False

        self.current_directory = path
        logger.info(f"Изменена рабочая директория на: {path}")
        return True

    def set_environment_var(self, key: str, value: str):
        """Установить переменную окружения"""
        self.environment_vars[key] = value
        logger.info(f"Установлена переменная окружения: {key}={value}")

    def get_environment_var(self, key: str, default: str = None) -> str:
        """Получить переменную окружения"""
        return self.environment_vars.get(key, default)


def categorize_command(cmd: str) -> CommandCategory:
    """
    Категоризирует команду по уровню опасности
    
    Args:
        cmd: Команда для анализа
        
    Returns:
        CommandCategory: Категория команды
    """
    cmd_lower = cmd.lower().strip()
    first_word = cmd_lower.split()[0] if cmd_lower.split() else ""

    # Встроенные команды
    if first_word in BUILTIN_COMMANDS:
        return CommandCategory.BUILTIN

    # Проверка на критически опасные паттерны
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in cmd_lower:
            return CommandCategory.CRITICAL

    # Безопасные команды (read-only)
    if first_word in SAFE_COMMANDS:
        return CommandCategory.SAFE

    # Команды изменяющие файлы
    write_commands = {'touch', 'mkdir', 'cp', 'mv', 'echo', 'tee', 'nano', 'vi', 'vim'}
    if first_word in write_commands:
        return CommandCategory.WRITE

    # Потенциально опасные
    dangerous_commands = {'rm', 'chmod', 'chown', 'kill', 'sudo', 'su', 'dd'}
    if first_word in dangerous_commands:
        return CommandCategory.DANGEROUS

    # По умолчанию - write
    return CommandCategory.WRITE


def is_dangerous_command(cmd: str) -> bool:
    """
    Проверяет команду на наличие опасных паттернов.
    Ранняя блокировка ДО запроса подтверждения
    
    Args:
        cmd: Команда для проверки
        
    Returns:
        bool: True если команда опасная
    """
    category = categorize_command(cmd)

    if category == CommandCategory.CRITICAL:
        logger.warning(f"🚨 КРИТИЧЕСКИ ОПАСНАЯ команда заблокирована: {cmd}")
        return True

    if category == CommandCategory.DANGEROUS:
        logger.warning(f"⚠️ Потенциально опасная команда: {cmd}")
        # Для dangerous не блокируем полностью, но логируем
        return False

    return False


def is_direct_command(cmd: str) -> bool:
    """
    Определяет является ли строка прямой bash командой
    
    Args:
        cmd: Строка для проверки
        
    Returns:
        bool: True если это bash команда, False если это запрос на AI
    """
    cmd = cmd.strip()
    
    if not cmd:
        return False
    
    # 1. Проверка на русские слова (признак запроса на русском)
    russian_words = ['создать', 'найти', 'установить', 'удалить', 'показать',
                     'открыть', 'закрыть', 'переместить', 'скопировать', 'вывести',
                     'проверить', 'скачать', 'загрузить', 'архив', 'распакова',
                     'обновить', 'очистить', 'помощь', 'сделай', 'дай', 'дай мне']
    
    for word in russian_words:
        if word in cmd.lower():
            return False

    # 2. Проверка на известные команды
    known_commands = {
        'ls', 'cd', 'pwd', 'mkdir', 'touch', 'rm', 'cp', 'mv', 'cat', 'grep',
        'find', 'echo', 'chmod', 'chown', 'ps', 'kill', 'top', 'htop', 'df',
        'du', 'apt', 'pip', 'git', 'docker', 'python', 'node', 'java', 'make',
        'gcc', 'g++', 'tar', 'zip', 'unzip', 'gzip', 'gunzip', 'sed', 'awk',
        'sort', 'uniq', 'wc', 'head', 'tail', 'less', 'more', 'file', 'stat',
        'ln', 'ln -s', 'alias', 'export', 'source', 'bash', 'sh', 'exit',
        'clear', 'history', 'whois', 'ping', 'curl', 'wget', 'netstat', 'ss',
        'ifconfig', 'ip', 'sudo', 'su', 'whoami', 'id', 'groups', 'test', 'diff'
    }
    
    first_word = cmd.split()[0] if cmd.split() else ""
    if first_word not in known_commands:
        return False

    # 3. Проверка на опасные паттерны (даже для прямых команд)
    if any(pattern in cmd for pattern in DANGEROUS_PATTERNS):
        return False

    # 4. Базовая валидация синтаксиса
    # Проверяем на сбалансированность кавычек
    if cmd.count('"') % 2 != 0 or cmd.count("'") % 2 != 0:
        return False

    return True


def parse_cd_command(cmd: str) -> Optional[str]:
    """
    Парсит команду cd и возвращает путь
    
    Args:
        cmd: Команда вида 'cd /path' или 'cd ..'
        
    Returns:
        str: Путь для перехода, или None если неверный формат
    """
    cmd = cmd.strip()
    
    if not cmd.lower().startswith('cd '):
        return None
    
    path = cmd[3:].strip()
    
    if not path:
        return None
    
    return path


def run_command(cmd: str, executor: CommandExecutor = None, timeout: int = 60) -> Tuple[int, str, str]:
    """
    Безопасно выполняет bash команду с проверками и поддержкой состояния
    
    Args:
        cmd: Команда для выполнения
        executor: CommandExecutor для сохранения состояния (опционально)
        timeout: Максимальное время выполнения в секундах
        
    Returns:
        Tuple[int, str, str]: (return_code, stdout, stderr)
    """
    if executor is None:
        executor = CommandExecutor()

    category = categorize_command(cmd)
    logger.info(f"Попытка выполнения команды [{category.value}]: {cmd}")

    # Дополнительная проверка перед выполнением
    if is_dangerous_command(cmd):
        error_msg = "⛔ Команда заблокирована по соображениям безопасности"
        logger.error(error_msg)
        return 1, "", error_msg

    # Обработка встроенных команд
    if category == CommandCategory.BUILTIN:
        return handle_builtin_command(cmd, executor)

    # Обработка обычных команд
    try:
        logger.debug(f"Выполнение с timeout={timeout}s в директории {executor.current_directory}")

        completed = subprocess.run(
            cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            cwd=executor.current_directory,
            env=executor.environment_vars
        )

        logger.info(f"Команда выполнена [код {completed.returncode}]")
        
        if completed.stdout:
            logger.debug(f"STDOUT: {completed.stdout[:200]}...")
        if completed.stderr:
            logger.debug(f"STDERR: {completed.stderr[:200]}...")

        executor.command_history.append({
            'command': cmd,
            'returncode': completed.returncode,
            'timestamp': __import__('datetime').datetime.now().isoformat()
        })

        return completed.returncode, completed.stdout, completed.stderr

    except subprocess.TimeoutExpired:
        error_msg = f"⏱️ Превышен лимит времени выполнения ({timeout}s)"
        logger.error(error_msg)
        return 1, "", error_msg

    except Exception as e:
        error_msg = f"Ошибка выполнения: {e}"
        logger.error(error_msg, exc_info=True)
        return 1, "", error_msg


def handle_builtin_command(cmd: str, executor: CommandExecutor) -> Tuple[int, str, str]:
    """
    Обрабатывает встроенные bash команды
    
    Args:
        cmd: Встроенная команда
        executor: CommandExecutor для сохранения состояния
        
    Returns:
        Tuple[int, str, str]: (return_code, stdout, stderr)
    """
    cmd = cmd.strip()
    first_word = cmd.split()[0].lower() if cmd.split() else ""

    # pwd - показать текущую директорию
    if first_word == 'pwd':
        return 0, executor.current_directory + '\n', ""

    # cd - сменить директорию
    elif first_word == 'cd':
        path = parse_cd_command(cmd)
        
        if path is None:
            # cd без аргументов = перейти в домашнюю директорию
            path = os.path.expanduser('~')

        if executor.set_current_directory(path):
            logger.info(f"cd успешен: {executor.current_directory}")
            return 0, "", ""
        else:
            error_msg = f"-bash: cd: {path}: No such file or directory"
            logger.warning(error_msg)
            return 1, "", error_msg

    # export - установить переменную окружения
    elif first_word == 'export':
        # Парсим export VAR=value или export VAR
        rest = cmd[6:].strip()
        
        if '=' in rest:
            key, value = rest.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"\'')
            executor.set_environment_var(key, value)
            return 0, "", ""
        else:
            # export VAR - просто экспортируем из текущего окружения
            var_name = rest.strip()
            if var_name in os.environ:
                executor.set_environment_var(var_name, os.environ[var_name])
                return 0, "", ""
            else:
                return 0, "", ""

    # history - показать историю
    elif first_word == 'history':
        history_output = "\n".join(
            f"{i+1} {cmd['command']}" 
            for i, cmd in enumerate(executor.command_history[-20:])  # Последние 20 команд
        )
        return 0, history_output + "\n", ""

    # alias, unalias, set, unset - заглушки
    elif first_word in ['alias', 'unalias', 'set', 'unset']:
        logger.info(f"Команда {first_word} не полностью поддерживается")
        return 0, "", ""

    # source, . - выполнить файл (упрощённая реализация)
    elif first_word in ['source', '.']:
        logger.info(f"Команда {first_word} требует полного bash")
        return 1, "", "source/. требует полной сессии bash"

    return 1, "", f"Неизвестная встроенная команда: {first_word}"


# Глобальный executor для использования в interactive.py
_global_executor: Optional[CommandExecutor] = None


def get_global_executor() -> CommandExecutor:
    """Получить глобальный executor (ленивая инициализация)"""
    global _global_executor
    if _global_executor is None:
        _global_executor = CommandExecutor()
    return _global_executor


def set_global_executor_cwd(path: str) -> bool:
    """Установить рабочую директорию глобального executor"""
    executor = get_global_executor()
    return executor.set_current_directory(path)


def get_global_executor_cwd() -> str:
    """Получить рабочую директорию глобального executor"""
    executor = get_global_executor()
    return executor.current_directory
