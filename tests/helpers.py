from app.extensions import db
from app.models import User


def make_user(email="user@example.com", password="Password123", role="user", name="Test User"):
    user = User(full_name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email="user@example.com", password="Password123"):
    return client.post("/login", data={"email": email, "password": password})