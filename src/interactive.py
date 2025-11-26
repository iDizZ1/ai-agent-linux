# interactive.py 

import logging
import os
import time
from colorama import Fore, Style, init
from llm_client import generate_command
from executor import (
    run_command, is_dangerous_command, categorize_command, CommandCategory,
    is_direct_command, CommandExecutor, get_global_executor
)
from session_manager import session_manager, Session


# Инициализация colorama для цветного вывода
init(autoreset=True)


logger = logging.getLogger(__name__)


def interactive_loop():
    """
    Главный интерактивный цикл с поддержкой сессий и многошаговых команд
    """
    restart_required = False

    while True:
        if restart_required:
            session = session_manager.get_or_create_current_session()
            restart_required = False
            print(f"{Fore.CYAN}🔄 Перезапуск с сессией: {session.id[:8]}...")
        else:
            session = session_manager.get_or_create_current_session()

        if not hasattr(session, '_executor'):
            session._executor = CommandExecutor()
        
        executor = session._executor

        logger.info(f"Запуск интерактивного режима для сессии: {session.id}")

        print(f"{Fore.CYAN}🤖 Запущен интерактивный режим AI-ассистента")
        print(f"{Fore.GREEN}📁 Сессия: {session.id[:8]}...")
        print(f"{Fore.YELLOW}🔧 Введите bash команду - без обращения к llm")
        print(f"{Fore.YELLOW}💬 Введите 'exit' или 'quit' для выхода")
        print(f"{Fore.YELLOW}📝 Введите 'help' для получения помощи")
        print(f"{Fore.YELLOW}📊 Введите 'history' для просмотра истории текущей сессии")
        print(f"{Fore.YELLOW}🎓 Введите 'session' для управления сессиями")
        print("-" * 50)

        session_exit = False

        while not session_exit and not restart_required:
            try:
                current_dir = executor.get_current_directory()
                short_dir = current_dir if len(current_dir) <= 30 else "..." + current_dir[-27:]
                
                prompt = input(f"{Fore.GREEN}AIask[{session.id[:8]}:{short_dir}]> {Style.RESET_ALL}").strip()

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
                        break
                    continue

                if prompt.lower() == "clear":
                    os.system('clear' if os.name != 'nt' else 'cls')
                    continue

                if not prompt:
                    continue

                logger.info(f"Обработка запроса: {prompt}")

                # Автоматический детектор команд
                if is_direct_command(prompt):
                    # Прямая bash команда
                    handle_direct_command(prompt, executor, session)
                else:
                    # AI запрос
                    handle_ai_request(prompt, executor, session)

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
            break


def handle_direct_command(cmd: str, executor: CommandExecutor, session: Session):
    """Обрабатывает прямую bash команду"""
    logger.info(f"Прямая bash команда: {cmd}")

    if is_dangerous_command(cmd):
        print(f"{Fore.RED}🚨 ОПАСНАЯ КОМАНДА ЗАБЛОКИРОВАНА!")
        print(f"{Fore.YELLOW}Команда: {cmd}")
        print(f"{Fore.RED}⛔ Эта команда может нанести серьезный вред системе.")
        logger.warning(f"Заблокирована опасная команда: {cmd}")
        session.add_event(cmd, cmd, "BLOCKED")
        session_manager.save_session(session.id)
        return

    category = categorize_command(cmd)
    category_icon = {
        CommandCategory.SAFE: f"{Fore.GREEN}✓",
        CommandCategory.WRITE: f"{Fore.YELLOW}✎",
        CommandCategory.DANGEROUS: f"{Fore.MAGENTA}⚠",
        CommandCategory.CRITICAL: f"{Fore.RED}⛔",
        CommandCategory.BUILTIN: f"{Fore.CYAN}⚙"
    }

    print(f"{Fore.CYAN}🔧 Команда: {Fore.WHITE}{cmd} {category_icon.get(category, '')}")

    confirm = input(f"{Fore.YELLOW}Выполнить? [y/N]: {Style.RESET_ALL}").strip().lower()

    if confirm in ('y', 'yes', 'да'):
        logger.info("Пользователь подтвердил выполнение")

        start_time = time.time()
        code, out, err = run_command(cmd, executor)
        execution_time = time.time() - start_time

        if code == 0:
            print(f"{Fore.GREEN}✅ Команда выполнена успешно")
            if out.strip():
                print(f"{Style.RESET_ALL}{out}")

            session.update_context_from_executor(executor)
            session.add_event(cmd, cmd, "SUCCESS", out, None, execution_time)
        else:
            if "превышен лимит времени" in err.lower() or "timeout" in err.lower():
                print(f"{Fore.YELLOW}⏱️ Команда не завершилась вовремя (timeout)")
            else:
                print(f"{Fore.RED}❌ Ошибка выполнения (код {code})")
            if err.strip():
                print(f"{Fore.RED}Детали: {err}")
            session.add_event(cmd, cmd, "ERROR", out, err, execution_time)

        session_manager.save_session(session.id)
    else:
        logger.info("Пользователь отменил выполнение")
        print(f"{Fore.YELLOW}⏭️ Выполнение пропущено")
        session.add_event(cmd, cmd, "CANCELLED")


