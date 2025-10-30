import json
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from database import db_manager

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """Контекст выполнения для сессии"""
    current_working_dir: str = "/"
    environment_vars: Dict[str, str] = None
    user_permissions: List[str] = None
    preferred_tools: List[str] = None

    def __post_init__(self):
        if self.environment_vars is None:
            self.environment_vars = {}
        if self.user_permissions is None:
            self.user_permissions = ["file_read", "file_write", "process_view"]
        if self.preferred_tools is None:
            self.preferred_tools = ["find", "grep", "ls", "cat"]


@dataclass
class SessionEvent:
    """Событие в сессии"""
    id: str
    timestamp: datetime
    query: str
    command: str
    status: str  # SUCCESS, ERROR, BLOCKED, CANCELLED
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


class Session:
    """Представляет одну сессию взаимодействия с пользователем"""

    def __init__(self, session_id: str = None, max_history: int = 100):
        self.id = session_id or str(uuid.uuid4())
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.context = SessionContext()
        self.events: List[SessionEvent] = []
        self.max_history = max_history
        self.metadata = {
            "user_skill_level": "beginner",
            "preferred_language": "russian", 
            "trust_level": 1.0,
        }
        
        # Загружаем из БД если сессия уже существует
        self._load_from_db()

    def _load_from_db(self):
        """Загружает данные сессии из базы данных"""
        try:
            # Загружаем все сессии из БД
            db_sessions = db_manager.get_all_sessions()
            session_data = next((s for s in db_sessions if s['id'] == self.id), None)
            
            if not session_data:
                logger.info(f"Сессия {self.id} не найдена в БД, создается новая")
                return

            # Восстанавливаем основные поля
            self.created_at = datetime.fromisoformat(session_data['created_at'])
            self.updated_at = datetime.fromisoformat(session_data['updated_at'])
            self.context.current_working_dir = session_data['current_working_dir']
            self.metadata.update({
                'user_skill_level': session_data['user_skill_level'],
                'preferred_language': session_data['preferred_language'],
                'trust_level': session_data['trust_level']
            })

            # Загружаем события сессии
            events_data = db_manager.get_session_events(self.id, self.max_history)
            for event_data in events_data:
                event = SessionEvent(
                    id=event_data['id'],
                    timestamp=datetime.fromisoformat(event_data['timestamp']),
                    query=event_data['query'],
                    command=event_data['command'],
                    status=event_data['status'],
                    output=event_data.get('output'),
                    error=event_data.get('error'),
                    execution_time=event_data.get('execution_time')
                )
                self.events.append(event)

            # Загружаем контекстные данные
            context_data = db_manager.get_session_context_data(self.id)
            
            # Восстанавливаем environment_vars из system_context
            env_vars = [ctx for ctx in context_data.get('system_context', []) 
                       if ctx['context_type'] == 'environment']
            for env_var in env_vars:
                self.context.environment_vars[env_var['key']] = env_var['value']

            # Восстанавливаем preferred_tools из user_preferences
            preferences = context_data.get('user_preferences', [])
            tool_names = [pref['tool_name'] for pref in preferences]
            self.context.preferred_tools.extend(tool_names)
            # Убираем дубликаты
            self.context.preferred_tools = list(dict.fromkeys(self.context.preferred_tools))

            logger.info(f"Загружена сессия из БД: {self.id} ({len(self.events)} событий)")

        except Exception as e:
            logger.error(f"Ошибка загрузки сессии {self.id} из БД: {e}")
            # При ошибке загрузки создаем новую сессию с этим ID
            self.created_at = datetime.now()
            self.updated_at = datetime.now()

    def get_recent_events(self, count: int = 10) -> List[SessionEvent]:
        """Возвращает последние события сессии"""
        return self.events[-count:] if self.events else []

    def get_statistics(self) -> Dict[str, Any]:
        """Статистика сессии"""
        total = len(self.events)
        if total == 0:
            return {}

        status_counts = {}
        for event in self.events:
            status_counts[event.status] = status_counts.get(event.status, 0) + 1

        return {
            "total_commands": total,
            "successful_commands": status_counts.get("SUCCESS", 0),
            "failed_commands": status_counts.get("ERROR", 0),
            "blocked_commands": status_counts.get("BLOCKED", 0),
            "success_rate": (status_counts.get("SUCCESS", 0) / total) * 100 if total > 0 else 0,
            "session_duration": str(self.updated_at - self.created_at)
        }

    def search_history(self, query: str, max_results: int = 5) -> List[SessionEvent]:
        """Поиск по истории сессии"""
        results = []
        query_lower = query.lower()

        for event in self.events:
            # Поиск по запросу пользователя
            if query_lower in event.query.lower():
                results.append(event)
            # Поиск по выполненной команде
            elif query_lower in event.command.lower():
                results.append(event)
            # Поиск по результату
            elif event.output and query_lower in event.output.lower():
                results.append(event)

        return results[-max_results:]  # Последние результаты

    def handle_search_command(self, query: str):
        """Обработка команды поиска по истории"""
        results = self.search_history(query)
        if not results:
            print(f"🔍 По запросу '{query}' ничего не найдено")
            return

        print(f"🔍 Результаты поиска '{query}':")
        for i, event in enumerate(results, 1):
            print(f"{i}. [{event.status}] {event.query}")
            print(f"   → {event.command}")
            if event.output:
                print(f"   📋 {event.output[:100]}...")

    def _update_user_metadata(self, command: str, output: str, error: str = None):
        """Анализирует команды для определения уровня пользователя"""
        complex_patterns = ['awk', 'sed', 'xargs', 'find.*-exec', 'grep -P']
        if any(pattern in command for pattern in complex_patterns):
            self.metadata["user_skill_level"] = "advanced"
        elif self.metadata["user_skill_level"] == "beginner" and len(self.events) > 5:
            self.metadata["user_skill_level"] = "intermediate"

    def _analyze_command_output(self, command: str, output: str, error: str = None):
        """Анализирует вывод команд для сбора информации о системе"""
        cmd_lower = command.lower()
        
        # Анализ вывода ls
        if cmd_lower.startswith('ls'):
            if output and not error:
                lines = output.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('total'):
                        # Простой парсинг вывода ls
                        parts = line.split()
                        if len(parts) > 1:
                            item_name = parts[-1]
                            item_type = 'directory' if line.startswith('d') else 'file'
                            db_manager.add_system_knowledge(
                                self.id, 'files', 
                                f"{self.context.current_working_dir}/{item_name}",
                                item_type
                            )
        
        # Анализ вывода find
        elif 'find' in cmd_lower:
            if output and not error:
                for line in output.split('\n'):
                    if line.strip():
                        db_manager.add_system_knowledge(
                            self.id, 'files', line.strip(), 'file'
                        )
        
        # Анализ вывода ps
        elif cmd_lower.startswith('ps'):
            if output and not error:
                lines = output.split('\n')[1:]  # Пропускаем заголовок
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) > 3:
                            process_name = parts[3]
                            db_manager.add_system_knowledge(
                                self.id, 'processes', process_name, 'process'
                            )

        # Обновляем метаданные пользователя
        self._update_user_metadata(command, output, error)

    def add_event(self, query: str, command: str, status: str,
                  output: str = None, error: str = None, execution_time: float = None):
        """Добавляет событие в историю сессии и сохраняет в БД"""
        event = SessionEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            query=query,
            command=command,
            status=status,
            output=output,
            error=error,
            execution_time=execution_time
        )

        self.events.append(event)
        self.updated_at = datetime.now()

        # Ограничиваем размер истории
        if len(self.events) > self.max_history:
            self.events = self.events[-self.max_history:]

        # Сохраняем в базу данных
        self._save_to_db()
        
        # Сохраняем событие в БД
        event_data = {
            'id': event.id,
            'session_id': self.id,
            'timestamp': event.timestamp.isoformat(),
            'query': event.query,
            'command': event.command,
            'status': event.status,
            'output': event.output,
            'error': event.error,
            'execution_time': event.execution_time
        }
        db_manager.save_event(event_data)
        
        # Обновляем предпочтения пользователя
        if command.strip():
            tool_name = command.split()[0]  # Первое слово команды
            success = status == 'SUCCESS'
            db_manager.update_user_preference(self.id, tool_name, success)

        logger.info(f"Добавлено событие в сессию {self.id}: {status}")
        return event

    def _save_to_db(self):
        """Сохраняет сессию в базу данных"""
        session_data = {
            'id': self.id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'context': asdict(self.context),
            'metadata': self.metadata
        }
        db_manager.save_session(session_data)

    def update_context_from_command(self, command: str, output: str, error: str = None):
        """Расширенное обновление контекста на основе выполненной команды"""
        cmd_lower = command.lower()

        # 1. ОБНОВЛЕНИЕ РАБОЧЕЙ ДИРЕКТОРИИ
        if cmd_lower.startswith('cd '):
            new_dir = command[3:].strip()
            if not error and "no such file" not in output.lower() and "not a directory" not in output.lower():
                # Обработка относительных путей
                if new_dir.startswith('/'):
                    # Абсолютный путь
                    self.context.current_working_dir = new_dir
                elif new_dir == '..':
                    # Переход на уровень выше
                    if self.context.current_working_dir != '/':
                        parts = self.context.current_working_dir.rstrip('/').split('/')
                        self.context.current_working_dir = '/'.join(parts[:-1]) or '/'
                elif new_dir == '~':
                    # Домашняя директория
                    self.context.current_working_dir = os.path.expanduser('~')
                else:
                    # Относительный путь
                    if self.context.current_working_dir == '/':
                        self.context.current_working_dir = f'/{new_dir}'
                    else:
                        self.context.current_working_dir = f'{self.context.current_working_dir}/{new_dir}'
                logger.info(f"Обновлена рабочая директория: {self.context.current_working_dir}")
                # Сохраняем в БД
                db_manager.update_system_context(
                    self.id, 'file_system', 'current_working_dir', 
                    self.context.current_working_dir
                )

        # 2. ОБНОВЛЕНИЕ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
        if cmd_lower.startswith('export '):
            # Парсим export VAR=value
            parts = command[7:].strip().split('=', 1)
            if len(parts) == 2:
                var, value = parts
                self.context.environment_vars[var.strip()] = value.strip()
                logger.info(f"Добавлена переменная окружения: {var.strip()}")
                db_manager.update_system_context(
                    self.id, 'environment', var.strip(), value.strip()
                )
        
        # 3. АНАЛИЗ ВЫВОДА КОМАНД ДЛЯ СБОРА ИНФОРМАЦИИ О СИСТЕМЕ
        self._analyze_command_output(command, output, error)
        
        # 4. ОБНОВЛЕНИЕ ПРЕДПОЧТЕНИЙ ПОЛЬЗОВАТЕЛЯ
        self._update_user_preferences(command, output, error)

        # 5. ОБНОВЛЕНИЕ УРОВНЯ НАВЫКОВ
        self._update_user_metadata(command, output, error)
        
        # Сохраняем изменения
        self._save_to_db()

    def _update_user_preferences(self, command: str, output: str, error: str = None):
        """Обновляет предпочтения пользователя на основе используемых команд"""
        cmd_lower = command.lower()

        # Анализ предпочитаемых инструментов
        tools_used = []

        if any(tool in cmd_lower for tool in ['find', 'locate']):
            tools_used.append('find')
        if any(tool in cmd_lower for tool in ['grep', 'awk', 'sed']):
            tools_used.append('text_processing')
        if any(tool in cmd_lower for tool in ['docker', 'podman']):
            tools_used.append('containers')
        if any(tool in cmd_lower for tool in ['git']):
            tools_used.append('version_control')
        if any(tool in cmd_lower for tool in ['python', 'pip']):
            tools_used.append('python')

        # Обновляем предпочтения (добавляем новые, но не удаляем старые)
        for tool in tools_used:
            if tool not in self.context.preferred_tools:
                self.context.preferred_tools.append(tool)

        # Ограничиваем список 10 самыми частыми инструментами
        if len(self.context.preferred_tools) > 10:
            self.context.preferred_tools = self.context.preferred_tools[-10:]

    def get_enhanced_context_prompt(self, query: str) -> str:
        """Получает расширенный контекст из БД для промпта"""
        return db_manager.get_enhanced_prompt_context(self.id, query)


