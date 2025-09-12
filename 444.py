from kp_admin import create_app, db
from kp_admin.models import KPFile
app = create_app()
with app.app_context():
    print("kp count:", KPFile.query.count())