def handle_ai_request(prompt: str, executor: CommandExecutor, session: Session):
    """Обрабатывает запрос к AI"""
    logger.info(f"AI запрос: {prompt}")

    enhanced_prompt = enhance_prompt_with_context(prompt, session, executor)
    resp = generate_command(enhanced_prompt)

    if not resp or not isinstance(resp, dict):
        print(f"{Fore.RED}❌ Ошибка: AI не вернул корректный ответ")
        logger.error(f"Некорректный ответ от generate_command: {resp}")
        session.add_event(prompt, "", "AI_ERROR")
        return

    # ✨ НОВОЕ: Проверяем есть ли несколько команд
    if 'commands' in resp and resp.get('commands'):
        # Многошаговые команды!
        handle_multi_commands(resp['commands'], resp.get('explanations', []), 
                            prompt, executor, session)
    else:
        # Одиночная команда
        handle_single_command(resp, prompt, executor, session)


def handle_single_command(resp: dict, original_prompt: str, 
                         executor: CommandExecutor, session: Session):
    """Обрабатывает одиночную команду"""
    cmd = resp.get("command", "")
    expl = resp.get("explanation", "")

    if not cmd:
        print(f"{Fore.RED}❌ Не удалось сгенерировать команду. Попробуйте переформулировать запрос.")
        if expl:
            print(f"{Fore.YELLOW}💡 AI сообщение: {expl}")
        logger.warning("Не удалось сгенерировать команду")
        session.add_event(original_prompt, "", "GENERATION_ERROR")
        return

    if is_dangerous_command(cmd):
        print(f"{Fore.RED}🚨 ОПАСНАЯ КОМАНДА ЗАБЛОКИРОВАНА!")
        print(f"{Fore.YELLOW}Команда: {cmd}")
        print(f"{Fore.RED}⛔ Эта команда может нанести серьезный вред системе.")
        logger.warning(f"Заблокирована опасная команда: {cmd}")
        session.add_event(original_prompt, cmd, "BLOCKED")
        session_manager.save_session(session.id)
        return

    category = categorize_command(cmd)
    category_icon = {
        CommandCategory.SAFE: f"{Fore.GREEN}✓",
        CommandCategory.WRITE: f"{Fore.YELLOW}✎",
        CommandCategory.DANGEROUS: f"{Fore.MAGENTA}⚠",
        CommandCategory.CRITICAL: f"{Fore.RED}⛔",
        CommandCategory.BUILTIN: f"{Fore.CYAN}⚙"
    }

    print(f"{Fore.CYAN}🤖 Команда: {Fore.WHITE}{cmd} {category_icon.get(category, '')}")
    if expl:
        print(f"{Fore.BLUE}💡 Объяснение: {expl}")

    confirm = input(f"{Fore.YELLOW}Выполнить? [y/N]: {Style.RESET_ALL}").strip().lower()

    if confirm in ('y', 'yes', 'да'):
        logger.info("Пользователь подтвердил выполнение")

        start_time = time.time()
        code, out, err = run_command(cmd, executor)
        execution_time = time.time() - start_time

        if code == 0:
            print(f"{Fore.GREEN}✅ Команда выполнена успешно")
            if out.strip():
                print(f"{Style.RESET_ALL}{out}")

            session.update_context_from_executor(executor)
            session.add_event(original_prompt, cmd, "SUCCESS", out, None, execution_time)
        else:
            if "превышен лимит времени" in err.lower() or "timeout" in err.lower():
                print(f"{Fore.YELLOW}⏱️ Команда не завершилась вовремя (timeout)")
            else:
                print(f"{Fore.RED}❌ Ошибка выполнения (код {code})")
            if err.strip():
                print(f"{Fore.RED}Детали: {err}")
            session.add_event(original_prompt, cmd, "ERROR", out, err, execution_time)

        session_manager.save_session(session.id)
    else:
        logger.info("Пользователь отменил выполнение")
        print(f"{Fore.YELLOW}⏭️ Выполнение пропущено")
        session.add_event(original_prompt, cmd, "CANCELLED")


