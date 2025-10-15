# executor.py - Безопасное выполнение команд с логированием

import subprocess
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Список потенциально опасных команд и паттернов
DANGEROUS_PATTERNS = [
    'rm -rf /',
    'rm -rf /*', 
    'dd if=',
    'mkfs',
    'fdisk',
    ':(){',  
    ':()',
    'sudo rm',
    'chmod 777 /',
    '> /dev/sd',
    'format',
    'deltree'
]

def run_command(cmd: str, timeout: int = 60) -> Tuple[int, str, str]:
    """
    Безопасно выполняет bash команду с проверкой на опасные паттерны.
    
    Args:
        cmd: Команда для выполнения
        timeout: Максимальное время выполнения в секундах
        
    Returns:
        Tuple[int, str, str]: (return_code, stdout, stderr)
    """
    logger.info(f"Попытка выполнения команды: {cmd}")
    
    # Проверка на опасные команды
    if is_dangerous_command(cmd):
        error_msg = f"Команда '{cmd}' заблокирована по соображениям безопасности"
        logger.warning(error_msg)
        return 1, "", error_msg
    
    try:
        logger.debug(f"Выполнение команды с timeout={timeout}s")
        completed = subprocess.run(
            cmd, 
            shell=True, 
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )
        
        logger.info(f"Команда выполнена с кодом возврата: {completed.returncode}")
        if completed.stdout:
            logger.debug(f"STDOUT: {completed.stdout[:200]}...")
        if completed.stderr:
            logger.debug(f"STDERR: {completed.stderr[:200]}...")
            
        return completed.returncode, completed.stdout, completed.stderr
        
    except subprocess.TimeoutExpired:
        error_msg = f"Команда '{cmd}' превысила лимит времени выполнения ({timeout}s)"
        logger.error(error_msg)
        return 1, "", error_msg
        
    except Exception as e:
        error_msg = f"Ошибка выполнения команды '{cmd}': {e}"
        logger.error(error_msg)
        return 1, "", error_msg

def is_dangerous_command(cmd: str) -> bool:
    """
    Проверяет команду на наличие потенциально опасных паттернов.
    
    Args:
        cmd: Команда для проверки
        
    Returns:
        bool: True если команда опасная, False в противном случае
    """
    cmd_lower = cmd.lower().strip()
    
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            logger.warning(f"Обнаружен опасный паттерн '{pattern}' в команде: {cmd}")
            return True
    
    return False