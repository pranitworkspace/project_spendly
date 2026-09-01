"""HTTP-level tests for the profile page's summary stats section.

Step 5 wires `_build_stats` to real `get_expense_summary()` /
`get_category_breakdown()` results. These tests assert the three stat blocks
render with the correct label/value pairs for both a user with expenses and a
freshly registered user with none.
"""

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


def _sign_in(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})


def _register_and_sign_in(client, name, email, password="password123"):
    client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )
    client.post("/login", data={"email": email, "password": password})


def test_profile_stats_show_demo_users_totals(client):
    _sign_in(client)

    response = client.get("/profile")

    assert response.status_code == 200
    assert "₹6,848.75".encode() in response.data
    assert b"Shopping" in response.data
    assert b'<span class="profile-stat-value">8</span>' in response.data


def test_profile_stats_render_exactly_three_blocks(client):
    _sign_in(client)

    response = client.get("/profile")

    assert response.data.count(b'class="profile-stat">') == 3


def test_profile_stats_top_category_is_shopping_for_seed_user(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b'<span class="profile-stat-value">Shopping</span>' in response.data


def test_profile_stats_handle_a_user_with_no_expenses(client):
    _register_and_sign_in(client, "Zoe Fresh", "zoe@example.com")

    response = client.get("/profile")

    assert response.status_code == 200
    assert "₹0.00".encode() in response.data
    assert b'<span class="profile-stat-value">0</span>' in response.data
    assert "—".encode() in response.data
    assert response.data.count(b'class="profile-stat">') == 3


def test_profile_stats_total_uses_thousands_separator(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b"6,848.75" in response.data
