
from kp_admin import create_app, db
from kp_admin.models import User, Lead, KPFile
import click

app = create_app()

@app.shell_context_processor
def shell():
    return {"db": db, "User": User, "Lead": Lead, "KPFile": KPFile}

@app.cli.command("create-admin")
@app.cli.command("list-users")
def list_users():
    from app.models import User
    print([u.email for u in User.query.all()])

@app.cli.command("set-password")

@app.cli.command("create-admin")
@click.option("--email", required=True)
@click.option("--password", required=True)
def create_admin(email, password):
    if User.query.filter_by(email=email).first():
        click.echo("User already exists")
        return
    u = User(email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.echo(f"Admin created: {email}")

@click.option("--email", required=True)
@click.option("--password", required=True)
def set_password(email, password):
    from app.models import User, db
    u = User.query.filter_by(email=email).first()
    if not u:
        print("User not found")
        return
    u.set_password(password)
    db.session.commit()
    print("Password updated")
@click.option("--email", required=True)
@click.option("--password", required=True)
def create_admin(email, password):
    if User.query.filter_by(email=email).first():
        click.echo("User already exists")
        return
    u = User(email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.echo(f"Admin created: {email}")
