# config.py - Конфигурация с логированием (ИСПРАВЛЕНО для вывода в консоль)

import logging
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_name: str = "llama3.2:3b"
    temperature: float = 0.3
    top_k: int = 40
    top_p: float = 0.9
    timeout: int = 30
    log_level: str = "INFO"
    log_file: str = "aiask.log"
    console_logging: bool = True  # ИЗМЕНЕНО: теперь True по умолчанию

settings = Settings()

# Настройка логирования
def setup_logging():
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Создаем директорию для логов если её нет
    os.makedirs("logs", exist_ok=True)
    
    # Настраиваем обработчики
    handlers = [
        logging.FileHandler(f"logs/{settings.log_file}")
    ]
    
    # Консольный вывод ВСЕГДА включён
    if settings.console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)  # В консоль только WARNING и выше
        handlers.append(console_handler)
    
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format=log_format,
        handlers=handlers
    )

# Инициализируем логирование
setup_logging()
logger = logging.getLogger(__name__)