class SessionManager:
    """Централизованное управление всеми сессиями"""

    def __init__(self, storage_path: str = "sessions"):
        self.sessions: Dict[str, Session] = {}
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.current_session_id: Optional[str] = None

        # Загружаем существующие сессии
        self._load_sessions()
        self._load_sessions_from_db()

    def _load_sessions_from_db(self):
        """Загружает все сессии из базы данных"""
        try:
            db_sessions = db_manager.get_all_sessions()
            
            for session_data in db_sessions:
                session_id = session_data['id']
                
                # Если сессия уже загружена из JSON, пропускаем
                if session_id in self.sessions:
                    continue
                    
                # Создаем объект сессии (он сам загрузит детали из БД)
                session = Session(session_id=session_id)
                self.sessions[session_id] = session
                
                logger.debug(f"Загружена сессия из БД: {session_id}")

            logger.info(f"Загружено {len(db_sessions)} сессий из БД")
            
            # Если есть сессии, устанавливаем последнюю как текущую
            if self.sessions and not self.current_session_id:
                latest_session = max(self.sessions.values(), 
                                   key=lambda s: s.updated_at)
                self.current_session_id = latest_session.id
                logger.info(f"Текущая сессия установлена: {latest_session.id[:8]}...")
                
        except Exception as e:
            logger.error(f"Ошибка загрузки сессий из БД: {e}")

    def create_session(self, session_id: str = None) -> Session:
        """Создает новую сессию"""
        session = Session(session_id)
        self.sessions[session.id] = session
        self.current_session_id = session.id

        # Сохраняем в БД
        session._save_to_db()

        logger.info(f"Создана новая сессия: {session.id}")
        return session

    def get_current_session(self) -> Optional[Session]:
        """Возвращает текущую активную сессию"""
        if self.current_session_id and self.current_session_id in self.sessions:
            return self.sessions[self.current_session_id]
        return None

    def get_or_create_current_session(self) -> Session:
        """Возвращает текущую сессию или создает новую"""
        session = self.get_current_session()
        if not session:
            session = self.create_session()
        return session

    def switch_session(self, session_id: str) -> bool:
        """Переключается на указанную сессию"""
        if session_id in self.sessions:
            self.current_session_id = session_id
            logger.info(f"Переключение на сессию: {session_id}")
            return True
        
        # Если сессия не найдена в памяти, пробуем загрузить из БД
        try:
            session = Session(session_id=session_id)
            self.sessions[session_id] = session
            self.current_session_id = session_id
            logger.info(f"Загружена и активирована сессия из БД: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Не удалось загрузить сессию {session_id} из БД: {e}")
            return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Возвращает список всех сессий с метаданными"""
        sessions_info = []
        for session_id, session in self.sessions.items():
            stats = session.get_statistics()
            sessions_info.append({
                "id": session_id,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "event_count": len(session.events),
                "is_current": session_id == self.current_session_id,
                **stats
            })

        return sorted(sessions_info, key=lambda x: x['updated_at'], reverse=True)

    def save_session(self, session_id: str = None):
        """Сохраняет сессию (теперь в основном в БД)"""
        session_id = session_id or self.current_session_id
        if not session_id or session_id not in self.sessions:
            return

        session = self.sessions[session_id]
        session._save_to_db()

        # Также сохраняем в JSON для обратной совместимости
        session_file = self.storage_path / f"{session_id}.json"
        try:
            session_data = {
                "id": session.id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "context": asdict(session.context),
                "metadata": session.metadata,
                "events": [
                    {
                        "id": event.id,
                        "timestamp": event.timestamp.isoformat(),
                        "query": event.query,
                        "command": event.command,
                        "status": event.status,
                        "output": event.output,
                        "error": event.error,
                        "execution_time": event.execution_time
                    }
                    for event in session.events
                ]
            }

            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Сохранена сессия в JSON: {session_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения сессии {session_id} в JSON: {e}")

    def _load_sessions(self):
        """Загружает сессии с обработкой ошибок"""
        for session_file in self.storage_path.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                session = Session(session_data["id"])
                session.created_at = datetime.fromisoformat(session_data["created_at"])
                session.updated_at = datetime.fromisoformat(session_data["updated_at"])
                session.context = SessionContext(**session_data["context"])
                session.metadata = session_data["metadata"]

                # Восстанавливаем события
                for event_data in session_data.get("events", []):
                    event = SessionEvent(
                        id=event_data["id"],
                        timestamp=datetime.fromisoformat(event_data["timestamp"]),
                        query=event_data["query"],
                        command=event_data["command"],
                        status=event_data["status"],
                        output=event_data.get("output"),
                        error=event_data.get("error"),
                        execution_time=event_data.get("execution_time")
                    )
                    session.events.append(event)

                self.sessions[session.id] = session
                logger.debug(f"Загружена сессия: {session.id}")

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Поврежден файл сессии {session_file}: {e}")
                # Создаем резервную копию и пропускаем
                backup_file = session_file.with_suffix('.json.corrupted')
                session_file.rename(backup_file)
                print(f"⚠️ Сессия {session_file.stem} повреждена, создана резервная копия")

    def cleanup_old_sessions(self, days: int = 30, max_sessions: int = 100):
        """Очистка старых сессий с ограничением по количеству"""
        # По времени
        cutoff_date = datetime.now() - timedelta(days=days)
        # По количеству (оставляем N самых новых)
        sessions_to_keep = sorted(
            self.sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True
        )[:max_sessions]

        # Удаляем старые
        for session in list(self.sessions.values()):
            if session not in sessions_to_keep and session.updated_at < cutoff_date:
                self._delete_session(session.id)

    def _delete_session(self, session_id: str):
        """Удаляет сессию"""
        if session_id in self.sessions:
            # Удаляем из памяти
            del self.sessions[session_id]
            
            # Удаляем JSON файл
            session_file = self.storage_path / f"{session_id}.json"
            if session_file.exists():
                session_file.unlink()
            
            # Если удаляемая сессия была текущей, сбрасываем текущую сессию
            if self.current_session_id == session_id:
                self.current_session_id = None
            
            logger.info(f"Удалена сессия: {session_id}")

    def find_session_by_prefix(self, prefix: str) -> Optional[str]:
        """
        Находит полный ID сессии по префиксу
        """
        matching_sessions = []
        for session_id in self.sessions.keys():
            if session_id.startswith(prefix):
                matching_sessions.append(session_id)

        if len(matching_sessions) == 1:
            return matching_sessions[0]
        elif len(matching_sessions) > 1:
            print(f"⚠️ Найдено несколько сессий:")
            for session_id in matching_sessions:
                print(f"  {session_id}")
            return None
        else:
            return None


# Глобальный экземпляр менеджера сессий
session_manager = SessionManager()