def handle_multi_commands(commands: list, explanations: list, original_prompt: str,
                         executor: CommandExecutor, session: Session):
    """Обрабатывает несколько команд с выбором режима выполнения"""
    logger.info(f"Многошаговые команды: {len(commands)} команд")

    # Показываем все команды
    print(f"\n{Fore.CYAN}🔍 Найдено {len(commands)} команд для выполнения:\n")

    for i, cmd in enumerate(commands, 1):
        category = categorize_command(cmd)
        category_icon = {
            CommandCategory.SAFE: f"{Fore.GREEN}✓",
            CommandCategory.WRITE: f"{Fore.YELLOW}✎",
            CommandCategory.DANGEROUS: f"{Fore.MAGENTA}⚠",
            CommandCategory.CRITICAL: f"{Fore.RED}⛔",
            CommandCategory.BUILTIN: f"{Fore.CYAN}⚙"
        }
        print(f"{Fore.WHITE}{i}. {cmd} {category_icon.get(category, '')}")

    # Проверяем безопасность всех команд
    dangerous_cmds = [cmd for cmd in commands if is_dangerous_command(cmd)]
    if dangerous_cmds:
        print(f"\n{Fore.RED}🚨 ОПАСНЫЕ КОМАНДЫ НАЙДЕНЫ:")
        for cmd in dangerous_cmds:
            print(f"  {Fore.RED}⛔ {cmd}")
        print(f"{Fore.RED}Выполнение отменено.")
        session.add_event(original_prompt, "; ".join(commands), "BLOCKED")
        session_manager.save_session(session.id)
        return

    # Меню выбора
    print(f"\n{Fore.CYAN}Как выполнить?")
    print(f"{Fore.GREEN}[1]{Style.RESET_ALL} Выполнить все сразу (быстро)")
    print(f"{Fore.GREEN}[2]{Style.RESET_ALL} Выполнить пошагово (с подтверждением)")
    print(f"{Fore.GREEN}[3]{Style.RESET_ALL} Отменить выполнение")

    choice = input(f"\n{Fore.YELLOW}> {Style.RESET_ALL}").strip()

    if choice == "1":
        # Выполнить все сразу
        execute_all_commands(commands, explanations, original_prompt, executor, session)
    elif choice == "2":
        # Выполнить пошагово
        execute_stepwise_commands(commands, explanations, original_prompt, executor, session)
    elif choice == "3":
        # Отменить
        print(f"{Fore.YELLOW}⏭️ Выполнение отменено")
        session.add_event(original_prompt, "; ".join(commands), "CANCELLED")
    else:
        print(f"{Fore.YELLOW}❓ Неверный выбор")


def execute_all_commands(commands: list, explanations: list, original_prompt: str,
                        executor: CommandExecutor, session: Session):
    """Выполняет все команды без подтверждения"""
    print(f"\n{Fore.CYAN}⚡ Выполнение всех команд...\n")

    start_time = time.time()
    successful = 0
    failed = 0
    all_outputs = []

    for i, cmd in enumerate(commands, 1):
        print(f"{Fore.WHITE}[{i}/{len(commands)}] {cmd}")

        code, out, err = run_command(cmd, executor)

        if code == 0:
            print(f"{Fore.GREEN}✅ Успешно")
            successful += 1
            if out.strip():
                print(f"{Style.RESET_ALL}{out}")
            all_outputs.append(out)
        else:
            print(f"{Fore.RED}❌ Ошибка (код {code})")
            failed += 1
            if err.strip():
                print(f"{Fore.RED}{err}")
            all_outputs.append(err)

    execution_time = time.time() - start_time

    # Итоговая статистика
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"✅ Успешно: {successful}/{len(commands)}")
    print(f"❌ Ошибок: {failed}/{len(commands)}")
    print(f"⏱️ Время: {execution_time:.2f}с")
    print(f"{Fore.CYAN}{'='*50}\n")

    session.update_context_from_executor(executor)
    session.add_event(original_prompt, "; ".join(commands), 
                     "SUCCESS" if failed == 0 else "PARTIAL_ERROR",
                     "\n".join(all_outputs), None, execution_time)
    session_manager.save_session(session.id)


