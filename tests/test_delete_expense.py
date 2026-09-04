"""Tests for Step 9 — delete expense.

Covers the `delete_expense` data-layer helper (database/db.py) and the
`POST /expenses/<id>/delete` route: the auth guard, the POST-only method
guard, ownership enforced in SQL (a foreign id and an unknown id are both a
404), the success flash, and the per-row Delete form on /profile.
"""

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


def _row_exists(expense_id):
    conn = db.get_db()
    try:
        return (
            conn.execute(
                "SELECT COUNT(*) FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def _an_expense_id(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? ORDER BY id LIMIT 1",
            (user_id,),
        ).fetchone()["id"]
    finally:
        conn.close()


def _other_user_expense():
    """A second account with one expense, built in the data layer.

    Not via POST /register: register() short-circuits to /profile for a
    signed-in session and would create nothing.
    """
    other_id = db.create_user("Other User", "other@spendly.com", "password123")
    return other_id, db.create_expense(other_id, 99.0, "Food", "2026-03-01", "Not yours")


# ------------------------------------------------------------------ #
# delete_expense — data layer                                         #
# ------------------------------------------------------------------ #

def test_delete_expense_removes_the_row():
    db.init_db()
    db.seed_db()
    uid = _demo_uid()
    expense_id = _an_expense_id(uid)

    assert db.delete_expense(expense_id, uid) is True
    assert not _row_exists(expense_id)


def test_delete_expense_leaves_the_users_other_rows_intact():
    db.init_db()
    db.seed_db()
    uid = _demo_uid()

    db.delete_expense(_an_expense_id(uid), uid)

    assert _expense_count(uid) == SEED_EXPENSE_COUNT - 1


def test_delete_expense_wrong_user_deletes_nothing():
    db.init_db()
    db.seed_db()
    uid = _demo_uid()
    expense_id = _an_expense_id(uid)
    other_id, _ = _other_user_expense()

    # Ownership is in the WHERE clause, so a mis-scoped call matches no rows
    # rather than deleting across accounts.
    assert db.delete_expense(expense_id, other_id) is False
    assert _row_exists(expense_id)
    assert _expense_count(uid) == SEED_EXPENSE_COUNT


def test_delete_expense_unknown_id_returns_false_and_does_not_raise():
    db.init_db()
    db.seed_db()
    uid = _demo_uid()

    assert db.delete_expense(999999, uid) is False
    assert _expense_count(uid) == SEED_EXPENSE_COUNT


# ------------------------------------------------------------------ #
# POST /expenses/<id>/delete — auth and method guards                 #
# ------------------------------------------------------------------ #

def test_delete_signed_out_redirects_to_login_and_keeps_the_row(client):
    uid = _demo_uid()
    expense_id = _an_expense_id(uid)

    response = client.post(f"/expenses/{expense_id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert _row_exists(expense_id)


def test_delete_signed_out_answers_real_and_unknown_ids_alike(client):
    """The auth guard runs first, so a signed-out probe learns nothing."""
    real_id = _an_expense_id(_demo_uid())

    real = client.post(f"/expenses/{real_id}/delete")
    unknown = client.post("/expenses/999999/delete")

    assert real.status_code == unknown.status_code == 302
    assert real.headers["Location"] == unknown.headers["Location"] == "/login"


def test_get_is_method_not_allowed_signed_out(client):
    # Method routing runs before the view, so this never reaches the auth
    # guard — a GET-able delete is exactly what the POST-only route prevents.
    assert client.get("/expenses/1/delete").status_code == 405


def test_get_is_method_not_allowed_signed_in(client):
    _sign_in(client)
    expense_id = _an_expense_id(_demo_uid())

    assert client.get(f"/expenses/{expense_id}/delete").status_code == 405
    assert _row_exists(expense_id)


def test_delete_with_stale_session_redirects_to_login(client):
    """A session pointing at an account that no longer exists is signed out."""
    uid = _demo_uid()
    expense_id = _an_expense_id(uid)

    # The user row is never deleted directly — PRAGMA foreign_keys = ON blocks
    # that while expenses reference it. Pointing the session at an id that was
    # never issued reaches the same guard.
    with client.session_transaction() as session:
        session["user_id"] = 999999
        session["user_name"] = "Ghost"

    response = client.post(f"/expenses/{expense_id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert _row_exists(expense_id)


# ------------------------------------------------------------------ #
# POST /expenses/<id>/delete — the happy path                         #
# ------------------------------------------------------------------ #

def test_delete_own_expense_removes_it_and_redirects_to_profile(client):
    _sign_in(client)
    uid = _demo_uid()
    expense_id = _an_expense_id(uid)

    response = client.post(f"/expenses/{expense_id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    assert not _row_exists(expense_id)
    assert _expense_count(uid) == SEED_EXPENSE_COUNT - 1


def test_delete_flashes_a_success_message(client):
    _sign_in(client)
    expense_id = _an_expense_id(_demo_uid())

    response = client.post(f"/expenses/{expense_id}/delete", follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Expense deleted." in body
    assert "flash-success" in body


def test_deleted_expense_disappears_from_the_transaction_table(client):
    _sign_in(client)
    expense_id = _an_expense_id(_demo_uid())

    client.post(f"/expenses/{expense_id}/delete")
    body = client.get("/profile").get_data(as_text=True)

    assert f"/expenses/{expense_id}/delete" not in body
    assert f"/expenses/{expense_id}/edit" not in body


# ------------------------------------------------------------------ #
# POST /expenses/<id>/delete — ownership                              #
# ------------------------------------------------------------------ #

def test_delete_another_users_expense_is_404_and_keeps_the_row(client):
    _sign_in(client)
    _, foreign_id = _other_user_expense()

    response = client.post(f"/expenses/{foreign_id}/delete")

    # 404 rather than 403: a 403 would confirm the id exists.
    assert response.status_code == 404
    assert _row_exists(foreign_id)


def test_delete_unknown_id_is_404(client):
    _sign_in(client)

    assert client.post("/expenses/999999/delete").status_code == 404


def test_foreign_and_unknown_ids_are_indistinguishable(client):
    _sign_in(client)
    _, foreign_id = _other_user_expense()

    foreign = client.post(f"/expenses/{foreign_id}/delete")
    unknown = client.post("/expenses/999999/delete")

    assert foreign.status_code == unknown.status_code == 404


def test_deleting_the_same_id_twice_is_404_the_second_time(client):
    _sign_in(client)
    expense_id = _an_expense_id(_demo_uid())

    first = client.post(f"/expenses/{expense_id}/delete")
    second = client.post(f"/expenses/{expense_id}/delete")

    assert first.status_code == 302
    assert second.status_code == 404


# ------------------------------------------------------------------ #
# The Delete control on /profile                                      #
# ------------------------------------------------------------------ #

def test_profile_row_has_a_delete_form_posting_to_the_right_url(client):
    _sign_in(client)
    expense_id = _an_expense_id(_demo_uid())
    body = client.get("/profile").get_data(as_text=True)

    assert f'action="/expenses/{expense_id}/delete"' in body
    assert 'method="POST"' in body


def test_profile_delete_control_is_never_a_link(client):
    """A GET-able delete is the bug the POST-only route exists to prevent."""
    _sign_in(client)
    expense_id = _an_expense_id(_demo_uid())
    body = client.get("/profile").get_data(as_text=True)

    assert f'href="/expenses/{expense_id}/delete"' not in body


def test_profile_delete_asks_for_confirmation(client):
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)

    assert "confirm(" in body
    assert "onsubmit" in body


def test_profile_still_offers_edit_alongside_delete(client):
    _sign_in(client)
    expense_id = _an_expense_id(_demo_uid())
    body = client.get("/profile").get_data(as_text=True)

    assert f'href="/expenses/{expense_id}/edit"' in body
    assert f'action="/expenses/{expense_id}/delete"' in body
