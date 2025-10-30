# interactive.py
import logging
import os
import time
from colorama import Fore, Style, init
from llm_client import generate_command
from executor import run_command, is_dangerous_command, categorize_command, CommandCategory
from session_manager import session_manager, Session
from database import db_manager  # ДОБАВИТЬ ЭТОТ ИМПОРТ

# Инициализация colorama для цветного вывода
init(autoreset=True)

logger = logging.getLogger(__name__)


def interactive_loop():
    """
    Главный интерактивный цикл с поддержкой перезапуска при смене сессии
    """
    restart_required = False

    while True:
        if restart_required:
            # Перезапускаем цикл с новой сессией
            session = session_manager.get_or_create_current_session()
            restart_required = False
            print(f"{Fore.CYAN}🔄 Перезапуск с сессией: {session.id[:8]}...")
        else:
            # Обычный запуск
            session = session_manager.get_or_create_current_session()

        logger.info(f"Запуск интерактивного режима для сессии: {session.id}")

        print(f"{Fore.CYAN}🤖 Запущен интерактивный режим AI-ассистента")
        print(f"{Fore.GREEN}📁 Сессия: {session.id[:8]}...")
        print(f"{Fore.YELLOW}💬 Введите 'exit' или 'quit' для выхода")
        print(f"{Fore.YELLOW}📝 Введите 'help' для получения помощи")
        print(f"{Fore.YELLOW}📊 Введите 'history' для просмотра истории текущей сессии")
        print(f"{Fore.YELLOW}🔧 Введите 'session' для управления сессиями")
        print(f"{Fore.YELLOW}🗃️ Введите 'context' для просмотра контекста из БД")
        print("-" * 50)

        session_exit = False

        while not session_exit and not restart_required:
            try:
                prompt = input(f"{Fore.GREEN}AIask[{session.id[:8]}]> {Style.RESET_ALL}").strip()

                if prompt.lower() in ("exit", "quit", "q"):
                    logger.info("Выход из интерактивного режима")
                    session_manager.save_session(session.id)
                    print(f"{Fore.CYAN}👋 До свидания! Сессия сохранена.")
                    session_exit = True
                    continue

                if prompt.lower() == "help":
                    show_help()
                    continue

                if prompt.lower() == "history":
                    show_session_history(session)
                    continue

                if prompt.lower() == "session":
                    restart_needed = handle_session_commands(session)
                    if restart_needed:
                        restart_required = True
                        break  # Выходим из внутреннего цикла для перезапуска
                    continue
                    
                if prompt.lower() == "context":
                    show_database_context(session)
                    continue

                if prompt.lower() == "clear":
                    os.system('clear' if os.name != 'nt' else 'cls')
                    continue

                if not prompt:
                    continue

                logger.info(f"Обработка запроса: {prompt}")

                # Генерируем команду с учетом контекста сессии
                enhanced_prompt = enhance_prompt_with_context(prompt, session)
                resp = generate_command(enhanced_prompt)

                # ЗАЩИТА ОТ None и неправильного формата ответа
                if not resp or not isinstance(resp, dict):
                    print(f"{Fore.RED}❌ Ошибка: AI не вернул корректный ответ")
                    logger.error(f"Некорректный ответ от generate_command: {resp}")
                    session.add_event(prompt, "", "AI_ERROR")
                    continue

                # Безопасное извлечение данных
                cmd = resp.get("command", "")
                expl = resp.get("explanation", "")

                if not cmd:
                    print(f"{Fore.RED}❌ Не удалось сгенерировать команду. Попробуйте переформулировать запрос.")
                    if expl:
                        print(f"{Fore.YELLOW}💡 AI сообщение: {expl}")
                    logger.warning("Не удалось сгенерировать команду")
                    session.add_event(prompt, "", "GENERATION_ERROR")
                    continue

                # Проверка безопасности ДО вывода
                if is_dangerous_command(cmd):
                    print(f"{Fore.RED}🚨 ОПАСНАЯ КОМАНДА ЗАБЛОКИРОВАНА!")
                    print(f"{Fore.YELLOW}Команда: {cmd}")
                    print(f"{Fore.RED}⛔ Эта команда может нанести серьезный вред системы.")
                    logger.warning(f"Заблокирована опасная команда: {cmd}")
                    session.add_event(prompt, cmd, "BLOCKED")
                    session_manager.save_session(session.id)
                    continue

                # Показываем категорию команды
                category = categorize_command(cmd)
                category_icon = {
                    CommandCategory.SAFE: f"{Fore.GREEN}✓",
                    CommandCategory.WRITE: f"{Fore.YELLOW}✎",
                    CommandCategory.DANGEROUS: f"{Fore.MAGENTA}⚠",
                    CommandCategory.CRITICAL: f"{Fore.RED}⛔"
                }

                print(f"{Fore.CYAN}🤖 Команда: {Fore.WHITE}{cmd} {category_icon.get(category, '')}")
                if expl:
                    print(f"{Fore.BLUE}💡 Объяснение: {expl}")

                # Подтверждение выполнения
                confirm = input(f"{Fore.YELLOW}Выполнить? [y/N]: {Style.RESET_ALL}").strip().lower()

                if confirm in ('y', 'yes', 'да'):
                    logger.info("Пользователь подтвердил выполнение")

                    start_time = time.time()
                    code, out, err = run_command(cmd)
                    execution_time = time.time() - start_time

                    if code == 0:
                        print(f"{Fore.GREEN}✅ Команда выполнена успешно")
                        if out.strip():
                            print(f"{Style.RESET_ALL}{out}")

                        # Обновляем контекст сессии
                        session.update_context_from_command(cmd, out)
                        session.add_event(prompt, cmd, "SUCCESS", out, None, execution_time)
                    else:
                        if "превышен лимит времени" in err.lower() or "timeout" in err.lower():
                            print(f"{Fore.YELLOW}⏱️ Команда не завершилась вовремя (timeout)")
                        else:
                            print(f"{Fore.RED}❌ Ошибка выполнения (код {code})")
                        if err.strip():
                            print(f"{Fore.RED}Детали: {err}")
                        session.add_event(prompt, cmd, "ERROR", out, err, execution_time)

                    # Авто-сохранение после выполнения
                    session_manager.save_session(session.id)
                else:
                    logger.info("Пользователь отменил выполнение")
                    print(f"{Fore.YELLOW}⏭️ Выполнение пропущено")
                    session.add_event(prompt, cmd, "CANCELLED")

            except KeyboardInterrupt:
                logger.info("Прерывание через Ctrl+C")
                session_manager.save_session(session.id)
                print(f"\n{Fore.CYAN}👋 Выход по прерыванию... Сессия сохранена.")
                session_exit = True
                break

            except Exception as e:
                logger.exception(f"Ошибка в интерактивном режиме: {e}")
                print(f"{Fore.RED}❌ Произошла ошибка: {e}")
                print(f"{Fore.YELLOW}🔄 Продолжаем работу...")
                if 'prompt' in locals():
                    session.add_event(prompt, "", "SYSTEM_ERROR", error=str(e))

        if session_exit:
            break  # Полный выход из программы


