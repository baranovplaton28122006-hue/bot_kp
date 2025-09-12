# kp_admin/models.py
from __future__ import annotations
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash  # <-- ДОБАВИЛИ
from . import db, login_manager


class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), default="admin", nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    # === ДОБАВИЛИ МЕТОДЫ РАБОТЫ С ПАРОЛЕМ ===
    def set_password(self, password: str) -> None:
        """Сохраняет хэш пароля в password_hash."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Проверяет введённый пароль по хэшу."""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.email}>"


class Lead(db.Model):
    __tablename__ = "lead"
    id = db.Column(db.Integer, primary_key=True)
    tg_user_id = db.Column(db.String(32), index=True)
    username = db.Column(db.String(64), index=True)
    name = db.Column(db.String(255))
    phone = db.Column(db.String(32), index=True)
    email = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    files = db.relationship("KPFile", back_populates="lead", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Lead {self.id} {self.phone or self.username or self.tg_user_id}>"


class KPFile(db.Model):
    __tablename__ = "kp_file"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    mimetype = db.Column(db.String(64), nullable=True, default="text/html")  # <-- добавили
    phone = db.Column(db.String(32), index=True)
    chat_id = db.Column(db.String(32))
    username = db.Column(db.String(64), index=True)
    name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"))
    lead = db.relationship("Lead", back_populates="files")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KPFile {self.id} {self.filename}>"


@login_manager.user_loader
def load_user(user_id: str):
    if not user_id:
        return None
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None
