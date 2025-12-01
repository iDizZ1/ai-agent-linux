import requests
import logging
import json
from typing import Dict, Optional, List

from config import settings

try:
    from rag_knowledge import get_rag_context

    HAS_RAG = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("RAG система инициализирована (текстовый поиск)")
except ImportError:
    HAS_RAG = False

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"


def generate_command(prompt: str, use_rag: bool = True) -> Dict:
    """
    Генерирует bash команду используя модель через ollama
    с поддержкой RAG контекста (текстовый поиск).

    Args:
        prompt: исходный промпт пользователя (может быть на русском)
        use_rag: использовать RAG контекст из базы знаний

    Returns:
        Dict с полями:
        - command: сгенерированная bash команда
        - explanation: объяснение на русском
    """
    logger.info(f"Генерирование команды: {prompt[:50]}...")

    enhanced_prompt = prompt
    if use_rag and HAS_RAG:
        try:
            rag_context = get_rag_context(prompt, top_k=3)
            if rag_context:
                enhanced_prompt = f"""{rag_context}

ПОЛЬЗОВАТЕЛЬСКИЙ ЗАПРОС: {prompt}

Используя примеры из базы знаний выше, сгенерируйте оптимальную bash команду:"""
                logger.info("RAG контекст добавлен к промпту")
        except Exception as e:
            logger.warning(f"Ошибка RAG: {e}")

    system_prompt = """Ты помощник для генерации bash команд.

ВАЖНО:
1. Отвечай ТОЛЬКО валидными bash командами
2. Если нужно несколько команд - разделяй их && или ;
3. Объясняй на русском что делает команда
4. Форматируй ответ как JSON:

{
"command": "команда или команды",
"explanation": "объяснение на русском"
}

БЕЗОПАСНОСТЬ:
- НИКОГДА не генерируй команды с rm -rf / или подобные
- Добавляй флаги для безопасности (-i для rm, --dry-run для опасных)
- Если команда потенциально опасна - предупреди пользователя"""

    try:
        logger.debug(f"Отправка запроса к ollama ({settings.model_name})...")

        # ИСПРАВЛЕНО: Удалены top_k и top_p - они не поддерживаются /api/generate!
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": settings.model_name,
                "prompt": f"{system_prompt}\n\n{enhanced_prompt}",  # system в prompt
                "stream": False,
                "options": {  # Все параметры в options!
                    "temperature": settings.temperature,
                    "top_k": settings.top_k,
                    "top_p": settings.top_p
                }
            },
            timeout=settings.timeout
        )

        response.raise_for_status()
        result = response.json()

        if "response" not in result:
            logger.error(f"Некорректный ответ от ollama: {result}")
            return _fallback_response(prompt)

        response_text = result["response"].strip()
        logger.debug(f"Ответ получен ({len(response_text)} символов)")

        parsed = _parse_model_response(response_text)
        if not parsed:
            logger.warning("Не удалось распарсить JSON ответ")
            return _fallback_response(prompt)

        logger.info(f"Команда сгенерирована: {parsed.get('command', '')[:50]}...")
        return parsed

    except requests.exceptions.ConnectionError:
        logger.error(f"Ошибка подключения к ollama на {OLLAMA_URL}")
        logger.error("   Убедитесь что Ollama запущена: ollama serve")
        return _fallback_response(prompt)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout при обращении к ollama (timeout={settings.timeout}s)")
        return _fallback_response(prompt)
    except Exception as e:
        logger.error(f"Ошибка при генерировании команды: {e}")
        return _fallback_response(prompt)


def _parse_model_response(response_text: str) -> Optional[Dict]:
    """
    Парсит JSON из ответа модели

    Args:
        response_text: текст ответа от модели

    Returns:
        Распарсенный JSON или None
    """
    import re

    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        logger.warning("JSON блок не найден в ответе")
        logger.debug(f"   Ответ: {response_text[:200]}")
        return None

    json_str = json_match.group(0)

    try:
        data = json.loads(json_str)

        if "command" not in data:
            logger.warning("В ответе нет поля 'command'")
            return None

        if "explanation" not in data:
            data["explanation"] = ""

        logger.debug(f"JSON распарсен успешно")
        return data

    except json.JSONDecodeError as e:
        logger.warning(f"Ошибка при парсинге JSON: {e}")
        logger.debug(f"   Попытка парсить: {json_str[:100]}")
        return None


def _fallback_response(prompt: str) -> Dict:
    """Возвращает fallback ответ если модель не доступна"""
    return {
        "command": "echo 'Model not available'",
        "explanation": "Model failed to process request. Check Ollama connection.",
        "error": True
    }


def test_ollama_connection() -> bool:
    """Проверяет подключение к ollama"""
    try:
        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=5
        )
        if response.status_code == 200:
            logger.info("Ollama доступна")
            return True
        else:
            logger.error(f"Ollama вернула статус {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка подключения: {e}")
        return False


def list_available_models() -> List[str]:
    """Получает список доступных моделей в ollama"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        response.raise_for_status()
        models = []
        for model in response.json().get("models", []):
            models.append(model.get("name", "unknown"))
        logger.info(f"Найдено {len(models)} моделей в ollama")
        return models
    except Exception as e:
        logger.error(f"Ошибка при получении списка моделей: {e}")
        return []


def get_command_from_prompt(prompt: str) -> Dict:
    """Альтернативное имя для generate_command"""
    return generate_command(prompt)