# aiask.py - Основная точка входа 

import typer
import logging
from config import setup_logging
from llm_client import generate_command
from executor import run_command
from interactive import interactive_loop

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
    
    try:
        resp = generate_command(query)
        cmd, expl = resp["command"], resp.get("explanation", "")
        
        if not cmd:
            typer.echo("❌ Не удалось сгенерировать команду. Проверьте подключение к LLM.")
            logger.error("Не удалось сгенерировать команду")
            return
            
        typer.echo(f"🤖 Команда: {cmd}")
        if expl:
            typer.echo(f"💡 Объяснение: {expl}")
            
        if typer.confirm("Выполнить?"):
            logger.info("Пользователь подтвердил выполнение команды")
            code, out, err = run_command(cmd)
            
            if code == 0:
                typer.echo("✅ Команда выполнена успешно")
                if out.strip():  # Показываем только непустой вывод
                    typer.echo(out)
            else:
                typer.echo(f"❌ Ошибка выполнения (код {code})")
                if err.strip():
                    typer.echo(f"Ошибка: {err}")
        else:
            logger.info("Пользователь отменил выполнение команды")
            typer.echo("Выполнение отменено")
            
    except Exception as e:
        logger.exception(f"Неожиданная ошибка в режиме ask: {e}")
        typer.echo(f"❌ Произошла ошибка: {e}")

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    Если команда не указана, запускаем интерактивный режим.
    """
    if ctx.invoked_subcommand is None:
        logger.info("Запуск интерактивного режима")
        interactive_loop()

if __name__ == "__main__":
    app()