"""Start SARAS:  python run.py   ->  http://localhost:5000
First run creates the database and loads demo data automatically."""
from app import create_app
from app.extensions import db
from app.models import User
from app.seed import run as seed

app = create_app()
with app.app_context():
    db.create_all()
    if not User.query.first():
        seed(app)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