def handle_session_commands(session: Session) -> bool:
    """
    Обрабатывает команды управления сессиями
    Возвращает True если требуется перезапуск цикла
    """
    print(f"\n{Fore.CYAN}🔄 УПРАВЛЕНИЕ СЕССИЯМИ")
    print(f"{Fore.GREEN}Текущая сессия: {session.id}")

    stats = session.get_statistics()
    if stats:
        print(f"{Fore.YELLOW}Статистика:")
        print(f"  Всего команд: {stats['total_commands']}")
        print(f"  Успешных: {stats['successful_commands']}")
        print(f"  Ошибок: {stats['failed_commands']}")
        print(f"  Заблокировано: {stats.get('blocked_commands', 0)}")
        print(f"  Успешность: {stats['success_rate']:.1f}%")

    print(f"\n{Fore.CYAN}Доступные команды:")
    print(f"  {Fore.GREEN}list{Style.RESET_ALL} - список всех сессий")
    print(f"  {Fore.GREEN}new{Style.RESET_ALL} - создать новую сессию")
    print(f"  {Fore.GREEN}save{Style.RESET_ALL} - сохранить текущую сессию")
    print(f"  {Fore.GREEN}switch <id>{Style.RESET_ALL} - переключиться на сессию")
    print(f"  {Fore.GREEN}info <id>{Style.RESET_ALL} - информация о сессии")
    print(f"  {Fore.GREEN}delete <id>{Style.RESET_ALL} - удалить сессию")
    print(f"  {Fore.GREEN}back{Style.RESET_ALL} - вернуться к работе")

    command = input(f"\n{Fore.YELLOW}session> {Style.RESET_ALL}").strip().lower()

    if command == "back":
        return False  # Не требуется перезапуск

    if command == "list":
        sessions_list = session_manager.list_sessions()
        print(f"\n{Fore.CYAN}📋 СЕССИИ:")
        for s in sessions_list:
            current_flag = " ← текущая" if s['is_current'] else ""
            print(
                f"  {s['id']} - {s['event_count']} команд, обновлена: {s['updated_at'].strftime('%H:%M')}{current_flag}")
        return False

    elif command == "new":
        # Сохраняем текущую сессию перед созданием новой
        session_manager.save_session(session.id)

        new_session = session_manager.create_session()
        print(f"{Fore.GREEN}✅ Создана новая сессия: {new_session.id}")

        # Переключаемся на новую сессию
        session_manager.switch_session(new_session.id)
        return True  # Требуется перезапуск цикла

    elif command == "save":
        session_manager.save_session(session.id)
        print(f"{Fore.GREEN}✅ Сессия сохранена")
        return False

    elif command.startswith("switch "):
        # Сохраняем текущую сессию перед переключением
        session_manager.save_session(session.id)

        target_id = command[7:].strip()

        # Прямой поиск по полному ID
        if target_id in session_manager.sessions:
            if session_manager.switch_session(target_id):
                print(f"{Fore.GREEN}✅ Переключено на сессию: {target_id}")
                return True  # Требуется перезапуск цикла
            else:
                print(f"{Fore.RED}❌ Ошибка переключения")
                return False
        else:
            # Поиск по префиксу
            matching_sessions = []
            for session_id in session_manager.sessions.keys():
                if session_id.startswith(target_id):
                    matching_sessions.append(session_id)

            if len(matching_sessions) == 1:
                full_id = matching_sessions[0]
                if session_manager.switch_session(full_id):
                    print(f"{Fore.GREEN}✅ Переключено на сессию: {full_id}")
                    return True  # Требуется перезапуск цикла
                else:
                    print(f"{Fore.RED}❌ Ошибка переключения")
                    return False
            elif len(matching_sessions) > 1:
                print(f"{Fore.YELLOW}⚠️ Найдено несколько сессий:")
                for session_id in matching_sessions:
                    print(f"  {session_id}")
                print(f"{Fore.YELLOW}💡 Уточните ID сессии")
                return False
            else:
                print(f"{Fore.RED}❌ Сессия не найдена: {target_id}")
                return False

    elif command.startswith("info "):
        target_id = command[5:].strip()

        # Находим сессию
        target_session = None
        if target_id in session_manager.sessions:
            target_session = session_manager.sessions[target_id]
        else:
            # Поиск по префиксу
            matching_sessions = [sid for sid in session_manager.sessions.keys()
                                 if sid.startswith(target_id)]
            if len(matching_sessions) == 1:
                target_session = session_manager.sessions[matching_sessions[0]]
            elif len(matching_sessions) > 1:
                print(f"{Fore.YELLOW}⚠️ Найдено несколько сессий:")
                for session_id in matching_sessions:
                    print(f"  {session_id}")
                return False

        if target_session:
            _show_session_info(target_session)
        else:
            print(f"{Fore.RED}❌ Сессия не найдена: {target_id}")
        return False

    elif command.startswith("delete "):
        target_id = command[7:].strip()

        # Нельзя удалить текущую сессию
        if target_id == session.id or target_id == session.id[:8]:
            print(f"{Fore.RED}❌ Нельзя удалить текущую сессию!")
            print(f"{Fore.YELLOW}💡 Переключитесь на другую сессию сначала")
            return False

        # Находим сессию для удаления
        session_to_delete = None
        if target_id in session_manager.sessions:
            session_to_delete = target_id
        else:
            # Поиск по префиксу
            matching_sessions = [sid for sid in session_manager.sessions.keys()
                                 if sid.startswith(target_id)]
            if len(matching_sessions) == 1:
                session_to_delete = matching_sessions[0]
            elif len(matching_sessions) > 1:
                print(f"{Fore.YELLOW}⚠️ Найдено несколько сессий:")
                for session_id in matching_sessions:
                    print(f"  {session_id}")
                return False

        if session_to_delete:
            if session_to_delete in session_manager.sessions:
                # Удаляем файл сессии
                session_file = session_manager.storage_path / f"{session_to_delete}.json"
                if session_file.exists():
                    os.remove(session_file)

                # Удаляем из менеджера
                del session_manager.sessions[session_to_delete]
                print(f"{Fore.GREEN}✅ Сессия удалена: {session_to_delete}")
            else:
                print(f"{Fore.RED}❌ Сессия не найдена: {target_id}")
        else:
            print(f"{Fore.RED}❌ Сессия не найдена: {target_id}")
        return False

    return False


