# -*- coding: utf-8 -*-
# Обновляет админку до "pro"-версии: роли, графики, фильтры, предпросмотр HTML-КП,
# ZIP мультисказч, импорт/экспорт CSV, заметки к лидам, страница настроек, REST API.
import os, io, sys, textwrap, json, shutil

ROOT = os.path.abspath(os.path.dirname(__file__))
PKG = os.path.join(ROOT, "kp_admin")
os.makedirs(PKG, exist_ok=True)
TEMPL = os.path.join(PKG, "templates")
os.makedirs(TEMPL, exist_ok=True)
ADMIN_TEMPL = os.path.join(TEMPL, "admin")
os.makedirs(ADMIN_TEMPL, exist_ok=True)
STATIC = os.path.join(PKG, "static", "css")
os.makedirs(STATIC, exist_ok=True)
INSTANCE = os.path.join(ROOT, "instance")
os.makedirs(INSTANCE, exist_ok=True)

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

# ---------- requirements ----------
w(os.path.join(ROOT, "requirements.txt"), """
Flask==3.0.3
Flask-Login==0.6.3
Flask-WTF==1.2.1
email-validator==2.1.1
SQLAlchemy==2.0.31
Flask-SQLAlchemy==3.1.1
WTForms==3.1.2
xhtml2pdf==0.2.15
python-slugify==8.0.4
pandas==2.2.2
""")

# ---------- manage.py ----------
w(os.path.join(ROOT, "manage.py"), """
from kp_admin import create_app, db
from kp_admin.models import User, Lead, KPFile
import click

app = create_app()

@app.shell_context_processor
def shell():
    return {"db": db, "User": User, "Lead": Lead, "KPFile": KPFile}

@app.cli.command("create-admin")
@click.option("--email", required=True)
@click.option("--password", required=True)
@click.option("--role", default="admin", type=click.Choice(["admin","manager","viewer"]))
def create_admin(email, password, role):
    if User.query.filter_by(email=email).first():
        click.echo("User already exists")
        return
    u = User(email=email, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.echo(f"Admin created: {email} ({role})")

@app.cli.command("list-users")
def list_users():
    for u in User.query.all():
        print(u.id, u.email, u.role)

@app.cli.command("set-password")
@click.option("--email", required=True)
@click.option("--password", required=True)
def set_password(email, password):
    u = User.query.filter_by(email=email).first()
    if not u:
        print("User not found")
        return
    u.set_password(password)
    db.session.commit()
    print("Password updated")
""")

# ---------- kp_admin/__init__.py ----------
w(os.path.join(PKG, "__init__.py"), """
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
            f.write('SECRET_KEY = "change-me"\\n')
            f.write('SQLALCHEMY_DATABASE_URI = "sqlite:///app.db"\\n')
            f.write('UPLOAD_FOLDER = "uploads/kp"\\n')
            f.write('ALLOWED_EXTENSIONS = {"pdf", "html"}\\n')
            f.write('BOT_TOKEN = ""\\n')
            f.write('API_KEY = "set-api-key"\\n')

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
""")

# ---------- kp_admin/models.py ----------
w(os.path.join(PKG, "models.py"), """
from . import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="admin")  # admin / manager / viewer
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

class LeadNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    lead = db.relationship("Lead", backref=db.backref("notes", lazy=True, order_by="LeadNote.created_at.desc()"))

class KPFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"), nullable=True)
    filename = db.Column(db.String(512), nullable=False)
    mimetype = db.Column(db.String(64), nullable=False, default="text/html")
    size_bytes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lead = db.relationship("Lead", backref=db.backref("kps", lazy=True, order_by="KPFile.created_at.desc()"))
""")

