from app.extensions import db
from app.models import TrustedContact, User
from tests.helpers import login, make_user


def test_register_creates_user_with_hashed_password(client):
    response = client.post("/register", data={
        "full_name": "Asha Patil",
        "email": "Asha@Example.com",
        "phone": "+91 98765 43210",
        "password": "Password123",
        "confirm_password": "Password123",
    })
    assert response.status_code == 302
    user = User.query.filter_by(email="asha@example.com").first()
    assert user is not None
    assert user.password_hash != "Password123"
    assert user.role == "user"
    assert user.phone == "+919876543210"


def test_register_rejects_duplicate_email(client):
    make_user("dup@example.com")
    response = client.post("/register", data={
        "full_name": "Someone",
        "email": "dup@example.com",
        "password": "Password123",
        "confirm_password": "Password123",
    })
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert User.query.count() == 1


def test_register_rejects_weak_password(client):
    response = client.post("/register", data={
        "full_name": "Someone",
        "email": "weak@example.com",
        "password": "password",
        "confirm_password": "password",
    })
    assert response.status_code == 200
    assert b"at least one letter and one number" in response.data
    assert User.query.count() == 0


def test_login_success(client):
    make_user()
    response = login(client)
    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]
    assert client.get("/dashboard").status_code == 200


def test_login_wrong_password(client):
    make_user()
    response = login(client, password="WrongPassword1")
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_regular_user_cannot_open_admin_page(client):
    make_user()
    login(client)
    assert client.get("/admin/").status_code == 403


def test_admin_can_open_admin_page(client):
    make_user("admin@example.com", role="admin")
    login(client, email="admin@example.com")
    assert client.get("/admin/").status_code == 200


def test_logout(client):
    make_user()
    login(client)
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_login_ignores_external_next_url(client):
    make_user()
    response = client.post(
        "/login?next=https://evil.com/",
        data={"email": "user@example.com", "password": "Password123"},
    )
    assert response.status_code == 302
    assert "evil.com" not in response.headers["Location"]


def test_user_can_add_contact(client):
    make_user()
    login(client)
    response = client.post("/contacts/add", data={
        "contact_name": "Mother",
        "contact_phone": "9876543210",
        "contact_relation": "Mother",
    })
    assert response.status_code == 302
    assert TrustedContact.query.count() == 1


def test_user_cannot_delete_another_users_contact(client):
    owner = make_user("owner@example.com")
    contact = TrustedContact(user_id=owner.id, name="Friend", phone="9876543210")
    db.session.add(contact)
    db.session.commit()

    make_user("intruder@example.com")
    login(client, email="intruder@example.com")
    response = client.post(f"/contacts/{contact.id}/delete")
    assert response.status_code == 404
    assert TrustedContact.query.count() == 1