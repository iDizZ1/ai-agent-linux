import os
import json
import logging
import re
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    """Запись в базе знаний"""
    command: str              
    description: str          
    category: str            
    keywords: List[str]      
    score: float = 0.0       


# Расширенный словарь синонимов для русского
SYNONYM_MAP = {
    # ===== ФАЙЛЫ И ДИРЕКТОРИИ =====
    "создай": ["mkdir", "touch", "create", "make", "new"],
    "создать": ["mkdir", "touch", "create", "make", "new"],
    "сделай": ["mkdir", "touch", "create", "make"],
    "сделать": ["mkdir", "touch", "create", "make"],
    "новый": ["mkdir", "touch", "create", "new"],
    "новая": ["mkdir", "touch", "create"],
    "новые": ["mkdir", "touch", "create"],
    
    "папка": ["mkdir", "directory", "folder", "dir", "path"],
    "директория": ["mkdir", "directory", "folder", "cd", "path"],
    "директории": ["mkdir", "directory", "folder", "cd"],
    "проект": ["mkdir", "project", "dir"],
    
    "файл": ["touch", "echo", "cat", "nano", "vim", "create", "file"],
    "файла": ["touch", "echo", "cat", "nano", "vim"],
    "файле": ["cat", "nano", "vim", "less", "more"],
    "файлы": ["touch", "echo", "cat", "nano", "find"],
    
    "удали": ["rm", "remove", "delete", "rmdir"],
    "удалить": ["rm", "remove", "delete"],
    "удаление": ["rm", "remove", "delete"],
    "удалены": ["rm", "remove", "delete"],
    
    "скопируй": ["cp", "copy"],
    "скопировать": ["cp", "copy"],
    "копирование": ["cp", "copy"],
    
    "переименуй": ["mv", "rename"],
    "переименовать": ["mv", "rename"],
    "переместить": ["mv", "move"],
    "переместит": ["mv", "move"],
    "переместить": ["mv", "move"],
    
    # ===== ПОИСК И ФИЛЬТРАЦИЯ =====
    "ищи": ["find", "grep", "search", "locate"],
    "найди": ["find", "grep", "search", "locate"],
    "найти": ["find", "grep", "search", "locate"],
    "поиск": ["find", "grep", "search", "locate"],
    "поиск": ["find", "grep", "search"],
    "ищет": ["grep", "find", "search"],
    "ищите": ["find", "grep", "search"],
    
    "фильтр": ["grep", "filter", "awk", "sed"],
    "фильтровать": ["grep", "filter", "awk"],
    "фильтрацию": ["grep", "filter"],
    
    # ===== ПРОСМОТР И РЕДАКТИРОВАНИЕ =====
    "просмотри": ["cat", "less", "more", "head", "tail", "view"],
    "просмотреть": ["cat", "less", "more", "head", "tail"],
    "содержимое": ["cat", "less", "more", "head", "tail"],
    
    "редактируй": ["nano", "vim", "vi", "echo", "cat", "edit"],
    "редактировать": ["nano", "vim", "vi", "echo", "cat"],
    "редактирование": ["nano", "vim", "vi", "edit"],
    
    "напиши": ["echo", "cat", "nano", "vim"],
    "написать": ["echo", "cat", "nano", "vim"],
    "добавь": ["echo", "cat", "nano", "append"],
    "добавить": ["echo", "cat", "nano"],
    
    "первые": ["head", "first"],
    "последние": ["tail", "last"],
    "строки": ["head", "tail", "grep", "wc"],
    
    # ===== ТЕКСТОВАЯ ОБРАБОТКА =====
    "замени": ["sed", "replace", "substitute"],
    "заменить": ["sed", "replace", "substitute"],
    "замена": ["sed", "replace"],
    
    "сортировка": ["sort", "order"],
    "сортируй": ["sort", "order"],
    "сортировать": ["sort", "order"],
    "отсортировать": ["sort", "order"],
    
    "подсчет": ["wc", "count"],
    "подсчитай": ["wc", "count"],
    "считай": ["wc", "count"],
    "строк": ["wc", "lines"],
    
    # ===== ПЕРЕХОДЫ И НАВИГАЦИЯ =====
    "перейди": ["cd", "move", "navigate"],
    "перейти": ["cd", "move", "navigate"],
    "переход": ["cd", "move"],
    "вверх": ["cd ..", "cd ..", "up"],
    "домой": ["cd ~", "cd ~", "home"],
    "корень": ["cd /", "root"],
    "текущая": ["pwd", "current"],
    "директория": ["pwd", "cd", "directory"],
    "путь": ["pwd", "cd", "path"],
    
    # ===== ПРОЦЕССЫ И МОНИТОРИНГ =====
    "процесс": ["ps", "top", "htop", "kill", "process"],
    "процессы": ["ps", "top", "htop", "kill"],
    "процесса": ["ps", "top", "kill"],
    
    "убей": ["kill", "pkill"],
    "убить": ["kill", "pkill"],
    "останови": ["kill", "pkill", "stop"],
    "остановить": ["kill", "pkill", "stop"],
    "остановка": ["kill", "stop"],
    
    "монитор": ["top", "htop", "ps", "watch"],
    "мониторинг": ["top", "htop", "watch"],
    "производительность": ["top", "htop", "vmstat"],
    
    # ===== СИСТЕМА И ИНФОРМАЦИЯ =====
    "пользователь": ["whoami", "id", "users", "who"],
    "память": ["free", "vmstat", "top"],
    "диск": ["df", "du", "lsblk", "disk"],
    "размер": ["du", "df", "wc", "size"],
    "место": ["df", "du", "space"],
    "информация": ["uname", "lsb_release", "hostnamectl"],
    "система": ["uname", "lsb_release", "system"],
    
    # ===== АРХИВИРОВАНИЕ =====
    "архив": ["tar", "zip", "gzip", "archive"],
    "архивировать": ["tar", "zip", "gzip", "compress"],
    "упаковать": ["tar", "zip", "gzip", "compress"],
    "упакуй": ["tar", "zip", "gzip"],
    "распаковать": ["tar", "unzip", "gunzip"],
    "распакуй": ["tar", "unzip", "gunzip"],
    "сжать": ["gzip", "bzip2", "compress"],
    "сжатие": ["gzip", "tar", "zip"],
    
    # ===== PYTHON =====
    "python": ["python", "py", "python3", "pip"],
    "питон": ["python", "py", "python3"],
    "исполни": ["python", "execute", "run"],
    "исполнить": ["python", "execute", "run"],
    "запусти": ["python", "execute", "run"],
    "запустить": ["python", "execute", "run"],
    
    "виртуальное": ["venv", "virtualenv"],
    "окружение": ["venv", "virtualenv", "environment"],
    "окружения": ["venv", "virtualenv"],
    
    "pip": ["pip", "install", "package"],
    "пакет": ["pip", "install", "package"],
    "пакеты": ["pip", "install"],
    "зависимость": ["pip", "install"],
    
    "тесты": ["pytest", "test", "testing"],
    "тест": ["pytest", "test"],
    "форматирование": ["black", "pylint", "flake8"],
    
    # ===== GIT =====
    "репозиторий": ["git", "repo"],
    "коммит": ["git commit"],
    "ветка": ["git branch"],
    "клон": ["git clone"],
    "пуш": ["git push"],
    "пул": ["git pull"],
    
    # ===== DOCKER =====
    "контейнер": ["docker", "container"],
    "образ": ["docker", "image"],
    "запусти контейнер": ["docker run"],
}


