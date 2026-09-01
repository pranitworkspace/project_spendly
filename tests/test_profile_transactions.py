"""HTTP-level tests for the profile page's transaction-history section.

Covers `_build_transactions` (app.py) via the `/profile` route: row count,
newest-first ordering, the LIMIT 10 cap, per-user scoping, the nullable
`description` column, and the date/amount formatting helpers it reuses.
"""

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


def test_profile_lists_all_seeded_transactions(client):
    _sign_in(client)

    response = client.get("/profile")

    assert response.status_code == 200
    assert response.data.count(b'class="profile-badge"') == 8


def test_profile_orders_transactions_newest_first(client):
    _sign_in(client)

    response = client.get("/profile")

    # Seed: "Gift" is the 21st, "Groceries" the 2nd — newest row comes first.
    assert response.data.index(b"Gift") < response.data.index(b"Groceries")


def test_profile_caps_transactions_at_ten(client):
    user_id = _register_and_sign_in(client, "Cap Test", "cap@example.com")
    for day in range(1, 13):
        _add_expense(user_id, 5.00, "Other", f"2026-09-{day:02d}", f"expense {day}")

    response = client.get("/profile")

    assert response.data.count(b'class="profile-badge"') == 10


def test_profile_scopes_transactions_to_the_signed_in_user(client):
    alice_id = _register_and_sign_in(client, "Alice A", "alice@example.com")
    _add_expense(alice_id, 20.00, "Food", "2026-09-05", "Alice only description")
    client.get("/logout")

    bob_id = _register_and_sign_in(client, "Bob B", "bob2@example.com")
    _add_expense(bob_id, 30.00, "Food", "2026-09-06", "Bob only description")

    # Currently signed in as Bob (registered/logged-in last).
    response = client.get("/profile")

    assert b"Bob only description" in response.data
    assert b"Alice only description" not in response.data

    # Switch back to Alice.
    client.get("/logout")
    client.post(
        "/login", data={"email": "alice@example.com", "password": "password123"}
    )
    response = client.get("/profile")

    assert b"Alice only description" in response.data
    assert b"Bob only description" not in response.data


def test_profile_renders_null_description_as_blank(client):
    user_id = _register_and_sign_in(client, "Null Desc", "nulldesc@example.com")
    _add_expense(user_id, 75.00, "Utilities", "2026-09-10", None)

    response = client.get("/profile")

    assert b'class="profile-badge"' in response.data
    assert "₹75.00".encode() in response.data
    assert b">None<" not in response.data


def test_profile_formats_transaction_dates_without_leading_zero(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b"2 Sep 2026" in response.data
    assert b"02 Sep 2026" not in response.data


def test_profile_formats_transaction_amounts_as_rupees(client):
    _sign_in(client)

    response = client.get("/profile")

    assert "₹450.00".encode() in response.data
