"""HTTP-level tests for sign-in and sign-out."""

from pathlib import Path

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


def test_valid_credentials_redirect_to_landing(client):
    response = client.post(
        "/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_valid_credentials_populate_the_session(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})

    with client.session_transaction() as session:
        assert session["user_id"] == 1
        assert session["user_name"] == "Demo User"
        assert "email" not in session
        assert "password_hash" not in session


def test_email_is_matched_case_insensitively(client):
    response = client.post(
        "/login", data={"email": "DEMO@Spendly.com", "password": DEMO_PASSWORD}
    )

    assert response.status_code == 302


def test_surrounding_whitespace_in_the_email_is_ignored(client):
    response = client.post(
        "/login", data={"email": "  demo@spendly.com  ", "password": DEMO_PASSWORD}
    )

    assert response.status_code == 302


def test_wrong_password_rerenders_with_a_generic_error(client):
    response = client.post(
        "/login", data={"email": DEMO_EMAIL, "password": "wrong-password"}
    )

    assert response.status_code == 200
    assert b"Incorrect email or password." in response.data
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_unknown_email_gives_the_identical_error(client):
    wrong_password = client.post(
        "/login", data={"email": DEMO_EMAIL, "password": "wrong-password"}
    )
    unknown_email = client.post(
        "/login", data={"email": "nobody@spendly.com", "password": DEMO_PASSWORD}
    )

    assert unknown_email.status_code == 200
    assert b"Incorrect email or password." in unknown_email.data
    # The two failures must be indistinguishable — no user enumeration.
    assert b"Incorrect email or password." in wrong_password.data


def test_empty_submission_is_rejected_without_a_400(client):
    response = client.post("/login", data={"email": "", "password": ""})

    assert response.status_code == 200
    assert b"All fields are required." in response.data


def test_missing_form_fields_do_not_400(client):
    response = client.post("/login", data={})

    assert response.status_code == 200
    assert b"All fields are required." in response.data


def test_whitespace_only_password_is_rejected(client):
    response = client.post("/login", data={"email": DEMO_EMAIL, "password": "   "})

    assert response.status_code == 200
    assert b"All fields are required." in response.data


def test_a_password_registered_with_padding_can_sign_in(client):
    """The hash is built from the raw string, so login must not strip either."""
    padded = "  spaced out  "
    client.post(
        "/register",
        data={"name": "Padded", "email": "padded@spendly.com", "password": padded},
    )

    response = client.post(
        "/login", data={"email": "padded@spendly.com", "password": padded}
    )

    assert response.status_code == 302


def test_login_form_action_uses_url_for():
    source = Path("templates/login.html").read_text()

    assert 'action="{{ url_for(\'login\') }}"' in source
    assert 'action="/login"' not in source


def test_failed_login_keeps_the_typed_email(client):
    response = client.post(
        "/login", data={"email": DEMO_EMAIL, "password": "wrong-password"}
    )

    assert b'value="demo@spendly.com"' in response.data


def test_login_page_renders_an_empty_email_field(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b'value=""' in response.data


def test_logout_redirects_to_landing(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})

    response = client.get("/logout")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_logout_clears_the_whole_session(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})

    client.get("/logout")

    with client.session_transaction() as session:
        assert "user_id" not in session
        assert "user_name" not in session


def test_logout_while_signed_out_is_harmless(client):
    response = client.get("/logout")

    assert response.status_code == 302


def test_logout_returns_no_placeholder_string(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})

    response = client.get("/logout")

    assert b"coming in Step 3" not in response.data


def test_other_stub_routes_are_untouched(client):
    assert b"Profile page \xe2\x80\x94 coming in Step 4" in client.get("/profile").data
    assert b"Add expense \xe2\x80\x94 coming in Step 7" in client.get("/expenses/add").data
    assert b"Edit expense \xe2\x80\x94 coming in Step 8" in client.get("/expenses/1/edit").data
    assert (
        b"Delete expense \xe2\x80\x94 coming in Step 9"
        in client.get("/expenses/1/delete").data
    )


# The landing page has its own "Sign in" ghost button (landing.html:98), so a
# bare b">Sign in<" check would match markup outside the navbar. Every nav
# assertion below is anchored to a nav-only class.
NAV_SIGNED_OUT = b'class="nav-cta">Get started<'
NAV_SIGNED_IN = b'class="nav-user">Demo User<'


def test_signed_out_nav_shows_sign_in_and_get_started(client):
    response = client.get("/")

    assert NAV_SIGNED_OUT in response.data
    assert b">Sign out<" not in response.data


def test_signed_in_nav_shows_the_name_and_sign_out(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})

    response = client.get("/")

    assert NAV_SIGNED_IN in response.data
    assert b">Sign out<" in response.data
    assert NAV_SIGNED_OUT not in response.data


def test_nav_returns_to_signed_out_after_logout(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    client.get("/logout")

    response = client.get("/")

    assert NAV_SIGNED_OUT in response.data
    assert NAV_SIGNED_IN not in response.data


def test_logout_flash_is_rendered(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})

    response = client.get("/logout", follow_redirects=True)

    assert b"You have been signed out." in response.data
    assert b"flash-success" in response.data


def test_flash_is_consumed_after_one_render(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    client.get("/logout", follow_redirects=True)

    response = client.get("/")

    assert b"You have been signed out." not in response.data
