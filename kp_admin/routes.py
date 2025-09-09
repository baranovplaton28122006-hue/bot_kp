
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from .models import User, Lead, KPFile
from . import db
from .utils import ensure_uploads_folder, allowed_file, render_kp_html, save_html_as_pdf
from werkzeug.utils import secure_filename
import os, math, mimetypes, json, datetime

bp = Blueprint("routes", __name__)

@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    # Заглушка настроек, чтобы не падало.
    # Позже можно расширить — сохранение в instance/config.py и т.п.
    class Cfg:
        BOT_TOKEN = current_app.config.get("BOT_TOKEN", "")
        UPLOAD_FOLDER = current_app.config.get("UPLOAD_FOLDER", "uploads/kp")
        API_KEY = current_app.config.get("API_KEY", "")
    return render_template("admin/settings.html", cfg=Cfg())

# ---------- Auth ----------
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

# ---------- Dashboard ----------
@bp.route("/")
@login_required
def dashboard():
    leads_count = Lead.query.count()
    kps_count = KPFile.query.count()
    latest_leads = Lead.query.order_by(Lead.created_at.desc()).limit(5).all()
    latest_kps = KPFile.query.order_by(KPFile.created_at.desc()).limit(5).all()
    return render_template("admin/dashboard.html",
                           leads_count=leads_count, kps_count=kps_count,
                           latest_leads=latest_leads, latest_kps=latest_kps)

@bp.route("/stats/counts")
@login_required
def stats_counts():
    import datetime
    from .models import Lead, KPFile
    days = [datetime.date.today() - datetime.timedelta(days=i) for i in range(13, -1, -1)]
    labels, leads, kps = [], [], []
    for d in days:
        d1 = datetime.datetime.combine(d, datetime.time.min)
        d2 = datetime.datetime.combine(d, datetime.time.max)
        labels.append(d.strftime("%Y-%m-%d"))
        leads.append(Lead.query.filter(Lead.created_at >= d1, Lead.created_at <= d2).count())
        kps.append(KPFile.query.filter(KPFile.created_at >= d1, KPFile.created_at <= d2).count())
    from flask import jsonify
    return jsonify({"labels": labels, "leads": leads, "kps": kps})


# ---------- Leads ----------
def _paginate(query, per_page=15):
    page = max(int(request.args.get("page", 1)), 1)
    total = query.count()
    pages = math.ceil(total / per_page) if per_page else 1
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, page, pages, total

@bp.route("/leads")
@login_required
def leads():
    q = request.args.get("q", "").strip()
    base = Lead.query
    if q:
        like = f"%{q}%"
        base = base.filter((Lead.company.ilike(like)) | (Lead.contact_name.ilike(like)) | (Lead.email.ilike(like)) | (Lead.phone.ilike(like)))
    base = base.order_by(Lead.created_at.desc())
    items, page, pages, total = _paginate(base, per_page=20)
    return render_template("admin/leads.html", items=items, page=page, pages=pages, total=total, q=q)

@bp.route("/leads/new", methods=["GET", "POST"])
@login_required
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
        for k in ["company","contact_name","phone","email","site_type","goal","audience","budget","deadline","notes"]:
            setattr(lead, k, request.form.get(k))
        db.session.commit()
        flash("Лид обновлён", "success")
        return redirect(url_for("routes.lead_detail", lead_id=lead.id))
    return render_template("admin/lead_form.html", lead=lead)

@bp.route("/leads/<int:lead_id>/delete", methods=["POST"])
@login_required
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

# ---------- KP Files ----------
@bp.route("/kp")
@login_required
def kp_index():
    base = KPFile.query.order_by(KPFile.created_at.desc())
    items, page, pages, total = _paginate(base, per_page=20)
    return render_template("admin/kp_list.html", items=items, page=page, pages=pages, total=total)

@bp.route("/kp/upload", methods=["POST"])
@login_required
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

@bp.route("/kp/delete/<int:kp_id>", methods=["POST"])
@login_required
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
@login_required
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

# ---------- Maintenance / Bulk ----------
@bp.route("/maintenance/bulk_delete", methods=["POST"])
@login_required
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