def execute_stepwise_commands(commands: list, explanations: list, original_prompt: str,
                             executor: CommandExecutor, session: Session):
    """Выполняет команды пошагово с подтверждением"""
    print(f"\n{Fore.CYAN}🔄 Пошаговое выполнение\n")

    start_time = time.time()
    successful = 0
    failed = 0
    skipped = 0
    all_outputs = []

    for i, cmd in enumerate(commands, 1):
        print(f"{Fore.WHITE}[{i}/{len(commands)}] {cmd}")
        if i <= len(explanations) and explanations[i-1]:
            print(f"{Fore.BLUE}💡 {explanations[i-1]}")

        confirm = input(f"{Fore.YELLOW}Выполнить? [y/N]: {Style.RESET_ALL}").strip().lower()

        if confirm not in ('y', 'yes', 'да'):
            print(f"{Fore.YELLOW}⏭️ Пропущено\n")
            skipped += 1
            continue

        code, out, err = run_command(cmd, executor)

        if code == 0:
            print(f"{Fore.GREEN}✅ Успешно")
            successful += 1
            if out.strip():
                print(f"{Style.RESET_ALL}{out}")
            all_outputs.append(out)
        else:
            print(f"{Fore.RED}❌ Ошибка (код {code})")
            failed += 1
            if err.strip():
                print(f"{Fore.RED}{err}")
            all_outputs.append(err)

        print()

    execution_time = time.time() - start_time

    # Итоговая статистика
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"✅ Успешно: {successful}/{len(commands)}")
    print(f"❌ Ошибок: {failed}/{len(commands)}")
    print(f"⏭️ Пропущено: {skipped}/{len(commands)}")
    print(f"⏱️ Время: {execution_time:.2f}с")
    print(f"{Fore.CYAN}{'='*50}\n")

    session.update_context_from_executor(executor)
    status = "SUCCESS" if failed == 0 else "PARTIAL_ERROR"
    session.add_event(original_prompt, "; ".join(commands), status,
                     "\n".join(all_outputs), None, execution_time)
    session_manager.save_session(session.id)


def handle_session_commands(session: Session) -> bool:
    """Обрабатывает команды управления сессиями"""
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
        return False

    if command == "list":
        sessions_list = session_manager.list_sessions()
        print(f"\n{Fore.CYAN}📋 СЕССИИ:")
        for s in sessions_list:
            current_flag = " ← текущая" if s['is_current'] else ""
            print(
                f"  {s['id']} - {s['event_count']} команд, обновлена: {s['updated_at'].strftime('%H:%M')}{current_flag}")
        return False

    elif command == "new":
        session_manager.save_session(session.id)
        new_session = session_manager.create_session()
        print(f"{Fore.GREEN}✅ Создана новая сессия: {new_session.id}")
        session_manager.switch_session(new_session.id)
        return True

    elif command == "save":
        session_manager.save_session(session.id)
        print(f"{Fore.GREEN}✅ Сессия сохранена")
        return False

    elif command.startswith("switch "):
        session_manager.save_session(session.id)
        target_id = command[7:].strip()

        if target_id in session_manager.sessions:
            if session_manager.switch_session(target_id):
                print(f"{Fore.GREEN}✅ Переключено на сессию: {target_id}")
                return True
            else:
                print(f"{Fore.RED}❌ Ошибка переключения")
                return False
        else:
            matching_sessions = []
            for session_id in session_manager.sessions.keys():
                if session_id.startswith(target_id):
                    matching_sessions.append(session_id)

            if len(matching_sessions) == 1:
                full_id = matching_sessions[0]
                if session_manager.switch_session(full_id):
                    print(f"{Fore.GREEN}✅ Переключено на сессию: {full_id}")
                    return True
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
        target_session = None
        if target_id in session_manager.sessions:
            target_session = session_manager.sessions[target_id]
        else:
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

        if target_id == session.id or target_id == session.id[:8]:
            print(f"{Fore.RED}❌ Нельзя удалить текущую сессию!")
            print(f"{Fore.YELLOW}💡 Переключитесь на другую сессию сначала")
            return False

        session_to_delete = None
        if target_id in session_manager.sessions:
            session_to_delete = target_id
        else:
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
                session_file = session_manager.storage_path / f"{session_to_delete}.json"
                if session_file.exists():
                    os.remove(session_file)

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


