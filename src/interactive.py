# interactive.py - Интерактивный режим 

import logging
from llm_client import generate_command
from executor import run_command

logger = logging.getLogger(__name__)

def interactive_loop():
    """Основной цикл интерактивного режима."""
    logger.info("Запуск интерактивного режима")
    print("🤖 Запущен интерактивный режим AI-ассистента")
    print("💬 Введите 'exit' или 'quit' для выхода")
    print("📝 Введите 'help' для получения помощи")
    print("-" * 50)
    
    while True:
        try:
            prompt = input("AIask> ").strip()
            
            if prompt.lower() in ("exit", "quit", "q"):
                logger.info("Выход из интерактивного режима по команде пользователя")
                print("👋 До свидания!")
                break
                
            if prompt.lower() == "help":
                show_help()
                continue
                
            if not prompt:
                continue
                
            logger.info(f"Обработка запроса в интерактивном режиме: {prompt}")
            
            # Генерируем команду
            resp = generate_command(prompt)
            cmd, expl = resp["command"], resp.get("explanation", "")
            
            if not cmd:
                print("❌ Не удалось сгенерировать команду. Попробуйте переформулировать запрос.")
                logger.warning("Не удалось сгенерировать команду в интерактивном режиме")
                continue
                
            print(f"🤖 Команда: {cmd}")
            if expl:
                print(f"💡 Объяснение: {expl}")
                
            # Подтверждение выполнения
            confirm = input("Выполнить? [y/N]: ").strip().lower()
            
            if confirm in ('y', 'yes', 'да'):
                logger.info("Пользователь подтвердил выполнение в интерактивном режиме")
                code, out, err = run_command(cmd)
                
                if code == 0:
                    print("✅ Команда выполнена успешно")
                    if out.strip():  # Показываем только непустой вывод
                        print(out)
                else:
                    print(f"❌ Ошибка выполнения (код {code})")
                    if err.strip():
                        print(f"Ошибка: {err}")
            else:
                logger.info("Пользователь отменил выполнение в интерактивном режиме")
                print("⏭️ Выполнение пропущено")
                
        except KeyboardInterrupt:
            logger.info("Прерывание работы через Ctrl+C")
            print("\n👋 Выход по прерыванию...")
            break
            
        except Exception as e:
            logger.exception(f"Неожиданная ошибка в интерактивном режиме: {e}")
            print(f"❌ Произошла ошибка: {e}")
            print("🔄 Продолжаем работу...")

def show_help():
    """Показывает справку по использованию."""
    help_text = """
🆘 Справка по AI-ассистенту:

📌 Основные команды:
  • Просто опишите что хотите сделать на русском языке
  • Примеры: "создать папку test", "показать процессы", "найти файлы .txt"
  
🔧 Служебные команды:
  • help - показать эту справку  
  • exit, quit, q - выход из программы
  • Ctrl+C - экстренный выход
  
⚠️ Безопасность:
  • Опасные команды автоматически блокируются
  • Всегда проверяйте команду перед подтверждением
  • Команды выполняются от имени текущего пользователя
  
💡 Советы:
  • Будьте конкретны в описании задачи
  • Указывайте имена файлов и путей если нужно
  • При ошибке попробуйте переформулировать запрос

📊 Логирование:
  • Все действия записываются в файл logs/aiask.log
    """
    print(help_text)