"""HTTP-level tests for the profile page.

Step 4 built the page against hardcoded data; Step 5 swapped that context for
real `users` / `expenses` queries. These tests assert the route guard, the four
sections, the navbar entry point, and that the page now reflects the signed-in
user's own data from the database.
"""

import re
from pathlib import Path
from unittest.mock import patch

import database.db as db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


def _sign_in(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})


def _register_and_sign_in(client, name, email, password="password123"):
    client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )
    client.post("/login", data={"email": email, "password": password})
    return db.get_user_by_email(email)["id"]


def _add_expense(user_id, amount, category, iso_date, description):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, iso_date, description),
        )
        conn.commit()
    finally:
        conn.close()


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
    # The exact 8 is coupled to seed_db()'s expense count and to the recent-
    # transactions query's LIMIT 10 (>= 8, so all seed rows render).
    assert response.data.count(b'class="profile-badge"') == 8
    assert b"profile-badge-food" not in response.data


def test_profile_does_not_leak_password_material(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b"password_hash" not in response.data
    assert b"scrypt" not in response.data
    assert b"pbkdf2" not in response.data


def test_profile_queries_the_database(client):
    _sign_in(client)

    with patch("database.db.get_db", wraps=db.get_db) as spy:
        client.get("/profile")

    assert spy.call_count >= 1


def test_profile_reflects_the_signed_in_users_own_data(client):
    user_id = _register_and_sign_in(client, "Bob Jones", "bob@example.com")
    _add_expense(user_id, 1000.00, "Shopping", "2026-09-15", "Bob laptop bag")
    _add_expense(user_id, 200.00, "Food", "2026-09-16", "Bob lunch")

    response = client.get("/profile")

    assert b"Bob Jones" in response.data
    assert b"bob@example.com" in response.data
    assert b"Bob laptop bag" in response.data
    # The demo user's seeded expense must never appear on Bob's profile.
    assert b"Groceries" not in response.data
    assert "₹1,200.00".encode() in response.data  # Bob's real total
    assert b"Shopping" in response.data  # Bob's top category


def test_profile_lists_transactions_newest_first(client):
    _sign_in(client)

    response = client.get("/profile")

    # Seed: "Gift" is the 21st, "Groceries" the 2nd — newest row comes first.
    assert response.data.index(b"Gift") < response.data.index(b"Groceries")


def test_profile_handles_a_user_with_no_expenses(client):
    _register_and_sign_in(client, "Zoe Fresh", "zoe@example.com")

    response = client.get("/profile")

    assert response.status_code == 200
    assert "₹0.00".encode() in response.data
    assert response.data.count(b'class="profile-stat">') >= 3
    assert b'class="profile-badge"' not in response.data
    assert b'class="profile-bar-row"' not in response.data


def test_nav_user_links_to_profile(client):
    _sign_in(client)

    response = client.get("/")

    assert b'href="/profile" class="nav-user"' in response.data


def test_profile_template_has_no_hardcoded_hex():
    source = (
        Path(__file__).resolve().parent.parent / "templates" / "profile.html"
    ).read_text()

    assert re.search(r"#[0-9a-fA-F]{3,6}", source) is None