# Матрица важности категорий
CATEGORY_IMPORTANCE = {
    "файлы": {"Работа с файлами": 1.0, "Создание": 1.0},
    "папка": {"Работа с директориями": 1.0, "Файлы": 0.8},
    "python": {"Python": 1.0, "Скрипты": 0.9},
    "поиск": {"Поиск": 1.0, "Работа с файлами": 0.9},
    "процесс": {"Проверка системы": 1.0, "Управление": 0.8},
    "архив": {"Архивация": 1.0},
}


class BashKnowledgeBase:
    """
    Оптимизированная база знаний для русского языка
    БЕЗ embeddings - использует только улучшенный текстовый поиск
    """
    
    def __init__(self, kb_path: str = "bash_knowledge_base.md"):
        """
        Args:
            kb_path: путь к файлу с базой знаний
        """
        self.kb_path = kb_path
        self.entries: List[KnowledgeEntry] = []
        
        logger.info("🚀 Инициализация BashKnowledgeBase (БЕЗ embeddings)")
        logger.info("✅ Используется оптимизированный текстовый поиск для русского")
        
        self._load_knowledge_base()
    
    def _load_knowledge_base(self):
        """Загружает базу знаний из markdown файла"""
        if not os.path.exists(self.kb_path):
            logger.warning(f"⚠️  База знаний не найдена: {self.kb_path}")
            return
        
        logger.info(f"📖 Загрузка базы знаний из {self.kb_path}")
        
        with open(self.kb_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        current_category = "General"
        
        for line in content.split('\n'):
            line = line.strip()
            
            if line.startswith('## Категория:'):
                current_category = line.replace('## Категория:', '').strip()
                logger.debug(f"📂 Категория: {current_category}")
            
            elif line.startswith('- `'):
                match = re.match(r'^- `([^`]+)`\s*-\s*(.+)$', line)
                if match:
                    command = match.group(1).strip()
                    description = match.group(2).strip()
                    
                    keywords = self._extract_keywords(command, description)
                    
                    entry = KnowledgeEntry(
                        command=command,
                        description=description,
                        category=current_category,
                        keywords=keywords
                    )
                    self.entries.append(entry)
        
        logger.info(f"✅ Загружено {len(self.entries)} команд в базу знаний")
    
    def _extract_keywords(self, command: str, description: str) -> List[str]:
        """Извлекает ключевые слова с синонимами"""
        keywords = set()
        
        # 1. Из команды
        cmd_parts = re.findall(r'\b[\w-]+\b', command.lower())
        keywords.update(cmd_parts[:4])
        
        # 2. Из описания на русском
        russian_words = re.findall(r'\b[а-яё]+\b', description.lower())
        keywords.update(russian_words[:3])
        
        # 3. Добавляем синонимы из описания
        for word in russian_words:
            if word in SYNONYM_MAP:
                synonyms = SYNONYM_MAP[word]
                keywords.update(synonyms[:3])
        
        # 4. Добавляем синонимы из команды
        for cmd_word in cmd_parts:
            if cmd_word in SYNONYM_MAP:
                synonyms = SYNONYM_MAP[cmd_word]
                keywords.update(synonyms[:2])
        
        return list(keywords)
    
    def search(self, query: str, top_k: int = 5) -> List[KnowledgeEntry]:
        """
        Поиск релевантных команд (только текстовый поиск)
        
        Args:
            query: запрос пользователя
            top_k: количество результатов
        
        Returns:
            Список релевантных записей
        """
        if not self.entries:
            logger.warning("⚠️  База знаний пуста")
            return []
        
        logger.info(f"🔍 Поиск: '{query[:50]}...'")
        
        results = self._text_search(query, top_k)
        results = sorted(results, key=lambda x: x.score, reverse=True)[:top_k]
        
        logger.info(f"✅ Найдено {len(results)} команд")
        for entry in results:
            logger.debug(f"   - {entry.command} (score: {entry.score:.2f})")
        
        return results
    
    def _text_search(self, query: str, top_k: int) -> List[KnowledgeEntry]:
        """
        Улучшенный текстовый поиск с синонимами и контекстом
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\b[а-яa-z]+\b', query_lower))
        
        # Расширяем query_words синонимами
        expanded_words = set(query_words)
        for word in query_words:
            if word in SYNONYM_MAP:
                expanded_words.update(SYNONYM_MAP[word])
        
        logger.debug(f"📝 Исходные слова: {query_words}")
        logger.debug(f"📚 Расширенные синонимами: {len(expanded_words)} слов")
        
        results = []
        for entry in self.entries:
            score = 0.0
            
            # 1. Точное совпадение в команде (вес: 2.5)
            if query_lower in entry.command.lower():
                score += 2.5
                logger.debug(f"   ✓ Точное совпадение в команде: {entry.command}")
            
            # 2. Точное совпадение в описании (вес: 2.0)
            if query_lower in entry.description.lower():
                score += 2.0
            
            # 3. Слова из query в команде (вес: 0.6 за слово)
            cmd_lower = entry.command.lower()
            matching_cmd_words = len(expanded_words & set(re.findall(r'\b[а-яa-z]+\b', cmd_lower)))
            score += matching_cmd_words * 0.6
            
            # 4. Слова из query в описании (вес: 0.5 за слово)
            desc_lower = entry.description.lower()
            matching_desc_words = len(expanded_words & set(re.findall(r'\b[а-яa-z]+\b', desc_lower)))
            score += matching_desc_words * 0.5
            
            # 5. Совпадение ключевых слов (вес: 0.2 за слово)
            matching_keywords = len(expanded_words & set(entry.keywords))
            score += matching_keywords * 0.2
            
            # 6. Контекстный бонус за категорию (вес: 0.4)
            for query_word in query_words:
                if query_word in CATEGORY_IMPORTANCE:
                    for important_cat, weight in CATEGORY_IMPORTANCE[query_word].items():
                        if important_cat.lower() in entry.category.lower():
                            score += weight * 0.4
            
            if score > 0:
                entry.score = score
                results.append(entry)
        
        return results
    
    def get_context_for_prompt(self, query: str, top_k: int = 3) -> str:
        """Получить контекст для включения в промпт модели"""
        results = self.search(query, top_k=top_k)
        
        if not results:
            return ""
        
        context_lines = ["\n📚 РЕЛЕВАНТНЫЕ КОМАНДЫ ИЗ БАЗЫ ЗНАНИЙ:"]
        
        for i, entry in enumerate(results, 1):
            context_lines.append(f"\n{i}. Команда: `{entry.command}`")
            context_lines.append(f"   Описание: {entry.description}")
            context_lines.append(f"   Категория: {entry.category}")
        
        return "\n".join(context_lines)


# Глобальный экземпляр
_kb_instance: Optional[BashKnowledgeBase] = None


def get_knowledge_base() -> BashKnowledgeBase:
    """Получить глобальный экземпляр базы знаний"""
    global _kb_instance
    
    if _kb_instance is None:
        _kb_instance = BashKnowledgeBase()
    
    return _kb_instance


def get_rag_context(query: str, top_k: int = 3) -> str:
    """Получить RAG контекст для запроса"""
    kb = get_knowledge_base()
    return kb.get_context_for_prompt(query, top_k=top_k)
