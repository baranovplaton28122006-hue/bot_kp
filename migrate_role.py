# migrate_role.py
from kp_admin import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # --- user.role ---
    cols = db.session.execute(text("PRAGMA table_info(user)")).fetchall()
    has_role = any(str(c[1]).lower() == "role" for c in cols)
    if not has_role:
        db.session.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(16)"))
        print("Added column user.role")

    db.session.execute(text(
        "UPDATE user SET role='admin' WHERE role IS NULL OR role=''"
    ))
    db.session.commit()
    print("Default role set to 'admin'")

    # --- lead.tg_user_id ---
    cols = db.session.execute(text("PRAGMA table_info(lead)")).fetchall()
    has_tg = any(str(c[1]).lower() == "tg_user_id" for c in cols)
    if not has_tg:
        try:
            db.session.execute(text("ALTER TABLE lead ADD COLUMN tg_user_id VARCHAR(32)"))
            db.session.commit()
            print("Added column lead.tg_user_id")
        except Exception as e:
            print("Skip tg_user_id:", e)

    print("Migration done.")
