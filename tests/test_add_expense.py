"""Tests for Step 7 — add expense.

Covers the `create_expense` data-layer helper (database/db.py) and the
`GET`/`POST /expenses/add` route: the auth guard, the validation ladder (each
failure re-renders the form with an `error` and writes nothing), a successful
insert scoped to the session user, and the navbar / profile entry points.
"""

from datetime import date

import database.db as db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

# seed_db() inserts exactly this many expenses for the demo user.
SEED_EXPENSE_COUNT = 8


def _sign_in(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})


def _demo_uid():
    return db.get_user_by_email(DEMO_EMAIL)["id"]


def _expense_count(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _valid_form(**overrides):
    data = {
        "amount": "50.0",
        "category": "Food",
        "date": date.today().isoformat(),
        "description": "Lunch",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------------ #
# create_expense — data layer                                         #
# ------------------------------------------------------------------ #

def test_create_expense_inserts_row():
    db.init_db()
    db.seed_db()
    uid = _demo_uid()

    new_id = db.create_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")
    assert isinstance(new_id, int)

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
    finally:
        conn.close()

    assert row["user_id"] == uid
    assert row["amount"] == 50.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"
    assert row["created_at"]


def test_create_expense_stores_none_description_as_null():
    db.init_db()
    db.seed_db()
    uid = _demo_uid()

    new_id = db.create_expense(uid, 12.0, "Other", "2026-03-20", None)

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
    finally:
        conn.close()

    assert row["description"] is None


def test_create_expense_rounds_amount_to_two_decimals():
    db.init_db()
    db.seed_db()
    uid = _demo_uid()

    new_id = db.create_expense(uid, 12.349, "Food", "2026-03-20", "x")

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
    finally:
        conn.close()

    assert row["amount"] == 12.35


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

def test_get_redirects_when_logged_out(client):
    response = client.get("/expenses/add")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_post_redirects_when_logged_out_and_writes_nothing(client):
    response = client.post("/expenses/add", data=_valid_form())

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert _expense_count(_demo_uid()) == SEED_EXPENSE_COUNT


# ------------------------------------------------------------------ #
# GET — the form                                                      #
# ------------------------------------------------------------------ #

def test_get_shows_form_when_logged_in(client):
    _sign_in(client)

    response = client.get("/expenses/add")
    body = response.data

    assert response.status_code == 200
    assert b"<form" in body
    assert b'method="POST"' in body
    assert b"<select" in body
    for category in db.CATEGORIES:
        assert category.encode() in body


def test_get_form_defaults_date_to_today(client):
    _sign_in(client)

    response = client.get("/expenses/add")

    assert f'value="{date.today().isoformat()}"'.encode() in response.data


# ------------------------------------------------------------------ #
# POST — success                                                      #
# ------------------------------------------------------------------ #

def test_post_valid_redirects_to_profile_and_inserts(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    response = client.post(
        "/expenses/add",
        data=_valid_form(amount="250.75", category="Transport", description="Cab"),
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    assert _expense_count(uid) == before + 1

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (uid,),
        ).fetchone()
    finally:
        conn.close()

    assert row["amount"] == 250.75
    assert row["category"] == "Transport"
    assert row["date"] == date.today().isoformat()
    assert row["description"] == "Cab"


def test_post_valid_expense_appears_on_profile(client):
    _sign_in(client)

    client.post(
        "/expenses/add",
        data=_valid_form(description="Uniquely-worded-lunch"),
    )
    response = client.get("/profile")

    assert b"Uniquely-worded-lunch" in response.data


def test_post_missing_description_saves_null(client):
    _sign_in(client)
    uid = _demo_uid()

    form = _valid_form()
    del form["description"]
    response = client.post("/expenses/add", data=form)

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT description FROM expenses WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (uid,),
        ).fetchone()
    finally:
        conn.close()

    assert row["description"] is None


# ------------------------------------------------------------------ #
# POST — validation failures re-render and write nothing              #
# ------------------------------------------------------------------ #

def test_post_missing_amount_rerenders(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    form = _valid_form()
    del form["amount"]
    response = client.post("/expenses/add", data=form)

    assert response.status_code == 200
    assert b"Amount is required." in response.data
    assert _expense_count(uid) == before


def test_post_zero_amount_rerenders(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    response = client.post("/expenses/add", data=_valid_form(amount="0"))

    assert response.status_code == 200
    assert b"Amount must be greater than 0." in response.data
    assert _expense_count(uid) == before


def test_post_non_finite_amount_rerenders(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    for bad in ("nan", "inf", "-inf", "1e999"):
        response = client.post("/expenses/add", data=_valid_form(amount=bad))
        assert response.status_code == 200, bad
        assert b"Amount must be greater than 0." in response.data, bad
        assert _expense_count(uid) == before, bad


def test_post_overlong_description_rerenders(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    response = client.post(
        "/expenses/add", data=_valid_form(description="x" * 201)
    )

    assert response.status_code == 200
    assert b"Description must be 200 characters or fewer." in response.data
    assert _expense_count(uid) == before


def test_post_non_numeric_amount_rerenders(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    response = client.post("/expenses/add", data=_valid_form(amount="abc"))

    assert response.status_code == 200
    assert b"Amount must be a number." in response.data
    assert _expense_count(uid) == before


def test_post_invalid_category_rerenders(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    response = client.post("/expenses/add", data=_valid_form(category="Crypto"))

    assert response.status_code == 200
    assert b"Choose a valid category." in response.data
    assert _expense_count(uid) == before


def test_post_invalid_date_rerenders(client):
    _sign_in(client)
    uid = _demo_uid()
    before = _expense_count(uid)

    response = client.post("/expenses/add", data=_valid_form(date="not-a-date"))

    assert response.status_code == 200
    assert b"Enter a valid date." in response.data
    assert _expense_count(uid) == before


def test_post_rerender_keeps_entered_values(client):
    _sign_in(client)

    response = client.post(
        "/expenses/add",
        data={
            "amount": "99.99",
            "category": "Transport",
            "date": "bad",
            "description": "Cab fare home",
        },
    )
    body = response.data

    assert response.status_code == 200
    assert b'value="99.99"' in body
    assert b'value="Cab fare home"' in body
    assert b"Transport" in body


# ------------------------------------------------------------------ #
# Entry points — navbar + profile button                             #
# ------------------------------------------------------------------ #

def test_navbar_shows_add_expense_when_logged_in(client):
    _sign_in(client)

    response = client.get("/profile")

    assert b'href="/expenses/add"' in response.data
    assert b"Add expense" in response.data


def test_navbar_hides_add_expense_when_logged_out(client):
    response = client.get("/")

    assert b"/expenses/add" not in response.data


def test_profile_has_add_expense_button(client):
    _sign_in(client)

    response = client.get("/profile")

    # One link in the navbar, one below the "Recent transactions" heading.
    assert response.data.count(b"/expenses/add") >= 2
