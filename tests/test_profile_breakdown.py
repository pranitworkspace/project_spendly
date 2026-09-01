"""HTTP-level tests for the profile page's category-breakdown section.

Step 5's breakdown slice turns `get_category_breakdown()` rows into the
template's `breakdown` list, where `pct` is each category's share of the
*largest* category (not of the grand total) so the top bar always renders
full width. These tests cover the demo user's seeded data, a user with no
expenses, and a controlled two-expense case.
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


def test_breakdown_shows_one_row_per_category_with_top_bar_at_100(client):
    _sign_in(client)

    response = client.get("/profile")

    assert response.status_code == 200
    assert response.data.count(b'class="profile-bar-row"') == 7
    assert b'style="width: 100%"' in response.data


def test_breakdown_is_ordered_largest_first(client):
    _sign_in(client)

    response = client.get("/profile")

    assert (
        response.data.index(b"Shopping")
        < response.data.index(b"Bills")
        < response.data.index(b"Transport")
    )


def test_breakdown_pct_is_a_plain_integer(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b"width: 84%" in response.data
    assert b"width: 84.0%" not in response.data


def test_breakdown_amounts_are_rupee_formatted(client):
    _sign_in(client)

    response = client.get("/profile")

    assert "₹2,250.00".encode() in response.data


def test_breakdown_is_empty_for_a_user_with_no_expenses(client):
    _register_and_sign_in(client, "Zoe Fresh", "zoe@example.com")

    response = client.get("/profile")

    assert response.status_code == 200
    assert response.data.count(b'class="profile-bar-row"') == 0


def test_breakdown_pct_is_relative_to_the_top_category(client):
    user_id = _register_and_sign_in(client, "Zoe Fresh", "zoe2@example.com")
    _add_expense(user_id, 100.00, "Food", "2026-09-05", "Lunch")
    _add_expense(user_id, 400.00, "Shopping", "2026-09-06", "Shoes")

    response = client.get("/profile")

    assert response.status_code == 200
    assert b"width: 100%" in response.data
    assert b"width: 25%" in response.data