# ---------- kp_admin/utils.py ----------
w(os.path.join(PKG, "utils.py"), r"""
import os, io, datetime
from flask import current_app
from slugify import slugify
from xhtml2pdf import pisa

def allowed_file(filename: str) -> bool:
    exts = current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "html"})
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts

def ensure_uploads_folder():
    folder = os.path.join(current_app.instance_path, current_app.config.get("UPLOAD_FOLDER", "uploads/kp"))
    os.makedirs(folder, exist_ok=True)
    return folder

def save_html_as_pdf(html: str, out_path: str) -> bool:
    """Simple HTML -> PDF using xhtml2pdf. Returns True/False."""
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(io.StringIO(html), dest=f)
    return not result.err

def render_kp_html(lead, blocks: dict) -> str:
    # список выбранных блоков
    items_html = "".join([f"<li><strong>{k}:</strong> {v}</li>" for k, v in blocks.items()])
    title = f"КП для {lead.company or lead.contact_name or 'клиента'}"

    html = """
    <!doctype html>
    <html lang="ru">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>%(title)s</title>
        <style>
          body{font-family: Arial, sans-serif; margin: 24px;}
          header, footer{border-top: 4px solid #22c55e; padding: 12px 0;}
          h1{margin: 0 0 8px;}
          .meta{color:#555; font-size:14px; margin-bottom:16px;}
          .section{margin:16px 0; padding:12px; border:1px solid #eee; border-radius:8px;}
          ul{margin:0; padding-left:20px;}
        </style>
      </head>
      <body>
        <header>
          <h1>%(title)s</h1>
          <div class="meta">Email: %(email)s • Тел: %(phone)s</div>
        </header>
        <div class="section">
          <h3>Параметры проекта</h3>
          <ul>
            <li>Тип сайта: %(site_type)s</li>
            <li>Цель: %(goal)s</li>
            <li>Аудитория: %(audience)s</li>
            <li>Бюджет: %(budget)s</li>
            <li>Срок: %(deadline)s</li>
          </ul>
        </div>
        <div class="section">
          <h3>Выбранные блоки</h3>
          <ul>%(items_html)s</ul>
        </div>
        <footer>
          <small>Сформировано админ-панелью</small>
        </footer>
      </body>
    </html>
    """ % dict(
        title=title,
        email=lead.email or "-",
        phone=lead.phone or "-",
        site_type=lead.site_type or "-",
        goal=lead.goal or "-",
        audience=lead.audience or "-",
        budget=lead.budget or "-",
        deadline=lead.deadline or "-",
        items_html=items_html,
    )
    return html
def parse_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None
""")

# ---------- templates/base.html ----------
w(os.path.join(TEMPL, "base.html"), """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}КП Админка{% endblock %}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  </head>
  <body class="bg-dark text-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-success">
      <div class="container-fluid">
        <a class="navbar-brand" href="{{ url_for('routes.dashboard') }}">КП Панель</a>
        <div class="collapse navbar-collapse">
          <ul class="navbar-nav me-auto mb-2 mb-lg-0">
            <li class="nav-item"><a class="nav-link" href="{{ url_for('routes.leads') }}">Лиды</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('routes.kp_index') }}">КП-файлы</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('routes.settings') }}">Настройки</a></li>
          </ul>
          {% if current_user.is_authenticated %}
          <span class="navbar-text me-3">{{ current_user.email }} ({{ current_user.role }})</span>
          <a class="btn btn-outline-light btn-sm" href="{{ url_for('routes.logout') }}">Выйти</a>
          {% endif %}
        </div>
      </div>
    </nav>

    <main class="container my-4">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}
            <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
              {{ message }}
              <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      {% block content %}{% endblock %}
    </main>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
""")

# ---------- dashboard ----------
w(os.path.join(ADMIN_TEMPL, "dashboard.html"), """
{% extends "base.html" %}
{% block content %}
<h4 class="mb-3">Панель управления</h4>
<div class="row g-3">
  <div class="col-6 col-lg-3"><div class="card text-bg-dark border-success"><div class="card-body"><div class="fw-bold">Лидов</div><div class="display-6">{{ leads_count }}</div></div></div></div>
  <div class="col-6 col-lg-3"><div class="card text-bg-dark border-success"><div class="card-body"><div class="fw-bold">КП-файлов</div><div class="display-6">{{ kps_count }}</div></div></div></div>
  <div class="col-6 col-lg-3"><div class="card text-bg-dark border-success"><div class="card-body"><div class="fw-bold">Уник. телефонов</div><div class="display-6">{{ uniq_phones }}</div></div></div></div>
  <div class="col-6 col-lg-3"><div class="card text-bg-dark border-success"><div class="card-body"><div class="fw-bold">Уник. email</div><div class="display-6">{{ uniq_emails }}</div></div></div></div>
</div>
<div class="row g-3 mt-1">
  <div class="col-12 col-lg-7">
    <div class="card text-bg-dark border-success">
      <div class="card-header">КП и лиды по дням</div>
      <div class="card-body"><canvas id="chartCounts"></canvas></div>
    </div>
  </div>
  <div class="col-12 col-lg-5">
    <div class="card text-bg-dark border-success">
      <div class="card-header">Последние КП</div>
      <div class="card-body">
        <ul class="list-group">
          {% for k in latest_kps %}
          <li class="list-group-item d-flex justify-content-between align-items-center"><span>{{ k.filename }}</span><a class="btn btn-sm btn-outline-success" href="{{ url_for('routes.kp_download', kp_id=k.id) }}">Скачать</a></li>
          {% else %}<li class="list-group-item">Пусто</li>{% endfor %}
        </ul>
      </div>
    </div>
  </div>
</div>
<script>
fetch("{{ url_for('routes.stats_counts') }}")
 .then(r=>r.json())
 .then(d=>{
   const ctx = document.getElementById('chartCounts');
   new Chart(ctx, {type:'line', data:{labels:d.labels, datasets:[{label:'Лиды', data:d.leads},{label:'КП', data:d.kps}]}, options:{responsive:true}});
 });
</script>
{% endblock %}
""")

# ---------- leads list ----------
w(os.path.join(ADMIN_TEMPL, "leads.html"), """
{% extends "base.html" %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">Лиды</h4>
  <div class="d-flex gap-2">
    <a class="btn btn-outline-success" href="{{ url_for('routes.lead_export_csv') }}">Экспорт CSV</a>
    <form class="d-inline-flex" method="post" enctype="multipart/form-data" action="{{ url_for('routes.lead_import_csv') }}">
      <input class="form-control form-control-sm" type="file" name="file" required>
      <button class="btn btn-success btn-sm ms-2">Импорт CSV</button>
    </form>
    <a class="btn btn-success" href="{{ url_for('routes.lead_new') }}">Новый лид</a>
  </div>
</div>

<form class="row g-2 mb-3" method="get">
  <div class="col-md-3"><input class="form-control" name="q_name" placeholder="Имя/компания" value="{{ q_name }}"></div>
  <div class="col-md-3"><input class="form-control" name="q_phone" placeholder="Телефон" value="{{ q_phone }}"></div>
  <div class="col-md-3"><input class="form-control" name="q_email" placeholder="Email" value="{{ q_email }}"></div>
  <div class="col-md-3 d-flex gap-2">
    <input class="form-control" type="date" name="q_date" value="{{ q_date }}">
    <button class="btn btn-outline-success" type="submit">Фильтр</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('routes.leads') }}">Сброс</a>
  </div>
</form>

<form method="post" action="{{ url_for('routes.bulk_delete') }}">
<table class="table table-dark table-hover align-middle">
  <thead>
    <tr>
      <th style="width:32px;"><input type="checkbox" onclick="document.querySelectorAll('input[name=ids]').forEach(cb=>cb.checked=this.checked)"></th>
      <th>ID</th><th>Компания / Имя</th><th>Email</th><th>Телефон</th><th>Создан</th><th>КП</th><th></th>
    </tr>
  </thead>
  <tbody>
    {% for l in items %}
    <tr>
      <td><input type="checkbox" name="ids" value="{{ l.id }}"></td>
      <td>{{ l.id }}</td>
      <td>{{ l.company or l.contact_name or "-" }}</td>
      <td>{{ l.email or "-" }}</td>
      <td>{{ l.phone or "-" }}</td>
      <td>{{ l.created_at.strftime("%Y-%m-%d %H:%M") }}</td>
      <td>{{ l.kps|length }}</td>
      <td class="text-end"><a class="btn btn-sm btn-outline-secondary" href="{{ url_for('routes.lead_detail', lead_id=l.id) }}">Открыть</a></td>
    </tr>
    {% else %}<tr><td colspan="8" class="text-center text-muted">Ничего не найдено</td></tr>{% endfor %}
  </tbody>
</table>

<nav><ul class="pagination mb-0">
  {% for p in range(1, pages+1) %}
    <li class="page-item {% if p==page %}active{% endif %}"><a class="page-link" href="?page={{ p }}&q_name={{ q_name|urlencode }}&q_phone={{ q_phone|urlencode }}&q_email={{ q_email|urlencode }}&q_date={{ q_date|urlencode }}">{{ p }}</a></li>
  {% endfor %}
</ul></nav>
</form>
{% endblock %}
""")

# ---------- lead form ----------
w(os.path.join(ADMIN_TEMPL, "lead_form.html"), """
{% extends "base.html" %}
{% block content %}
<form method="post">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h4 class="mb-0">{{ 'Новый лид' if not lead else ('Лид #' ~ lead.id) }}</h4>
    {% if lead %}
    <div class="d-flex gap-2">
      <a class="btn btn-outline-secondary" href="{{ url_for('routes.lead_export_json', lead_id=lead.id) }}">Экспорт JSON</a>
      <button class="btn btn-success" formaction="{{ url_for('routes.kp_generate', lead_id=lead.id) }}" formmethod="post">Сгенерировать КП</button>
    </div>
    {% endif %}
  </div>

  <div class="row g-3">
    <div class="col-md-6"><label class="form-label">Компания</label><input class="form-control" name="company" value="{{ lead.company if lead else '' }}"></div>
    <div class="col-md-6"><label class="form-label">Контактное лицо</label><input class="form-control" name="contact_name" value="{{ lead.contact_name if lead else '' }}"></div>
    <div class="col-md-4"><label class="form-label">Телефон</label><input class="form-control" name="phone" value="{{ lead.phone if lead else '' }}"></div>
    <div class="col-md-4"><label class="form-label">Email</label><input class="form-control" type="email" name="email" value="{{ lead.email if lead else '' }}"></div>
    <div class="col-md-4"><label class="form-label">Тип сайта</label><input class="form-control" name="site_type" value="{{ lead.site_type if lead else '' }}"></div>
    <div class="col-md-4"><label class="form-label">Цель</label><input class="form-control" name="goal" value="{{ lead.goal if lead else '' }}"></div>
    <div class="col-md-4"><label class="form-label">Аудитория</label><input class="form-control" name="audience" value="{{ lead.audience if lead else '' }}"></div>
    <div class="col-md-4"><label class="form-label">Бюджет</label><input class="form-control" name="budget" value="{{ lead.budget if lead else '' }}"></div>
    <div class="col-md-4"><label class="form-label">Срок</label><input class="form-control" name="deadline" value="{{ lead.deadline if lead else '' }}"></div>
    <div class="col-12"><label class="form-label">Примечания</label><textarea class="form-control" name="notes" rows="3">{{ lead.notes if lead else '' }}</textarea></div>
  </div>

  {% if lead %}
  <div class="mt-4">
    <h5>Заметки</h5>
    <form method="post" action="{{ url_for('routes.lead_add_note', lead_id=lead.id) }}" class="d-flex gap-2">
      <input class="form-control" name="text" placeholder="Добавить заметку…" required>
      <button class="btn btn-outline-success">Добавить</button>
    </form>
    <ul class="list-group mt-2">
      {% for n in lead.notes %}
      <li class="list-group-item d-flex justify-content-between align-items-center"><span>{{ n.text }}</span><small class="text-muted">{{ n.created_at.strftime("%Y-%m-%d %H:%M") }}</small></li>
      {% else %}<li class="list-group-item">Пока нет заметок</li>{% endfor %}
    </ul>
  </div>
  {% endif %}

  <div class="mt-3 d-flex gap-2">
    <button class="btn btn-success" type="submit">Сохранить</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('routes.leads') }}">Назад</a>
    {% if lead %}<form method="post" action="{{ url_for('routes.lead_delete', lead_id=lead.id) }}"><button class="btn btn-outline-danger">Удалить</button></form>{% endif %}
  </div>
</form>
{% endblock %}
""")

# ---------- kp list ----------
w(os.path.join(ADMIN_TEMPL, "kp_list.html"), """
{% extends "base.html" %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">КП-файлы</h4>
  <div class="d-flex gap-2">
    <form class="d-inline-flex" method="post" action="{{ url_for('routes.kp_upload') }}" enctype="multipart/form-data">
      <input type="file" class="form-control form-control-sm" name="file" required>
      <button class="btn btn-success btn-sm ms-2" type="submit">Загрузить</button>
    </form>
    <a class="btn btn-outline-success btn-sm" href="{{ url_for('routes.kp_index') }}">Обновить</a>
  </div>
</div>

<form class="row g-2 mb-3" method="get">
  <div class="col-md-3"><input class="form-control" name="q_phone" placeholder="Телефон" value="{{ q_phone }}"></div>
  <div class="col-md-3"><input class="form-control" name="q_email" placeholder="Email" value="{{ q_email }}"></div>
  <div class="col-md-3"><input class="form-control" type="date" name="q_date" value="{{ q_date }}"></div>
  <div class="col-md-3 d-flex gap-2">
    <select class="form-select" name="sort">
      <option value="new" {% if sort=='new' %}selected{% endif %}>Сначала новые</option>
      <option value="old" {% if sort=='old' %}selected{% endif %}>Сначала старые</option>
      <option value="name" {% if sort=='name' %}selected{% endif %}>По имени файла</option>
    </select>
    <button class="btn btn-outline-success">Фильтр</button>
    <a class="btn btn-outline-secondary" href="{{ url_for('routes.kp_index') }}">Сброс</a>
  </div>
</form>

<form method="post" action="{{ url_for('routes.kp_bulk_zip') }}">
<table class="table table-dark table-striped align-middle">
  <thead>
    <tr>
      <th style="width:32px;"><input type="checkbox" onclick="document.querySelectorAll('input[name=ids]').forEach(cb=>cb.checked=this.checked)"></th>
      <th>ID</th><th>Имя файла</th><th>Размер</th><th>Тип</th><th>Создан</th><th></th>
    </tr>
  </thead>
  <tbody>
    {% for k in items %}
    <tr>
      <td><input type="checkbox" name="ids" value="{{ k.id }}"></td>
      <td>{{ k.id }}</td>
      <td>{{ k.filename }}</td>
      <td>{{ (k.size_bytes // 1024) }} КБ</td>
      <td>{{ k.mimetype }}</td>
      <td>{{ k.created_at.strftime("%Y-%m-%d %H:%M") }}</td>
      <td class="text-end">
        <a class="btn btn-sm btn-outline-success" href="{{ url_for('routes.kp_download', kp_id=k.id) }}">Скачать</a>
        {% if 'html' in k.mimetype or k.filename.lower().endswith('.html') %}
        <a class="btn btn-sm btn-outline-info" href="{{ url_for('routes.kp_preview', kp_id=k.id) }}" target="_blank">Предпросмотр</a>
        {% endif %}
        <form method="post" action="{{ url_for('routes.kp_delete', kp_id=k.id) }}" class="d-inline"><button class="btn btn-sm btn-outline-danger">Удалить</button></form>
      </td>
    </tr>
    {% else %}<tr><td colspan="7" class="text-center text-muted">Нет файлов</td></tr>{% endfor %}
  </tbody>
</table>

<div class="d-flex justify-content-between align-items-center">
  <div class="d-flex gap-2"><button class="btn btn-outline-light btn-sm" type="submit">Скачать выбранные ZIP</button></div>
  <nav><ul class="pagination mb-0">{% for p in range(1, pages+1) %}
    <li class="page-item {% if p==page %}active{% endif %}"><a class="page-link" href="?page={{ p }}&q_phone={{ q_phone|urlencode }}&q_email={{ q_email|urlencode }}&q_date={{ q_date|urlencode }}&sort={{ sort|urlencode }}">{{ p }}</a></li>
  {% endfor %}</ul></nav>
</div>
</form>
{% endblock %}
""")

# ---------- settings ----------
w(os.path.join(ADMIN_TEMPL, "settings.html"), """
{% extends "base.html" %}
{% block content %}
<h4 class="mb-3">Настройки</h4>
<form method="post">
  <div class="row g-3">
    <div class="col-md-6"><label class="form-label">BOT_TOKEN</label><input class="form-control" name="BOT_TOKEN" value="{{ cfg.BOT_TOKEN }}"></div>
    <div class="col-md-6"><label class="form-label">UPLOAD_FOLDER (относительно instance/)</label><input class="form-control" name="UPLOAD_FOLDER" value="{{ cfg.UPLOAD_FOLDER }}"></div>
    <div class="col-md-6"><label class="form-label">API_KEY (для REST)</label><input class="form-control" name="API_KEY" value="{{ cfg.API_KEY }}"></div>
  </div>
  <div class="mt-3"><button class="btn btn-success">Сохранить</button></div>
</form>
{% endblock %}
""")

# ---------- static css ----------
w(os.path.join(STATIC, "app.css"), """
body { background: #0b1220 url('https://images.unsplash.com/photo-1444703686981-a3abbc4d4fe3?q=80&w=2070&auto=format&fit=crop') center/cover fixed; }
.card { border-radius: 14px; }
.table td, .table th { vertical-align: middle; }
.btn { border-radius: 10px; }
.navbar { box-shadow: 0 2px 10px rgba(0,0,0,.3); }
.list-group-item { background-color: rgba(0,0,0,.25); color: #e6e6e6; }
""")

# ---------- routes ----------
w(os.path.join(PKG, "routes.py"), r"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app, abort, jsonify, Response
from flask_login import login_user, logout_user, login_required, current_user
from .models import User, Lead, KPFile, LeadNote
from . import db
from .utils import ensure_uploads_folder, allowed_file, render_kp_html, save_html_as_pdf, parse_date
from werkzeug.utils import secure_filename
import os, math, mimetypes, json, datetime, io, zipfile

bp = Blueprint("routes", __name__)

def require_role(*roles):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("routes.login"))
            if current_user.role not in roles:
                flash("Недостаточно прав", "danger")
                return redirect(url_for("routes.dashboard"))
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return login_required(wrapper)
    return decorator

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("routes.dashboard"))
        flash("Неверный email или пароль", "danger")
    return render_template("login.html")

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("routes.login"))

@bp.route("/")
@login_required
def dashboard():
    leads_count = Lead.query.count()
    kps_count = KPFile.query.count()
    uniq_phones = db.session.query(Lead.phone).filter(Lead.phone.isnot(None)).distinct().count()
    uniq_emails = db.session.query(Lead.email).filter(Lead.email.isnot(None)).distinct().count()
    latest_leads = Lead.query.order_by(Lead.created_at.desc()).limit(5).all()
    latest_kps = KPFile.query.order_by(KPFile.created_at.desc()).limit(5).all()
    return render_template("admin/dashboard.html",
                           leads_count=leads_count, kps_count=kps_count,
                           uniq_phones=uniq_phones, uniq_emails=uniq_emails,
                           latest_leads=latest_leads, latest_kps=latest_kps)

@bp.route("/stats/counts")
@login_required
def stats_counts():
    days = [datetime.date.today() - datetime.timedelta(days=i) for i in range(13,-1,-1)]
    labels = [d.strftime("%Y-%m-%d") for d in days]
    lead_counts, kp_counts = [], []
    for d in days:
        d1 = datetime.datetime.combine(d, datetime.time.min)
        d2 = datetime.datetime.combine(d, datetime.time.max)
        lead_counts.append(Lead.query.filter(Lead.created_at>=d1, Lead.created_at<=d2).count())
        kp_counts.append(KPFile.query.filter(KPFile.created_at>=d1, KPFile.created_at<=d2).count())
    return jsonify({"labels": labels, "leads": lead_counts, "kps": kp_counts})

def _paginate(query, per_page=20):
    page = max(int(request.args.get("page", 1)), 1)
    total = query.count()
    pages = (total + per_page - 1) // per_page
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, page, pages, total

@bp.route("/leads")
@login_required
def leads():
    from .utils import parse_date
    q_name = request.args.get("q_name","").strip()
    q_phone = request.args.get("q_phone","").strip()
    q_email = request.args.get("q_email","").strip()
    q_date = request.args.get("q_date","").strip()

    base = Lead.query
    if q_name:
        like = f"%{q_name}%"
        base = base.filter((Lead.company.ilike(like)) | (Lead.contact_name.ilike(like)))
    if q_phone:
        base = base.filter(Lead.phone.ilike(f"%{q_phone}%"))
    if q_email:
        base = base.filter(Lead.email.ilike(f"%{q_email}%"))
    if q_date:
        day = parse_date(q_date)
        if day:
            d1 = datetime.datetime.combine(day, datetime.time.min)
            d2 = datetime.datetime.combine(day, datetime.time.max)
            base = base.filter(Lead.created_at>=d1, Lead.created_at<=d2)

    base = base.order_by(Lead.created_at.desc())
    items, page, pages, total = _paginate(base, per_page=20)
    return render_template("admin/leads.html", items=items, page=page, pages=pages, total=total,
                           q_name=q_name, q_phone=q_phone, q_email=q_email, q_date=q_date)

@bp.route("/leads/new", methods=["GET", "POST"])
@require_role("admin","manager")
def lead_new():
    if request.method == "POST":
        data = {k: request.form.get(k) for k in ["company","contact_name","phone","email","site_type","goal","audience","budget","deadline","notes"]}
        lead = Lead(**data)
        db.session.add(lead)
        db.session.commit()
        flash("Лид создан", "success")
        return redirect(url_for("routes.leads"))
    return render_template("admin/lead_form.html", lead=None)

@bp.route("/leads/<int:lead_id>", methods=["GET", "POST"])
@login_required
def lead_detail(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if request.method == "POST":
        if current_user.role not in ["admin","manager"]:
            flash("Недостаточно прав", "danger")
            return redirect(url_for("routes.lead_detail", lead_id=lead.id))
        for k in ["company","contact_name","phone","email","site_type","goal","audience","budget","deadline","notes"]:
            setattr(lead, k, request.form.get(k))
        db.session.commit()
        flash("Лид обновлён", "success")
        return redirect(url_for("routes.lead_detail", lead_id=lead.id))
    return render_template("admin/lead_form.html", lead=lead)

@bp.route("/leads/<int:lead_id>/note", methods=["POST"])
@require_role("admin","manager")
def lead_add_note(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    text = request.form.get("text","").strip()
    if text:
        from .models import LeadNote
        db.session.add(LeadNote(lead_id=lead.id, text=text))
        db.session.commit()
        flash("Заметка добавлена","success")
    return redirect(url_for("routes.lead_detail", lead_id=lead.id))

@bp.route("/leads/<int:lead_id>/delete", methods=["POST"])
@require_role("admin")
def lead_delete(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    db.session.delete(lead)
    db.session.commit()
    flash("Лид удалён", "info")
    return redirect(url_for("routes.leads"))

@bp.route("/leads/<int:lead_id>/export.json")
@login_required
def lead_export_json(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    data = {k: getattr(lead, k) for k in ["id","company","contact_name","phone","email","site_type","goal","audience","budget","deadline","notes"]}
    return (json.dumps(data, ensure_ascii=False, indent=2), 200, {"Content-Type": "application/json; charset=utf-8"})

@bp.route("/leads/export.csv")
@login_required
def lead_export_csv():
    import pandas as pd
    rows = []
    for l in Lead.query.order_by(Lead.id.asc()).all():
        rows.append({
            "id": l.id, "company": l.company, "contact_name": l.contact_name, "phone": l.phone, "email": l.email,
            "site_type": l.site_type, "goal": l.goal, "audience": l.audience, "budget": l.budget, "deadline": l.deadline,
            "notes": l.notes, "created_at": l.created_at
        })
    df = pd.DataFrame(rows)
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    return Response(csv_bytes, mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=leads.csv"})

@bp.route("/leads/import.csv", methods=["POST"])
@require_role("admin","manager")
def lead_import_csv():
    file = request.files.get("file")
    if not file:
        flash("Файл не выбран","warning")
        return redirect(url_for("routes.leads"))
    import pandas as pd
    df = pd.read_csv(file)
    for _, r in df.iterrows():
        lead = Lead(company=r.get("company"), contact_name=r.get("contact_name"), phone=str(r.get("phone") or ""),
                    email=r.get("email"), site_type=r.get("site_type"), goal=r.get("goal"), audience=r.get("audience"),
                    budget=r.get("budget"), deadline=r.get("deadline"), notes=r.get("notes"))
        db.session.add(lead)
    db.session.commit()
    flash("Импорт выполнен","success")
    return redirect(url_for("routes.leads"))

@bp.route("/kp")
@login_required
def kp_index():
    q_phone = request.args.get("q_phone","").strip()
    q_email = request.args.get("q_email","").strip()
    q_date = request.args.get("q_date","").strip()
    sort = request.args.get("sort","new")

    base = KPFile.query
    if q_phone:
        base = base.join(Lead, isouter=True).filter(Lead.phone.ilike(f"%{q_phone}%"))
    if q_email:
        base = base.join(Lead, isouter=True).filter(Lead.email.ilike(f"%{q_email}%"))
    if q_date:
        from .utils import parse_date
        day = parse_date(q_date)
        if day:
            d1 = datetime.datetime.combine(day, datetime.time.min)
            d2 = datetime.datetime.combine(day, datetime.time.max)
            base = base.filter(KPFile.created_at>=d1, KPFile.created_at<=d2)

    if sort=="new":
        base = base.order_by(KPFile.created_at.desc())
    elif sort=="old":
        base = base.order_by(KPFile.created_at.asc())
    else:
        base = base.order_by(KPFile.filename.asc())

    items, page, pages, total = _paginate(base, per_page=20)
    return render_template("admin/kp_list.html", items=items, page=page, pages=pages, total=total,
                           q_phone=q_phone, q_email=q_email, q_date=q_date, sort=sort)

@bp.route("/kp/upload", methods=["POST"])
@require_role("admin","manager")
def kp_upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Не выбран файл", "warning")
        return redirect(url_for("routes.kp_index"))
    if not allowed_file(file.filename):
        flash("Недопустимый формат", "danger")
        return redirect(url_for("routes.kp_index"))
    folder = ensure_uploads_folder()
    filename = secure_filename(file.filename)
    path = os.path.join(folder, filename)
    file.save(path)
    size = os.path.getsize(path)
    mtype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    kp = KPFile(filename=filename, size_bytes=size, mimetype=mtype)
    db.session.add(kp)
    db.session.commit()
    flash("Файл загружен", "success")
    return redirect(url_for("routes.kp_index"))

@bp.route("/kp/download/<int:kp_id>")
@login_required
def kp_download(kp_id):
    kp = KPFile.query.get_or_404(kp_id)
    folder = ensure_uploads_folder()
    path = os.path.join(folder, kp.filename)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(folder, kp.filename, as_attachment=True)

@bp.route("/kp/preview/<int:kp_id>")
@login_required
def kp_preview(kp_id):
    kp = KPFile.query.get_or_404(kp_id)
    folder = ensure_uploads_folder()
    path = os.path.join(folder, kp.filename)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(folder, kp.filename, as_attachment=False, mimetype="text/html")

@bp.route("/kp/delete/<int:kp_id>", methods=["POST"])
@require_role("admin")
def kp_delete(kp_id):
    kp = KPFile.query.get_or_404(kp_id)
    folder = ensure_uploads_folder()
    path = os.path.join(folder, kp.filename)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(kp)
    db.session.commit()
    flash("КП удалено", "info")
    return redirect(url_for("routes.kp_index"))

@bp.route("/kp/generate/<int:lead_id>", methods=["POST"])
@require_role("admin","manager")
def kp_generate(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    blocks = request.form.to_dict() or {"Стоимость": "Индивидуально", "Поддержка": "30 дней", "Срок разработки": "2-4 недели"}
    html = render_kp_html(lead, blocks)
    folder = ensure_uploads_folder()
    base_name = f"KP_{lead.id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    html_name = base_name + ".html"
    html_path = os.path.join(folder, html_name)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    pdf_name = base_name + ".pdf"
    pdf_path = os.path.join(folder, pdf_name)
    pdf_ok = save_html_as_pdf(html, pdf_path)

    filename = pdf_name if pdf_ok else html_name
    final_path = pdf_path if pdf_ok else html_path
    size = os.path.getsize(final_path)
    mtype = "application/pdf" if pdf_ok else "text/html"

    kp = KPFile(lead_id=lead.id, filename=filename, size_bytes=size, mimetype=mtype)
    db.session.add(kp)
    db.session.commit()
    flash("КП сгенерировано" + (" (PDF)" if pdf_ok else " (HTML)"), "success")
    return redirect(url_for("routes.kp_index"))

@bp.route("/kp/bulk-zip", methods=["POST"])
@login_required
def kp_bulk_zip():
    ids = request.form.getlist("ids")
    if not ids:
        flash("Не выбраны элементы", "warning")
        return redirect(url_for("routes.kp_index"))
    mem = io.BytesIO()
    folder = ensure_uploads_folder()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for sid in ids:
            kp = KPFile.query.get(int(sid))
            if not kp: continue
            path = os.path.join(folder, kp.filename)
            if os.path.exists(path):
                z.write(path, kp.filename)
    mem.seek(0)
    return Response(mem.getvalue(), mimetype="application/zip",
                    headers={"Content-Disposition":"attachment; filename=kp_selected.zip"})

@bp.route("/maintenance/bulk_delete", methods=["POST"])
@require_role("admin")
def bulk_delete():
    ids = request.form.getlist("ids")
    if not ids:
        flash("Не выбраны элементы", "warning")
        return redirect(request.referrer or url_for("routes.dashboard"))
    for sid in ids:
        kp = KPFile.query.get(sid)
        if kp:
            folder = ensure_uploads_folder()
            path = os.path.join(folder, kp.filename)
            if os.path.exists(path):
                os.remove(path)
            db.session.delete(kp)
            continue
        lead = Lead.query.get(sid)
        if lead:
            db.session.delete(lead)
    db.session.commit()
    flash("Удаление выполнено", "info")
    return redirect(request.referrer or url_for("routes.dashboard"))

@bp.route("/settings", methods=["GET","POST"])
@require_role("admin")
def settings():
    cfg = type("Cfg", (), {})()
    cfg.BOT_TOKEN = current_app.config.get("BOT_TOKEN","")
    cfg.UPLOAD_FOLDER = current_app.config.get("UPLOAD_FOLDER","uploads/kp")
    cfg.API_KEY = current_app.config.get("API_KEY","set-api-key")

    if request.method == "POST":
        cfg_path = os.path.join(current_app.instance_path, "config.py")
        with open(cfg_path, "r", encoding="utf-8") as f:
            content = f.read()
        def set_kv(text, key, value_repr):
            import re
            pattern = rf'^{key}\s*=.*$'
            repl = f'{key} = {value_repr}'
            if re.search(pattern, text, flags=re.M):
                return re.sub(pattern, repl, text, flags=re.M)
            else:
                return text + f"\\n{repl}\\n"
        content = set_kv(content, "BOT_TOKEN", repr(request.form.get("BOT_TOKEN","")))
        content = set_kv(content, "UPLOAD_FOLDER", repr(request.form.get("UPLOAD_FOLDER","uploads/kp")))
        content = set_kv(content, "API_KEY", repr(request.form.get("API_KEY","set-api-key")))
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(content)
        flash("Настройки сохранены. Перезапустите сервер для применения.", "success")
        return redirect(url_for("routes.settings"))

    return render_template("admin/settings.html", cfg=cfg)

def check_api_key(req):
    api_key = current_app.config.get("API_KEY","")
    return req.headers.get("X-API-Key")==api_key or req.args.get("api_key")==api_key

@bp.route("/api/leads", methods=["POST"])
def api_leads():
    if not check_api_key(request):
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(force=True)
    lead = Lead(company=data.get("company"), contact_name=data.get("contact_name"), phone=data.get("phone"),
                email=data.get("email"), site_type=data.get("site_type"), goal=data.get("goal"),
                audience=data.get("audience"), budget=data.get("budget"), deadline=data.get("deadline"),
                notes=data.get("notes"))
    db.session.add(lead)
    db.session.commit()
    return jsonify({"ok":True, "lead_id":lead.id})

@bp.route("/api/kp", methods=["POST"])
def api_kp():
    if not check_api_key(request):
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(force=True)
    lead_id = data.get("lead_id")
    filename = data.get("filename")
    size = int(data.get("size_bytes") or 0)
    mtype = data.get("mimetype") or "text/html"
    db.session.add(KPFile(lead_id=lead_id, filename=filename, size_bytes=size, mimetype=mtype))
    db.session.commit()
    return jsonify({"ok":True})
""")

print("✅ Upgrade files written. Now run: pip install -r requirements.txt")
