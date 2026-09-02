"""Step 7 — Add Expense.

Tests are written against `.claude/specs/07-add-expense.md`, i.e. what the
feature is supposed to do, not how the route happens to be coded.

Covered contract:
- data-layer insert helper persists a row; a `None` description lands as SQL NULL
- `GET  /expenses/add` — login-guarded; when allowed, renders a POST form with a
  category `<select>` listing all 7 fixed categories and amount/category/date/
  description fields
- `POST /expenses/add` — login-guarded; valid data inserts one row for the
  signed-in user and redirects to `/profile`
- `POST` validation: missing / zero / non-numeric amount, category outside the
  fixed 7, malformed date each re-render the form (200) with an error message and
  no row written, keeping the other entered values
- an omitted / blank description is accepted and stored as NULL
- navbar exposes an "Add Expense" link only while signed in
- the profile page links to `/expenses/add`

The real data-layer module is `database/db.py` (the spec's `database/queries.py`
does not exist); the insert helper there is `create_expense(user_id, amount,
category, expense_date, description=None)`.
"""

import pytest

import database.db as db
from database.db import create_expense

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

ADD_URL = "/expenses/add"
LOGIN_URL = "/login"
PROFILE_URL = "/profile"

# The 7 fixed categories, per the spec — hardcoded here as the contract rather
# than imported from the module under test.
CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)

