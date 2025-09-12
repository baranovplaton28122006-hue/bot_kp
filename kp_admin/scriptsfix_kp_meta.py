import re
from kp_admin import create_app, db
from kp_admin.models import KPFile

BAD = {"mail", "email", "почта"}

def sanitize_username(u):
    if not u:
        return None
    u = u.strip().lstrip("@")
    if u.lower() in BAD:
        return None
    return u if re.fullmatch(r"[A-Za-z0-9_]{3,32}", u) else None

FN_PHONE = re.compile(r"^KP_(\d{11,12})_", re.IGNORECASE)

def phone_from_filename(fn):
    m = FN_PHONE.match(fn or "")
    if m:
        return "+" + m.group(1)
    return None

app = create_app()
with app.app_context():
    updated = 0
    for k in KPFile.query.all():
        new_u = sanitize_username(k.username)
        new_p = k.phone or phone_from_filename(k.filename)
        changed = False
        if new_u != k.username:
            k.username = new_u
            changed = True
        if new_p != k.phone:
            k.phone = new_p
            changed = True
        if changed:
            updated += 1
    if updated:
        db.session.commit()
    print(f"Updated rows: {updated}")
