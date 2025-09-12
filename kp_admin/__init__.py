import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()


def create_app() -> Flask:
    app = Flask(__name__)

    # Базовая конфигурация
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///kp_admin.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REMEMBER_COOKIE_DURATION=60 * 60 * 24 * 30,  # 30 дней
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", "generated_kp"),
    )

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "kp.login"  # куда редиректить неавторизованных

    # ленивый импорт моделей (чтоб не ловить циклические)
    from .models import User  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # регистрируем blueprint с роутами
    with app.app_context():
        from .routes import bp as kp_bp
        app.register_blueprint(kp_bp)
        db.create_all()

    return app
