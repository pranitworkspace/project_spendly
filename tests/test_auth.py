"""HTTP-level tests for sign-in and sign-out."""

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


def test_login_page_renders(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"Welcome back" in response.data


def test_client_uses_the_throwaway_database(client, temp_db):
    from database.db import get_user_by_email

    assert temp_db.exists()
    assert get_user_by_email(DEMO_EMAIL) is not None


def test_app_has_a_secret_key(client):
    import app as app_module

    assert app_module.app.secret_key


def test_session_is_writable(client):
    with client.session_transaction() as session:
        session["probe"] = "ok"

    with client.session_transaction() as session:
        assert session["probe"] == "ok"
