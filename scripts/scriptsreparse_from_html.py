# scripts/reparse_from_html.py
from kp_admin import create_app, db
from kp_admin.models import KPFile
from kp_admin.utils import parse_kp_file_meta, _sanitize_username  # type: ignore
import os

def uploads_folder(app) -> str:
    return os.path.abspath(
        os.path.join(app.root_path, app.config["UPLOAD_FOLDER"])
    )

app = create_app()
with app.app_context():
    base = uploads_folder(app)
    updated = 0
    for k in KPFile.query.all():
        path = os.path.join(base, k.filename)
        if not os.path.exists(path):
            continue
        meta = parse_kp_file_meta(path) or {}
        changed = False

        new_phone = meta.get("phone") or k.phone
        new_user  = _sanitize_username(meta.get("username")) or None  # пусто если мусор

        if new_phone != k.phone:
            k.phone = new_phone; changed = True
        if new_user != (k.username or None):
            k.username = new_user; changed = True

        if changed:
            updated += 1
    if updated:
        db.session.commit()
    print(f"Updated: {updated}")
