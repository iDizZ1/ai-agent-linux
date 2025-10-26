# executor.py - Безопасное выполнение команд 

import subprocess
import logging
from typing import Tuple, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class CommandCategory(Enum):
    """Категории команд по уровню опасности"""
    SAFE = "safe"          # read-only команды
    WRITE = "write"        # команды изменяющие файлы
    DANGEROUS = "dangerous" # потенциально опасные
    CRITICAL = "critical"   # критически опасные

# Расширенный список опасных паттернов (ЭТАП 2.1)
DANGEROUS_PATTERNS = [
    'rm -rf /',
    'rm -rf /*',
    'rm -rf ~',
    'rm -rf *',
    'rm -r /',
    'dd if=',
    'mkfs',
    'fdisk',
    ':(){',       # fork bomb
    ':()',
    '> /dev/sd',
    'format',
    'deltree',
    'chmod -R 777 /',
    'chown -R',
    '> /dev/null &',
    'wget http',  # скачивание
    'curl http',
    '| sh',       # pipe в shell
    '| bash',
    '; rm',
    '&& rm',
    'shred',
    'kill -9',    # массовое убийство процессов
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
    'df', 'du', 'free', 'ps', 'top', 'history'
}

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
    
    # Проверка на критически опасные паттерны
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in cmd_lower:
            return CommandCategory.CRITICAL
    
    # Безопасные команды (read-only)
    if first_word in SAFE_COMMANDS:
        return CommandCategory.SAFE
    
    # Команды изменяющие файлы
    write_commands = {'touch', 'mkdir', 'cp', 'mv', 'echo', 'tee'}
    if first_word in write_commands:
        return CommandCategory.WRITE
    
    # Потенциально опасные
    dangerous_commands = {'rm', 'chmod', 'chown', 'kill', 'sudo', 'su'}
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

def run_command(cmd: str, timeout: int = 60) -> Tuple[int, str, str]:
    """
    Безопасно выполняет bash команду с проверками.
    
    Args:
        cmd: Команда для выполнения
        timeout: Максимальное время выполнения в секундах
        
    Returns:
        Tuple[int, str, str]: (return_code, stdout, stderr)
    """
    category = categorize_command(cmd)
    logger.info(f"Попытка выполнения команды [{category.value}]: {cmd}")
    
    # Дополнительная проверка перед выполнением
    if is_dangerous_command(cmd):
        error_msg = "⛔ Команда заблокирована по соображениям безопасности"
        logger.error(error_msg)
        return 1, "", error_msg
    
    try:
        logger.debug(f"Выполнение с timeout={timeout}s")
        completed = subprocess.run(
            cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )
        
        logger.info(f"Команда выполнена [код {completed.returncode}]")
        
        if completed.stdout:
            logger.debug(f"STDOUT: {completed.stdout[:200]}...")
        if completed.stderr:
            logger.debug(f"STDERR: {completed.stderr[:200]}...")
            
        return completed.returncode, completed.stdout, completed.stderr
        
    except subprocess.TimeoutExpired:
        error_msg = f"⏱️ Превышен лимит времени выполнения ({timeout}s)"
        logger.error(error_msg)
        return 1, "", error_msg
        
    except Exception as e:
        error_msg = f"Ошибка выполнения: {e}"
        logger.error(error_msg, exc_info=True)
        return 1, "", error_msg