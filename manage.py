import click
from kp_admin import create_app, db

# ВАЖНО: создаём приложение и регистрируем команды на нём
app = create_app()

# импортируем после create_app, чтобы не схватить циклические импорты
from kp_admin.routes import rescan_new_files  # noqa: E402  (используем готовую логику сканирования)


@app.cli.command("init-db")
def init_db():
    """Создать таблицы базы данных (если их ещё нет)."""
    with app.app_context():
        db.create_all()
        click.echo("DB ready")


@app.cli.command("scan-kp")
def scan_kp():
    """Просканировать папку с КП и добавить новые файлы в БД."""
    with app.app_context():
        added = rescan_new_files(silent=True)
        click.echo(f"Импортировано файлов: {added}")