def _show_session_info(session: Session):
    """Показывает детальную информацию о сессии"""
    stats = session.get_statistics()

    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"📊 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О СЕССИИ")
    print(f"{'=' * 60}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}ID: {session.id}")
    print(f"{Fore.GREEN}Создана: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.GREEN}Обновлена: {session.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.GREEN}Длительность: {session.updated_at - session.created_at}")

    print(f"\n{Fore.YELLOW}📈 СТАТИСТИКА:")
    if stats:
        for key, value in stats.items():
            print(f"  {key}: {value}")
    else:
        print(f"  Нет данных о статистике")

    print(f"\n{Fore.BLUE}🎯 КОНТЕКСТ:")
    print(f"  Текущая директория: {session.context.current_working_dir}")
    print(f"  Переменные окружения: {len(session.context.environment_vars)}")
    print(f"  Права доступа: {', '.join(session.context.user_permissions)}")
    print(f"  Предпочтения: {', '.join(session.context.preferred_tools)}")

    print(f"\n{Fore.MAGENTA}👤 МЕТАДАННЫЕ:")
    for key, value in session.metadata.items():
        print(f"  {key}: {value}")

    print(f"\n{Fore.CYAN}📜 ПОСЛЕДНИЕ КОМАНДЫ (последние 5):")
    recent_events = session.get_recent_events(5)
    if recent_events:
        for i, event in enumerate(recent_events, 1):
            status_icon = {
                "SUCCESS": f"{Fore.GREEN}✅",
                "ERROR": f"{Fore.RED}❌",
                "BLOCKED": f"{Fore.RED}🚨",
                "CANCELLED": f"{Fore.YELLOW}⏭️"
            }
            icon = status_icon.get(event.status, "")
            print(f"  {icon} {event.timestamp.strftime('%H:%M:%S')} - {event.command}")
    else:
        print(f"  Нет выполненных команд")

    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")


