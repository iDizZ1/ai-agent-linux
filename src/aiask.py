from datetime import datetime

import typer
import logging
from config import setup_logging
from llm_client import generate_command
from executor import run_command, is_dangerous_command
from session_manager import session_manager

# Инициализируем логирование
setup_logging()
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, help="AI ассистент для генерации bash команд")


@app.command()
def ask(query: str = typer.Argument(..., help="Запрос на естественном языке")):
    """
    Отправить один запрос к LLM и выполнить сгенерированную команду по подтверждению.
    """
    logger.info(f"Запуск в режиме одиночного запроса: {query}")

    # Создаем временную сессию для одиночного запроса
    session = session_manager.create_session(f"single_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    try:
        enhanced_prompt = f"Одиночный запрос: {query}"
        resp = generate_command(enhanced_prompt)
        cmd, expl = resp["command"], resp.get("explanation", "")

        if not cmd:
            typer.echo("❌ Не удалось сгенерировать команду. Проверьте подключение к LLM.")
            logger.error("Не удалось сгенерировать команду")
            return

        # ПРОВЕРКА БЕЗОПАСНОСТИ ДО ВЫВОДА
        if is_dangerous_command(cmd):
            typer.echo(f"🚨 ОПАСНАЯ КОМАНДА ЗАБЛОКИРОВАНА!")
            typer.echo(f"Команда: {cmd}")
            typer.echo(f"⛔ Эта команда может нанести серьезный вред системе и автоматически заблокирована.")
            logger.warning(f"Заблокирована опасная команда: {cmd}")
            return

        typer.echo(f"🤖 Команда: {cmd}")
        if expl:
            typer.echo(f"💡 Объяснение: {expl}")

        if typer.confirm("Выполнить?"):
            logger.info("Пользователь подтвердил выполнение команды")
            code, out, err = run_command(cmd)

            if code == 0:
                typer.echo("✅ Команда выполнена успешно")
                if out.strip():
                    typer.echo(out)
            else:
                if "превышен лимит времени" in err.lower() or "timeout" in err.lower():
                    typer.echo(f"⏱️ Команда не завершилась вовремя (timeout)")
                else:
                    typer.echo(f"❌ Ошибка выполнения (код {code})")
                if err.strip():
                    typer.echo(f"Детали: {err}")
        else:
            logger.info("Пользователь отменил выполнение команды")
            typer.echo("Выполнение отменено")

        # В конце сохраняем сессию
        session_manager.save_session(session.id)


    except Exception as e:
        session.add_event(query, "", "SYSTEM_ERROR", error=str(e))
        session_manager.save_session(session.id)
        raise

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    Если команда не указана, запускаем интерактивный режим.
    """
    if ctx.invoked_subcommand is None:
        logger.info("Запуск интерактивного режима")
        from interactive import interactive_loop
        interactive_loop()  # Простой запуск без параметров

if __name__ == "__main__":
    app()