import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.seed import run as seed


@pytest.fixture(scope="module")
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        seed(app, verbose=False)
    yield app


def login(app, user, pw):
    c = app.test_client()
    r = c.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.get_json()
    return c


@pytest.fixture
def student(app):
    return login(app, "akash", "akash123")


@pytest.fixture
def teacher(app):
    return login(app, "khan", "khan123")


@pytest.fixture
def admin(app):
    return login(app, "admin", "admin123")