def show_database_context(session):
    """Показывает контекст из базы данных"""
    context = db_manager.get_session_context(session.id)
    if not context:
        print(f"{Fore.YELLOW}📭 Контекст не найден в базе данных")
        return
        
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"🗃️ КОНТЕКСТ ИЗ БАЗЫ ДАННЫХ")
    print(f"{'=' * 60}{Style.RESET_ALL}")
    
    # Информация о сессии
    session_data = context['session']
    print(f"{Fore.GREEN}📁 СЕССИЯ:")
    print(f"  ID: {session_data['id']}")
    print(f"  Директория: {session_data['current_working_dir']}")
    print(f"  Уровень: {session_data['user_skill_level']}")
    print(f"  Язык: {session_data['preferred_language']}")
    print(f"  Доверие: {session_data['trust_level']}")
    
    # Предпочтения
    if context['user_preferences']:
        print(f"\n{Fore.BLUE}🎯 ПРЕДПОЧТЕНИЯ:")
        for pref in context['user_preferences']:
            success_rate = pref['success_rate'] * 100
            print(f"  {pref['tool_name']}: {pref['usage_count']} использований, {success_rate:.1f}% успеха")
    
    # Знания о системе
    if context['system_knowledge']:
        print(f"\n{Fore.MAGENTA}📚 ИЗВЕСТНЫЕ ФАЙЛЫ/ПРОЦЕССЫ:")
        knowledge_by_category = {}
        for item in context['system_knowledge']:
            category = item['category']
            if category not in knowledge_by_category:
                knowledge_by_category[category] = []
            knowledge_by_category[category].append(item)
            
        for category, items in knowledge_by_category.items():
            print(f"  {category.upper()}:")
            for item in items[:3]:
                print(f"    {item['item_path']}")
    
    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")