VALID_FORM = {
    "amount": "50.0",
    "category": "Food",
    "date": "2026-03-20",
    "description": "Lunch",
}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _sign_in(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post(LOGIN_URL, data={"email": email, "password": password})


def _demo_id():
    return db.get_user_by_email(DEMO_EMAIL)["id"]


def _expenses_for(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def _location(response):
    return response.headers.get("Location", "")


def _form(**overrides):
    """A valid form payload with `overrides` applied; a value of None drops the key."""
    data = dict(VALID_FORM)
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


# --------------------------------------------------------------------------- #
# Data layer — create_expense                                                 #
# --------------------------------------------------------------------------- #

class TestCreateExpenseHelper:
    def test_valid_insert_persists_a_row(self, client):
        user_id = _demo_id()

        new_id = create_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        assert isinstance(new_id, int), "helper should return the new row id"
        conn = db.get_db()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE id = ?", (new_id,)
            ).fetchone()
        finally:
            conn.close()

        assert row is not None, "expense row was not inserted"
        assert row["user_id"] == user_id
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_none_description_is_stored_as_sql_null(self, client):
        user_id = _demo_id()

        new_id = create_expense(user_id, 12.5, "Bills", "2026-03-21", None)

        conn = db.get_db()
        try:
            row = conn.execute(
                "SELECT id FROM expenses WHERE id = ? AND description IS NULL",
                (new_id,),
            ).fetchone()
        finally:
            conn.close()

        assert row is not None, "description=None must be stored as SQL NULL"


# --------------------------------------------------------------------------- #
# GET /expenses/add                                                           #
# --------------------------------------------------------------------------- #

class TestGetAddExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get(ADD_URL)

        assert response.status_code == 302, "logged-out GET must redirect"
        assert LOGIN_URL in _location(response), "redirect target should be /login"

    def test_authenticated_renders_post_form(self, client):
        _sign_in(client)

        response = client.get(ADD_URL)

        assert response.status_code == 200
        body = response.data.lower()
        assert b"<form" in body, "expected an add-expense <form>"
        assert b'method="post"' in body, "form must submit via POST"
        assert b"<select" in body, "category field should be a <select>"

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_form_lists_every_fixed_category(self, client, category):
        _sign_in(client)

        response = client.get(ADD_URL)

        assert response.status_code == 200
        assert category.encode() in response.data, (
            f"category {category!r} missing from the form"
        )

    def test_form_exposes_all_input_fields(self, client):
        _sign_in(client)

        response = client.get(ADD_URL)

        for field in (
            b'name="amount"',
            b'name="category"',
            b'name="date"',
            b'name="description"',
        ):
            assert field in response.data, f"{field!r} missing from the form"


# --------------------------------------------------------------------------- #
# POST /expenses/add — auth guard + happy path                                #
# --------------------------------------------------------------------------- #

class TestPostAddExpenseHappyPath:
    def test_unauthenticated_redirects_to_login(self, client):
        response = client.post(ADD_URL, data=_form())

        assert response.status_code == 302, "logged-out POST must redirect"
        assert LOGIN_URL in _location(response), "redirect target should be /login"

    def test_valid_data_redirects_to_profile_and_inserts_row(self, client):
        _sign_in(client)
        user_id = _demo_id()
        before = len(_expenses_for(user_id))

        response = client.post(ADD_URL, data=_form())

        assert response.status_code == 302
        assert PROFILE_URL in _location(response), "success should redirect to /profile"

        rows = _expenses_for(user_id)
        assert len(rows) == before + 1, "exactly one expense row should be added"
        match = [
            r for r in rows
            if r["date"] == "2026-03-20" and r["description"] == "Lunch"
        ]
        assert len(match) == 1, "the submitted expense was not persisted"
        assert match[0]["amount"] == 50.0
        assert match[0]["category"] == "Food"
        assert match[0]["user_id"] == user_id

    @pytest.mark.parametrize(
        "desc_override",
        [{"description": None}, {"description": ""}, {"description": "   "}],
        ids=["omitted", "empty", "whitespace"],
    )
    def test_blank_description_is_accepted_and_stored_as_null(self, client, desc_override):
        _sign_in(client)
        user_id = _demo_id()

        response = client.post(
            ADD_URL, data=_form(date="2026-03-22", **desc_override)
        )

        assert response.status_code == 302, "a blank description is not an error"
        assert PROFILE_URL in _location(response)

        conn = db.get_db()
        try:
            row = conn.execute(
                "SELECT id FROM expenses "
                "WHERE user_id = ? AND date = ? AND description IS NULL",
                (user_id, "2026-03-22"),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "missing description should persist as SQL NULL"

    def test_description_is_stored_literally_not_interpolated(self, client):
        _sign_in(client)
        user_id = _demo_id()
        payload = "'); DROP TABLE expenses; --"

        response = client.post(
            ADD_URL, data=_form(date="2026-03-25", description=payload)
        )

        assert response.status_code == 302
        rows = [r for r in _expenses_for(user_id) if r["date"] == "2026-03-25"]
        assert len(rows) == 1, "parameterised insert should store the value verbatim"
        assert rows[0]["description"] == payload


# --------------------------------------------------------------------------- #
# POST /expenses/add — validation                                             #
# --------------------------------------------------------------------------- #

class TestPostAddExpenseValidation:
    @pytest.mark.parametrize(
        "override",
        [
            {"amount": None},
            {"amount": "0"},
            {"amount": "abc"},
            {"category": "Groceries"},
            {"date": "not-a-date"},
        ],
        ids=[
            "missing-amount",
            "zero-amount",
            "non-numeric-amount",
            "invalid-category",
            "invalid-date",
        ],
    )
    def test_invalid_input_rerenders_form_with_error_and_no_row(self, client, override):
        _sign_in(client)
        user_id = _demo_id()
        before = len(_expenses_for(user_id))

        response = client.post(ADD_URL, data=_form(**override))

        assert response.status_code == 200, "a rejected submission re-renders the form"
        assert b"<form" in response.data.lower(), "the form should be shown again"
        assert b"error" in response.data.lower(), "expected a visible error message"
        assert len(_expenses_for(user_id)) == before, (
            "an invalid submission must not write a row"
        )

    def test_failed_submission_preserves_other_entered_values(self, client):
        _sign_in(client)

        # Category is invalid, so the form bounces; the rest must survive.
        response = client.post(
            ADD_URL,
            data=_form(
                amount="77.77",
                category="Groceries",
                date="2026-03-20",
                description="Movie night",
            ),
        )

        assert response.status_code == 200
        assert b"77.77" in response.data, "entered amount should be re-populated"
        assert b"Movie night" in response.data, "entered description should be re-populated"
        assert b"2026-03-20" in response.data, "entered date should be re-populated"


# --------------------------------------------------------------------------- #
# Navigation — navbar link + profile-page link                               #
# --------------------------------------------------------------------------- #

class TestAddExpenseNavigation:
    def test_navbar_shows_add_expense_link_when_signed_in(self, client):
        _sign_in(client)

        response = client.get(PROFILE_URL)

        assert response.status_code == 200
        assert b"Add expense" in response.data, "navbar should offer an Add expense link"
        assert ADD_URL.encode() in response.data, "link should point at /expenses/add"

    def test_navbar_hides_add_expense_link_when_signed_out(self, client):
        response = client.get("/")

        assert response.status_code == 200
        assert ADD_URL.encode() not in response.data, (
            "the Add Expense link must not show for logged-out visitors"
        )

    def test_profile_page_links_to_the_add_expense_form(self, client):
        _sign_in(client)

        response = client.get(PROFILE_URL)

        assert response.status_code == 200
        assert response.data.count(ADD_URL.encode()) >= 1, (
            "profile page should link to /expenses/add"
        )
        assert b"Add expense" in response.data
