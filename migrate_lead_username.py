from kp_admin import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    cols = db.session.execute(text("PRAGMA table_info(lead)")).fetchall()
    have = {str(c[1]).lower() for c in cols}
    if "username" not in have:
        db.session.execute(text("ALTER TABLE lead ADD COLUMN username VARCHAR(64)"))
        print("Added lead.username")
    if "name" not in have:
        db.session.execute(text("ALTER TABLE lead ADD COLUMN name VARCHAR(255)"))
        print("Added lead.name")
    db.session.commit()
    print("OK")