def enhance_prompt_with_context(prompt: str, session: Session) -> str:
    """
    Умное улучшение промпта с учетом полного контекста сессии
    Без эмодзи - только чистый текст для модели
    """
    context_parts = []

    # 1. ТЕКУЩЕЕ СОСТОЯНИЕ СИСТЕМЫ
    context_parts.append("КОНТЕКСТ СИСТЕМЫ:")
    context_parts.append(f"- Рабочая директория: {session.context.current_working_dir}")
    context_parts.append(f"- Уровень пользователя: {session.metadata.get('user_skill_level', 'beginner')}")

    # 2. АНАЛИЗ ПОСЛЕДНИХ КОМАНД
    recent_events = session.get_recent_events(3)

    if recent_events:
        context_parts.append("\nПОСЛЕДНИЕ КОМАНДЫ:")
        for event in recent_events[-3:]:
            status = "УСПЕХ" if event.status == "SUCCESS" else "ОШИБКА"
            context_parts.append(f"- {event.command} [{status}]")
            if event.output and len(event.output.strip()) < 50 and event.status == "SUCCESS":
                context_parts.append(f"  Результат: {event.output.strip()}")

    # 3. АНАЛИЗ ТЕКУЩЕГО ЗАПРОСА
    prompt_lower = prompt.lower()

    # Определяем тип текущего запроса для лучшего контекста
    if any(word in prompt_lower for word in ['найди', 'поиск', 'find', 'search', 'grep']):
        context_parts.append("\nТИП ЗАПРОСА: ПОИСК")
        context_parts.append("Пользователь ищет файлы или информацию в системе")

    elif any(word in prompt_lower for word in ['создай', 'сделай', 'create', 'make', 'mkdir', 'touch']):
        context_parts.append(f"\nТИП ЗАПРОСА: СОЗДАНИЕ")
        context_parts.append(f"Текущее местоположение: {session.context.current_working_dir}")

    elif any(word in prompt_lower for word in ['удали', 'удалить', 'remove', 'delete', 'rm']):
        context_parts.append("\nТИП ЗАПРОСА: УДАЛЕНИЕ")
        context_parts.append("ВНИМАНИЕ: Это операция удаления - будьте осторожны")

    elif any(word in prompt_lower for word in ['покажи', 'открой', 'show', 'display', 'cat', 'less']):
        context_parts.append("\nТИП ЗАПРОСА: ПРОСМОТР")
        context_parts.append("Пользователь хочет просмотреть содержимое файлов или директорий")

    # 4. УЧЕТ ПРЕДЫДУЩИХ ОШИБОК
    recent_errors = [e for e in recent_events if e.status == "ERROR"]
    if recent_errors:
        context_parts.append("\nПРЕДЫДУЩИЕ ОШИБКИ (избегайте повторения):")
        for error in recent_errors[-2:]:
            error_msg = error.error[:100] + "..." if len(error.error) > 100 else error.error
            context_parts.append(f"- {error.command}")
            context_parts.append(f"  Ошибка: {error_msg}")

    # 5. АДАПТАЦИЯ К УРОВНЮ ПОЛЬЗОВАТЕЛЯ
    user_level = session.metadata.get("user_skill_level", "beginner")
    if user_level == "beginner":
        context_parts.append("\nРЕКОМЕНДАЦИЯ: Используйте простые и безопасные команды")
    elif user_level == "advanced":
        context_parts.append("\nРЕКОМЕНДАЦИЯ: Можно использовать сложные команды (awk, sed, pipes)")

    # Собираем финальный промпт
    context_str = "\n".join(context_parts)

    enhanced_prompt = f"""{context_str}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {prompt}

СГЕНЕРИРУЙТЕ БАШ-КОМАНДУ:"""

    logger.debug(f"Улучшенный промпт (чистый текст): {context_str}")
    return enhanced_prompt


