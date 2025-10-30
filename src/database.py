# database.py
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер базы данных SQLite для хранения контекста и истории"""
    
    def __init__(self, db_path: str = "ai_assistant.db"):
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных с созданием таблиц"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица сессий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    current_working_dir TEXT NOT NULL,
                    user_skill_level TEXT NOT NULL,
                    preferred_language TEXT NOT NULL,
                    trust_level REAL NOT NULL
                )
            ''')
            
            # Таблица событий сессии
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    query TEXT NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output TEXT,
                    error TEXT,
                    execution_time REAL,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            ''')
            
            # Таблица контекста системы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    context_type TEXT NOT NULL,  -- 'file_system', 'process', 'network', 'environment'
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            ''')
            
            # Таблица предпочтений пользователя
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 1,
                    last_used TEXT NOT NULL,
                    success_rate REAL DEFAULT 1.0,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE,
                    UNIQUE(session_id, tool_name)
                )
            ''')
            
            # Таблица знаний о системе
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    category TEXT NOT NULL,  -- 'files', 'directories', 'services', 'configs'
                    item_path TEXT NOT NULL,
                    item_type TEXT NOT NULL,  -- 'file', 'directory', 'service', 'config'
                    metadata TEXT,
                    discovered_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    access_count INTEGER DEFAULT 1,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            ''')
            
            # Индексы для улучшения производительности
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_session ON session_events(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON session_events(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_context_session ON system_context(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_session ON system_knowledge(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_category ON system_knowledge(category)')
            
            conn.commit()
        
        logger.info(f"База данных инициализирована: {self.db_path}")

    def save_session(self, session_data: Dict[str, Any]):
        """Сохраняет или обновляет сессию в базе данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO sessions 
                (id, created_at, updated_at, current_working_dir, user_skill_level, preferred_language, trust_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_data['id'],
                session_data['created_at'],
                session_data['updated_at'],
                session_data['context']['current_working_dir'],
                session_data['metadata']['user_skill_level'],
                session_data['metadata']['preferred_language'],
                session_data['metadata']['trust_level']
            ))
            
            conn.commit()

    def save_event(self, event_data: Dict[str, Any]):
        """Сохраняет событие сессии"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO session_events 
                (id, session_id, timestamp, query, command, status, output, error, execution_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event_data['id'],
                event_data['session_id'],
                event_data['timestamp'],
                event_data['query'],
                event_data['command'],
                event_data['status'],
                event_data.get('output'),
                event_data.get('error'),
                event_data.get('execution_time')
            ))
            
            conn.commit()

    def update_system_context(self, session_id: str, context_type: str, key: str, value: str, metadata: str = None):
        """Обновляет контекст системы"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO system_context 
                (session_id, timestamp, context_type, key, value, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                datetime.now().isoformat(),
                context_type,
                key,
                value,
                metadata
            ))
            
            conn.commit()

    def update_user_preference(self, session_id: str, tool_name: str, success: bool = True):
        """Обновляет предпочтения пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Проверяем существующую запись
            cursor.execute('''
                SELECT usage_count, success_rate FROM user_preferences 
                WHERE session_id = ? AND tool_name = ?
            ''', (session_id, tool_name))
            
            result = cursor.fetchone()
            
            if result:
                # Обновляем существующую запись
                usage_count, old_success_rate = result
                new_usage_count = usage_count + 1
                new_success_rate = ((old_success_rate * usage_count) + (1 if success else 0)) / new_usage_count
                
                cursor.execute('''
                    UPDATE user_preferences 
                    SET usage_count = ?, success_rate = ?, last_used = ?
                    WHERE session_id = ? AND tool_name = ?
                ''', (new_usage_count, new_success_rate, datetime.now().isoformat(), session_id, tool_name))
            else:
                # Создаем новую запись
                cursor.execute('''
                    INSERT INTO user_preferences 
                    (session_id, tool_name, last_used, success_rate)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, tool_name, datetime.now().isoformat(), 1.0 if success else 0.0))
            
            conn.commit()

    def add_system_knowledge(self, session_id: str, category: str, item_path: str, item_type: str, metadata: str = None):
        """Добавляет знания о системе"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Проверяем существующую запись
            cursor.execute('''
                SELECT access_count FROM system_knowledge 
                WHERE session_id = ? AND category = ? AND item_path = ?
            ''', (session_id, category, item_path))
            
            result = cursor.fetchone()
            now = datetime.now().isoformat()
            
            if result:
                # Обновляем существующую запись
                access_count = result[0] + 1
                cursor.execute('''
                    UPDATE system_knowledge 
                    SET last_accessed = ?, access_count = ?, metadata = ?
                    WHERE session_id = ? AND category = ? AND item_path = ?
                ''', (now, access_count, metadata, session_id, category, item_path))
            else:
                # Создаем новую запись
                cursor.execute('''
                    INSERT INTO system_knowledge 
                    (session_id, category, item_path, item_type, metadata, discovered_at, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, category, item_path, item_type, metadata, now, now))
            
            conn.commit()

    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Получает полный контекст сессии"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Получаем основную информацию о сессии
            cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
            session_row = cursor.fetchone()
            
            if not session_row:
                return None
            
            # Получаем последние события
            cursor.execute('''
                SELECT * FROM session_events 
                WHERE session_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 10
            ''', (session_id,))
            events = [dict(row) for row in cursor.fetchall()]
            
            # Получаем контекст системы
            cursor.execute('SELECT * FROM system_context WHERE session_id = ?', (session_id,))
            system_context = [dict(row) for row in cursor.fetchall()]
            
            # Получаем предпочтения пользователя
            cursor.execute('''
                SELECT tool_name, usage_count, success_rate 
                FROM user_preferences 
                WHERE session_id = ? 
                ORDER BY usage_count DESC 
                LIMIT 5
            ''', (session_id,))
            preferences = [dict(row) for row in cursor.fetchall()]
            
            # Получаем знания о системе
            cursor.execute('''
                SELECT category, item_path, item_type, metadata 
                FROM system_knowledge 
                WHERE session_id = ? 
                ORDER BY last_accessed DESC 
                LIMIT 20
            ''', (session_id,))
            knowledge = [dict(row) for row in cursor.fetchall()]
            
            return {
                'session': dict(session_row),
                'recent_events': events,
                'system_context': system_context,
                'user_preferences': preferences,
                'system_knowledge': knowledge
            }

    def get_enhanced_prompt_context(self, session_id: str, current_query: str) -> str:
        """Создает расширенный контекст для промпта на основе данных из БД"""
        context = self.get_session_context(session_id)
        if not context:
            return current_query
        
        context_parts = []
        
        # 1. Информация о сессии
        session = context['session']
        context_parts.append(f"ТЕКУЩАЯ СЕССИЯ:")
        context_parts.append(f"- Рабочая директория: {session['current_working_dir']}")
        context_parts.append(f"- Уровень пользователя: {session['user_skill_level']}")
        context_parts.append(f"- Уровень доверия: {session['trust_level']}")
        
        # 2. Последние команды
        if context['recent_events']:
            context_parts.append("\nПОСЛЕДНИЕ КОМАНДЫ:")
            for event in context['recent_events'][:5]:
                status = "✅" if event['status'] == 'SUCCESS' else "❌"
                context_parts.append(f"- {event['command']} {status}")
                if event['output'] and len(event['output']) < 50:
                    context_parts.append(f"  Результат: {event['output']}")
        
        # 3. Предпочтения пользователя
        if context['user_preferences']:
            context_parts.append("\nПРЕДПОЧТЕНИЯ ПОЛЬЗОВАТЕЛЯ:")
            for pref in context['user_preferences']:
                success_rate = pref['success_rate'] * 100
                context_parts.append(f"- {pref['tool_name']} (использовано: {pref['usage_count']}, успешность: {success_rate:.1f}%)")
        
        # 4. Знания о системе
        if context['system_knowledge']:
            # Группируем по категориям
            knowledge_by_category = {}
            for item in context['system_knowledge']:
                category = item['category']
                if category not in knowledge_by_category:
                    knowledge_by_category[category] = []
                knowledge_by_category[category].append(item)
            
            context_parts.append("\nИЗВЕСТНАЯ ИНФОРМАЦИЯ О СИСТЕМЕ:")
            for category, items in knowledge_by_category.items():
                context_parts.append(f"- {category.upper()}:")
                for item in items[:3]:  # Максимум 3 элемента на категорию
                    context_parts.append(f"  {item['item_path']} ({item['item_type']})")
        
        # 5. Контекст системы
        if context['system_context']:
            context_parts.append("\nКОНТЕКСТ СИСТЕМЫ:")
            for ctx in context['system_context'][:5]:
                context_parts.append(f"- {ctx['key']}: {ctx['value']}")
        
        context_str = "\n".join(context_parts)
        enhanced_prompt = f"""КОНТЕКСТ ДЛЯ ГЕНЕРАЦИИ КОМАНДЫ:
{context_str}

ТЕКУЩИЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {current_query}

СГЕНЕРИРУЙТЕ КОМАНДУ:"""
        
        return enhanced_prompt

    def cleanup_old_data(self, days_to_keep: int = 30):
        """Очищает старые данные"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Удаляем старые сессии и связанные данные через каскадное удаление
            cursor.execute('DELETE FROM sessions WHERE updated_at < ?', (cutoff_date,))
            
            conn.commit()

# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()