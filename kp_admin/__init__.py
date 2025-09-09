
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "routes.login"

def ensure_instance(app):
    os.makedirs(app.instance_path, exist_ok=True)
    cfg_path = os.path.join(app.instance_path, "config.py")
    if not os.path.exists(cfg_path):
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write('SECRET_KEY = "change-me"\n')
            f.write('SQLALCHEMY_DATABASE_URI = "sqlite:///app.db"\n')
            f.write('UPLOAD_FOLDER = "uploads/kp"\n')
            f.write('ALLOWED_EXTENSIONS = {"pdf", "html"}\n')
            f.write('BOT_TOKEN = ""\n')

def create_app():
    app = Flask(__name__, instance_relative_config=True, static_folder="static", template_folder="templates")
    ensure_instance(app)
    app.config.from_pyfile("config.py", silent=True)
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        from . import models
        db.create_all()

    from .routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    return app
