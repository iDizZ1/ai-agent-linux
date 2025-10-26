# interactive.py - Интерактивный режим

import logging
from colorama import Fore, Style, init
from llm_client import generate_command
from executor import run_command, is_dangerous_command, categorize_command, CommandCategory

# Инициализация colorama для цветного вывода
init(autoreset=True)

logger = logging.getLogger(__name__)

# Временная история команд (без БД)
session_history = []

def interactive_loop():
    """Основной цикл интерактивного режима с улучшенным UX (ЭТАП 2.3)"""
    logger.info("Запуск интерактивного режима")
    
    print(f"{Fore.CYAN}🤖 Запущен интерактивный режим AI-ассистента")
    print(f"{Fore.YELLOW}💬 Введите 'exit' или 'quit' для выхода")
    print(f"{Fore.YELLOW}📝 Введите 'help' для получения помощи")
    print(f"{Fore.YELLOW}📊 Введите 'history' для просмотра истории текущей сессии")
    print("-" * 50)
    
    while True:
        try:
            prompt = input(f"{Fore.GREEN}AIask> {Style.RESET_ALL}").strip()
            
            if prompt.lower() in ("exit", "quit", "q"):
                logger.info("Выход из интерактивного режима")
                print(f"{Fore.CYAN}👋 До свидания!")
                break
                
            if prompt.lower() == "help":
                show_help()
                continue
                
            if prompt.lower() == "history":
                show_session_history()
                continue
                
            if prompt.lower() == "clear":
                import os
                os.system('clear' if os.name != 'nt' else 'cls')
                continue
                
            if not prompt:
                continue
                
            logger.info(f"Обработка запроса: {prompt}")
            
            # Генерируем команду
            resp = generate_command(prompt)
            cmd, expl = resp["command"], resp.get("explanation", "")
            
            if not cmd:
                print(f"{Fore.RED}❌ Не удалось сгенерировать команду. Попробуйте переформулировать запрос.")
                logger.warning("Не удалось сгенерировать команду")
                continue
            
            # Проверка безопасности ДО вывода 
            if is_dangerous_command(cmd):
                print(f"{Fore.RED}🚨 ОПАСНАЯ КОМАНДА ЗАБЛОКИРОВАНА!")
                print(f"{Fore.YELLOW}Команда: {cmd}")
                print(f"{Fore.RED}⛔ Эта команда может нанести серьезный вред системе.")
                logger.warning(f"Заблокирована опасная команда: {cmd}")
                session_history.append({"query": prompt, "command": cmd, "status": "BLOCKED"})
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
                code, out, err = run_command(cmd)
                
                if code == 0:
                    print(f"{Fore.GREEN}✅ Команда выполнена успешно")
                    if out.strip():
                        print(f"{Style.RESET_ALL}{out}")
                    session_history.append({"query": prompt, "command": cmd, "status": "SUCCESS"})
                else:
                    if "превышен лимит времени" in err.lower() or "timeout" in err.lower():
                        print(f"{Fore.YELLOW}⏱️ Команда не завершилась вовремя (timeout)")
                    else:
                        print(f"{Fore.RED}❌ Ошибка выполнения (код {code})")
                    if err.strip():
                        print(f"{Fore.RED}Детали: {err}")
                    session_history.append({"query": prompt, "command": cmd, "status": "ERROR"})
            else:
                logger.info("Пользователь отменил выполнение")
                print(f"{Fore.YELLOW}⏭️ Выполнение пропущено")
                session_history.append({"query": prompt, "command": cmd, "status": "CANCELLED"})
                
        except KeyboardInterrupt:
            logger.info("Прерывание через Ctrl+C")
            print(f"\n{Fore.CYAN}👋 Выход по прерыванию...")
            break
            
        except Exception as e:
            logger.exception(f"Ошибка в интерактивном режиме: {e}")
            print(f"{Fore.RED}❌ Произошла ошибка: {e}")
            print(f"{Fore.YELLOW}🔄 Продолжаем работу...")

def show_help():
    """Показывает справку с улучшенным форматированием """
    help_text = f"""
{Fore.CYAN}{'=' * 60}
🆘 СПРАВКА ПО AI-АССИСТЕНТУ
{'=' * 60}{Style.RESET_ALL}

{Fore.GREEN}📌 ОСНОВНЫЕ КОМАНДЫ:{Style.RESET_ALL}
  • Просто опишите что хотите сделать на русском языке
  • Примеры:
    - "создать папку test"
    - "показать процессы"
    - "найти файлы .txt"
    - "посчитать строки в файле"

{Fore.YELLOW}🔧 СЛУЖЕБНЫЕ КОМАНДЫ:{Style.RESET_ALL}
  • {Fore.CYAN}help{Style.RESET_ALL}    - показать эту справку
  • {Fore.CYAN}history{Style.RESET_ALL} - показать историю текущей сессии
  • {Fore.CYAN}clear{Style.RESET_ALL}   - очистить экран
  • {Fore.CYAN}exit{Style.RESET_ALL}    - выход из программы (также: quit, q)
  • {Fore.CYAN}Ctrl+C{Style.RESET_ALL}  - экстренный выход

{Fore.RED}⚠️  БЕЗОПАСНОСТЬ:{Style.RESET_ALL}
  • Опасные команды {Fore.RED}автоматически блокируются{Style.RESET_ALL}
  • Блокировка происходит {Fore.RED}ДО{Style.RESET_ALL} запроса подтверждения
  • Категории команд:
    {Fore.GREEN}✓{Style.RESET_ALL} Безопасные (read-only)
    {Fore.YELLOW}✎{Style.RESET_ALL} Изменяющие файлы
    {Fore.MAGENTA}⚠{Style.RESET_ALL} Потенциально опасные
    {Fore.RED}⛔{Style.RESET_ALL} Критически опасные (блокируются)

{Fore.BLUE}💡 СОВЕТЫ:{Style.RESET_ALL}
  • Будьте конкретны в описании задачи
  • Указывайте имена файлов и путей
  • При ошибке попробуйте переформулировать
  • Всегда проверяйте команду перед подтверждением

{Fore.MAGENTA}📊 ЛОГИРОВАНИЕ:{Style.RESET_ALL}
  • Все действия записываются в {Fore.CYAN}logs/aiask.log{Style.RESET_ALL}
  • Опасные команды логируются с уровнем WARNING
  • Ошибки логируются с полным traceback

{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}
"""
    print(help_text)

def show_session_history():
    """Показывает историю команд текущей сессии (ЭТАП 2.3)"""
    if not session_history:
        print(f"{Fore.YELLOW}📭 История пуста")
        return
    
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"📜 ИСТОРИЯ ТЕКУЩЕЙ СЕССИИ ({len(session_history)} команд)")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")
    
    for i, entry in enumerate(session_history, 1):
        status_icon = {
            "SUCCESS": f"{Fore.GREEN}✅",
            "ERROR": f"{Fore.RED}❌",
            "BLOCKED": f"{Fore.RED}🚨",
            "CANCELLED": f"{Fore.YELLOW}⏭️"
        }
        icon = status_icon.get(entry["status"], "")
        
        print(f"{icon} {Fore.WHITE}[{i}]{Style.RESET_ALL} {Fore.CYAN}{entry['query']}{Style.RESET_ALL}")
        print(f"    → {Fore.YELLOW}{entry['command']}{Style.RESET_ALL}")
        print(f"    [{entry['status']}]\n")
    
    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")