def enhance_prompt_with_context(prompt: str, session: Session, executor: CommandExecutor) -> str:
    """Улучшает промпт с контекстом сессии"""
    context_parts = []

    context_parts.append("КОНТЕКСТ СИСТЕМЫ:")
    context_parts.append(f"- Рабочая директория: {executor.get_current_directory()}")
    context_parts.append(f"- Уровень пользователя: {session.metadata.get('user_skill_level', 'beginner')}")

    recent_events = session.get_recent_events(3)

    if recent_events:
        context_parts.append("\nПОСЛЕДНИЕ КОМАНДЫ:")
        for event in recent_events[-3:]:
            status = "УСПЕХ" if event.status == "SUCCESS" else "ОШИБКА"
            context_parts.append(f"- {event.command} [{status}]")
            if event.output and len(event.output.strip()) < 50 and event.status == "SUCCESS":
                context_parts.append(f"  Результат: {event.output.strip()}")

    prompt_lower = prompt.lower()

    if any(word in prompt_lower for word in ['найди', 'поиск', 'find', 'search', 'grep']):
        context_parts.append("\nТИП ЗАПРОСА: ПОИСК")

    elif any(word in prompt_lower for word in ['создай', 'сделай', 'create', 'make', 'mkdir', 'touch']):
        context_parts.append(f"\nТИП ЗАПРОСА: СОЗДАНИЕ")
        context_parts.append(f"Текущее местоположение: {executor.get_current_directory()}")

    context_str = "\n".join(context_parts)

    enhanced_prompt = f"""{context_str}


ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {prompt}


СГЕНЕРИРУЙТЕ БАШ-КОМАНДУ (ИЛИ НЕСКОЛЬКО КОМАНД ЕСЛИ НУЖНО):"""

    logger.debug(f"Улучшенный промпт: {context_str}")
    return enhanced_prompt


def show_help():
    """Показывает справку"""
    help_text = f"""
{Fore.CYAN}{'=' * 60}
🆘 СПРАВКА ПО AI-АССИСТЕНТУ
{'=' * 60}{Style.RESET_ALL}


{Fore.GREEN}📌 ОСНОВНЫЕ КОМАНДЫ:{Style.RESET_ALL}
  • Вводите прямые bash команды: ls -la, mkdir test, cd /tmp и т.д.
  • Опишите что хотите на русском языке - AI сгенерирует команду
  • Система запоминает контекст между командами


{Fore.YELLOW}🔧 СЛУЖЕБНЫЕ КОМАНДЫ:{Style.RESET_ALL}
  • {Fore.CYAN}help{Style.RESET_ALL}    - показать эту справку
  • {Fore.CYAN}history{Style.RESET_ALL} - показать историю текущей сессии
  • {Fore.CYAN}session{Style.RESET_ALL} - управление сессиями
  • {Fore.CYAN}clear{Style.RESET_ALL}   - очистить экран
  • {Fore.CYAN}exit{Style.RESET_ALL}    - выход с сохранением сессии


{Fore.BLUE}💡 МНОГОШАГОВЫЕ КОМАНДЫ:{Style.RESET_ALL}
  AIask> создай папку gdrrig, перейди в нее и там создай 2 файла
  
  🔍 Найдено 4 команды для выполнения:
  1. mkdir gdrrig ✎
  2. cd gdrrig ⚙
  3. touch file1.txt ✎
  4. touch file2.txt ✎
  
  Как выполнить?
  [1] Выполнить все сразу (быстро)
  [2] Выполнить пошагово (с подтверждением)
  [3] Отменить выполнение


{Fore.MAGENTA}📊 СЕССИИ И КОНТЕКСТ:{Style.RESET_ALL}
  • Каждая сессия сохраняет историю и контекст
  • Автоматическое определение уровня пользователя
  • Сохранение рабочей директории (поддержка cd)
  • Статистика успешности команд


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

    for i, event in enumerate(session.events[-10:], 1):
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
