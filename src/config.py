import logging
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Конфигурация AI Agent для генерации bash команд с RAG поддержкой"""
    
    # ========== LLM параметры ==========
    model_name: str = "qwen3:0.6b"
    temperature: float = 0.3
    top_k: int = 40
    top_p: float = 0.9
    timeout: int = 30
    
    # ========== RAG параметры ==========
    use_rag: bool = True
    kb_path: str = "bash_knowledge_base.md"
    text_search_top_k: int = 5
    
    # ========== Логирование ==========
    log_level: str = "INFO"
    log_file: str = "aiask.log"
    console_logging: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Создаем экземпляр
settings = Settings()

# Настройка логирования
def setup_logging():
    """Инициализирует систему логирования"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    os.makedirs("logs", exist_ok=True)
    
    handlers = [
        logging.FileHandler(f"logs/{settings.log_file}")
    ]
    
    if settings.console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        handlers.append(console_handler)
    
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format=log_format,
        handlers=handlers
    )

# Инициализируем логирование
setup_logging()
logger = logging.getLogger(__name__)

logger.info(f"Конфигурация загружена:")
logger.info(f" - Model: {settings.model_name}")
logger.info(f" - RAG: {'ВКЛЮЧЕНА' if settings.use_rag else 'ОТКЛЮЧЕНА'}")
logger.info(f" - Knowledge Base: {settings.kb_path}")
