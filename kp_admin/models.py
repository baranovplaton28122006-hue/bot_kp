
from . import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(255))
    contact_name = db.Column(db.String(255))
    phone = db.Column(db.String(64))
    email = db.Column(db.String(255))
    site_type = db.Column(db.String(128))
    goal = db.Column(db.String(255))
    audience = db.Column(db.String(255))
    budget = db.Column(db.String(128))
    deadline = db.Column(db.String(128))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class KPFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"), nullable=True)
    filename = db.Column(db.String(512), nullable=False)
    mimetype = db.Column(db.String(64), nullable=False, default="text/html")
    size_bytes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lead = db.relationship("Lead", backref=db.backref("kps", lazy=True))