def show_help():
    """Показывает справку с улучшенным форматированием"""
    help_text = f"""
{Fore.CYAN}{'=' * 60}
🆘 СПРАВКА ПО AI-АССИСТЕНТУ (СЕССИИ)
{'=' * 60}{Style.RESET_ALL}

{Fore.GREEN}📌 ОСНОВНЫЕ КОМАНДЫ:{Style.RESET_ALL}
  • Просто опишите что хотите сделать на русском языке
  • Система запоминает контекст между командами
  • Автоматическое сохранение истории

{Fore.YELLOW}🔧 СЛУЖЕБНЫЕ КОМАНДЫ:{Style.RESET_ALL}
  • {Fore.CYAN}help{Style.RESET_ALL}    - показать эту справку
  • {Fore.CYAN}history{Style.RESET_ALL} - показать истории текущей сессии
  • {Fore.CYAN}session{Style.RESET_ALL} - управление сессиями
  • {Fore.CYAN}context{Style.RESET_ALL} - показать контекст из БД
  • {Fore.CYAN}clear{Style.RESET_ALL}   - очистить экран
  • {Fore.CYAN}exit{Style.RESET_ALL}    - выход с сохранением сессии

{Fore.BLUE}💡 СЕССИИ И КОНТЕКСТ:{Style.RESET_ALL}
  • Каждая сессия сохраняет историю и контекст
  • Автоматическое определение уровня пользователя
  • Сохранение рабочей директории
  • Статистика успешности команд

{Fore.MAGENTA}📊 ЛОГИРОВАНИЕ:{Style.RESET_ALL}
  • Сессии сохраняются в {Fore.CYAN}sessions/{Style.RESET_ALL}
  • Полная история всех взаимодействий
  • Возможность переключения между сессиями

{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}
"""
    print(help_text)


def show_session_history(session: Session):
    """Показывает историю текущей сессии"""
    if not session.events:
        print(f"{Fore.YELLOW}📭 История пуста")
        return

    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"📜 ИСТОРИЯ СЕССИИ {session.id[:8]}... ({len(session.events)} команд)")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")

    for i, event in enumerate(session.events[-10:], 1):  # Последние 10 команд
        status_icon = {
            "SUCCESS": f"{Fore.GREEN}✅",
            "ERROR": f"{Fore.RED}❌",
            "BLOCKED": f"{Fore.RED}🚨",
            "CANCELLED": f"{Fore.YELLOW}⏭️",
            "GENERATION_ERROR": f"{Fore.RED}🤖",
            "SYSTEM_ERROR": f"{Fore.RED}💥"
        }
        icon = status_icon.get(event.status, "")

        time_str = event.timestamp.strftime("%H:%M:%S")
        print(f"{icon} {Fore.WHITE}[{i}]{Style.RESET_ALL} {Fore.CYAN}{event.query}{Style.RESET_ALL}")
        print(f"    → {Fore.YELLOW}{event.command}{Style.RESET_ALL}")
        print(f"    [{event.status}] в {time_str}")
        if event.execution_time:
            print(f"    ⏱️ {event.execution_time:.2f}с\n")
        else:
            print()

    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")