from datetime import datetime
import typer
import logging
import os
import sys

from config import setup_logging
from llm_client import generate_command, test_ollama_connection
from executor import run_command, is_dangerous_command, CommandExecutor, get_global_executor
from session_manager import session_manager
from interactive import interactive_loop

# Инициализируем логирование
setup_logging()
logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="🤖 AI ассистент для генерации bash команд с поддержкой RAG"
)


@app.command()
def ask(query: str = typer.Argument(..., help="Запрос на естественном языке")):
    """
    Отправить один запрос к LLM и выполнить сгенерированную команду.

    Примеры:
        aiask "создай папку test"
        aiask "найди все python файлы"
        aiask "покажи размер директории"
    """
    logger.info(f"🎯 Режим одиночного запроса: {query}")

    # Создаем временную сессию для одиночного запроса
    session = session_manager.create_session(
        f"single_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    executor = get_global_executor()

    try:
        # Улучшаем промпт контекстом
        enhanced_prompt = f"""ЗАПРОС: {query}

КОНТЕКСТ:
- Рабочая директория: {executor.get_current_directory()}

Сгенерируй bash-команду для выполнения."""

        logger.debug(f"Отправка промпта к LLM: {enhanced_prompt}")

        # Генерируем команду
        resp = generate_command(enhanced_prompt)

        if not resp or not isinstance(resp, dict):
            typer.echo(f"❌ Ошибка: AI не вернул корректный ответ")
            logger.error(f"Некорректный ответ: {resp}")
            session.add_event(query, "", "AI_ERROR")
            session_manager.save_session(session.id)
            return

        cmd = resp.get("command", "")
        expl = resp.get("explanation", "")

        if not cmd:
            typer.echo("❌ Не удалось сгенерировать команду. Проверьте подключение к LLM.")
            logger.error("Команда не сгенерирована")
            session.add_event(query, "", "GENERATION_ERROR")
            session_manager.save_session(session.id)
            return

        # ✅ ПРОВЕРКА БЕЗОПАСНОСТИ ДО ВЫВОДА
        if is_dangerous_command(cmd):
            typer.echo(f"\n🚨 ОПАСНАЯ КОМАНДА ЗАБЛОКИРОВАНА!")
            typer.echo(f"   Команда: {cmd}")
            typer.echo(f"   ⛔ Эта команда может нанести серьезный вред системе")
            logger.warning(f"Заблокирована опасная команда: {cmd}")
            session.add_event(query, cmd, "BLOCKED")
            session_manager.save_session(session.id)
            return

        # Показываем сгенерированную команду
        typer.echo(f"\n🤖 Команда: {typer.style(cmd, fg=typer.colors.CYAN, bold=True)}")
        if expl:
            typer.echo(f"💡 Объяснение: {expl}")

        # Запрашиваем подтверждение
        if typer.confirm("\n✓ Выполнить?", default=False):
            logger.info("Пользователь подтвердил выполнение")

            code, out, err = run_command(cmd, executor)

            if code == 0:
                typer.echo(typer.style("✅ Команда выполнена успешно\n", fg=typer.colors.GREEN))
                if out.strip():
                    typer.echo(out)
                session.add_event(query, cmd, "SUCCESS", out, None)
            else:
                if "timeout" in err.lower():
                    typer.echo(f"⏱️ Команда не завершилась вовремя (timeout)")
                else:
                    typer.echo(typer.style(f"❌ Ошибка выполнения (код {code})", fg=typer.colors.RED))
                    if err.strip():
                        typer.echo(f"📋 {err}")
                session.add_event(query, cmd, "ERROR", out, err)
        else:
            logger.info("Пользователь отменил выполнение")
            typer.echo(typer.style("⏭️ Выполнение отменено\n", fg=typer.colors.YELLOW))
            session.add_event(query, cmd, "CANCELLED")

        session_manager.save_session(session.id)

    except Exception as e:
        logger.exception(f"Ошибка в режиме одиночного запроса: {e}")
        session.add_event(query, "", "SYSTEM_ERROR", error=str(e))
        session_manager.save_session(session.id)
        raise


@app.command()
def interactive():
    """
    Запустить интерактивный режим.

    В интерактивном режиме вы можете:
    - Вводить bash команды напрямую
    - Делать запросы на русском языке
    - Работать с многошаговыми командами
    - Управлять сессиями

    Примеры команд:
        ls -la           (прямая bash команда)
        создай папку    (запрос на русском)
        help            (справка)
        history         (история сессии)
        exit            (выход)
    """
    logger.info("🎯 Запуск интерактивного режима")
    interactive_loop()


@app.command()
def check():
    """
    Проверить подключение к компонентам системы.
    """
    logger.info("🔍 Проверка системы")

    typer.echo("\n" + typer.style("=" * 50, fg=typer.colors.CYAN))
    typer.echo(typer.style("🔍 ПРОВЕРКА КОМПОНЕНТОВ СИСТЕМЫ", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 50 + "\n", fg=typer.colors.CYAN))

    # 1. Проверка Ollama
    typer.echo("1️⃣  Проверка подключения к Ollama...")
    if test_ollama_connection():
        typer.echo(typer.style("   ✅ Ollama доступна\n", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("   ❌ Ollama недоступна\n", fg=typer.colors.RED))
        logger.error("Ollama недоступна")

    # 2. Проверка базы знаний
    typer.echo("2️⃣  Проверка базы знаний...")
    # Ищем в той же директории, где лежит модуль
    module_dir = os.path.dirname(os.path.abspath(__file__))
    kb_file = os.path.join(module_dir, "bash_knowledge_base.md")

    if os.path.exists(kb_file):
        with open(kb_file, 'r', encoding='utf-8') as f:
            lines = len(f.readlines())
        typer.echo(typer.style(f"   OK База знаний найдена ({lines} строк)\n", fg=typer.colors.GREEN))
    else:
        # Пытаемся найти в рабочей директории
        alt_kb_file = "bash_knowledge_base.md"
        if os.path.exists(alt_kb_file):
            with open(alt_kb_file, 'r', encoding='utf-8') as f:
                lines = len(f.readlines())
            typer.echo(typer.style(f"   OK База знаний найдена в рабочей директории ({lines} строк)\n",
                                   fg=typer.colors.GREEN))
        else:
            typer.echo(typer.style(f"   ОШИБКА База знаний не найдена ({kb_file})\n", fg=typer.colors.YELLOW))
            logger.warning(f"База знаний не найдена: {kb_file}")

    # 3. Проверка сессий
    typer.echo("3️⃣  Проверка хранилища сессий...")
    sessions_count = len(session_manager.list_sessions())
    typer.echo(typer.style(f"   ✅ Сессий: {sessions_count}\n", fg=typer.colors.GREEN))

    # 4. Проверка executor
    typer.echo("4️⃣  Проверка CommandExecutor...")
    executor = get_global_executor()
    cwd = executor.get_current_directory()
    typer.echo(typer.style(f"   ✅ Рабочая директория: {cwd}\n", fg=typer.colors.GREEN))

    typer.echo(typer.style("=" * 50, fg=typer.colors.CYAN))
    typer.echo(typer.style("✅ Проверка завершена!", fg=typer.colors.GREEN, bold=True))
    typer.echo(typer.style("=" * 50 + "\n", fg=typer.colors.CYAN))


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    🤖 AI Ассистент для генерации bash команд

    Режимы использования:

    1. ИНТЕРАКТИВНЫЙ (по умолчанию):
       $ aiask

    2. ОДИНОЧНЫЙ ЗАПРОС:
       $ aiask ask "создай папку test"

    3. ИНТЕРАКТИВНЫЙ (явно):
       $ aiask interactive

    4. ПРОВЕРКА СИСТЕМЫ:
       $ aiask check

    5. СПРАВКА:
       $ aiask --help
    """

    # Если команда не указана - запускаем интерактивный режим
    if ctx.invoked_subcommand is None:
        logger.info("🎯 Автоматический выбор интерактивного режима")
        interactive_loop()


def print_logo():
    """Выводит логотип приложения"""
    logo = """
    ╔══════════════════════════════════════════════╗
    ║                                              ║
    ║          🤖 AI-ASK - AI Bash Helper          ║
    ║                                              ║
    ║   Генерация bash команд с искусственным      ║
    ║   интеллектом и проверкой безопасности       ║
    ║                                              ║
    ║   Версия: 2.0 (с поддержкой RAG)             ║
    ║                                              ║
    ╚══════════════════════════════════════════════╝
    """
    typer.echo(typer.style(logo, fg=typer.colors.CYAN))


if __name__ == "__main__":
    try:
        # Показываем логотип при запуске
        if len(sys.argv) == 1 or sys.argv[1] in ['--help', '-h']:
            print_logo()

        # Запускаем CLI
        app()

    except KeyboardInterrupt:
        logger.info("Прерывание через Ctrl+C")
        typer.echo(typer.style("\n\n👋 Выход...", fg=typer.colors.CYAN))
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        typer.echo(typer.style(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА:\n{e}", fg=typer.colors.RED), err=True)
        sys.exit(1)