"""HTTP-level tests for the Step 4 profile page.

The page renders hardcoded data this step — these tests assert the route guard,
the four sections, and the navbar entry point. Step 5 swaps the hardcoded context
for real queries and should leave every assertion here green.
"""

import re
from pathlib import Path
from unittest.mock import patch

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


def _sign_in(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})


def test_profile_redirects_when_signed_out(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_profile_returns_200_when_signed_in(client):
    _sign_in(client)

    response = client.get("/profile")

    assert response.status_code == 200


def test_profile_extends_base_layout(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b'<nav class="navbar">' in response.data
    assert b'class="footer"' in response.data
    assert "Profile — Spendly".encode() in response.data


def test_profile_shows_user_info_card(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b"Demo User" in response.data
    assert b"demo@spendly.com" in response.data
    assert b"Member since" in response.data
    assert b'class="profile-avatar"' in response.data


def test_profile_shows_summary_stats(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b'class="profile-stats"' in response.data
    assert b"Total spent" in response.data
    assert b"Transactions" in response.data
    assert b"Top category" in response.data
    assert response.data.count(b'class="profile-stat">') >= 3


def test_profile_shows_transaction_table(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b'class="profile-tx-table"' in response.data
    assert b"<thead" in response.data
    assert b"Amount" in response.data
    assert b"Groceries" in response.data
    assert response.data.count(b'class="profile-badge"') >= 3


def test_profile_shows_category_breakdown(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b"Category breakdown" in response.data
    assert b'class="profile-bar-track"' in response.data
    assert b"width:" in response.data
    assert response.data.count(b'class="profile-bar-row"') >= 3


def test_profile_uses_one_neutral_badge_class(client):
    _sign_in(client)

    response = client.get("/profile")

    # One shared badge class for every category — no per-category variants.
    assert response.data.count(b'class="profile-badge"') == 8
    assert b"profile-badge-food" not in response.data


def test_profile_does_not_leak_password_material(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b"password_hash" not in response.data
    assert b"scrypt" not in response.data
    assert b"pbkdf2" not in response.data


def test_profile_makes_no_db_call(client):
    _sign_in(client)

    with patch("database.db.get_db") as spy:
        client.get("/profile")

    assert spy.call_count == 0


def test_nav_user_links_to_profile(client):
    _sign_in(client)

    response = client.get("/")

    assert b'href="/profile" class="nav-user"' in response.data


def test_profile_template_has_no_hardcoded_hex():
    source = (
        Path(__file__).resolve().parent.parent / "templates" / "profile.html"
    ).read_text()

    assert re.search(r"#[0-9a-fA-F]{3,6}", source) is None
