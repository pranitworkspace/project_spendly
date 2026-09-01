"""Tests for the data layer (database/db.py)."""

import sqlite3
from datetime import date

import pytest
from werkzeug.security import check_password_hash

from database.db import (
    CATEGORIES,
    create_user,
    get_category_breakdown,
    get_db,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)


def table_names(conn):
    """Return the project's own tables, excluding SQLite internals.

    AUTOINCREMENT makes SQLite create a `sqlite_sequence` table, so the
    `sqlite_%` filter is what keeps this at the two tables we declared.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def counts(conn):
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    expenses = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    return users, expenses


def test_get_db_returns_row_factory_connection():
    init_db()
    conn = get_db()
    try:
        row = conn.execute("SELECT 1 AS answer").fetchone()
        assert row["answer"] == 1
    finally:
        conn.close()


def test_get_db_enables_foreign_keys():
    init_db()
    conn = get_db()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_init_db_creates_both_tables():
    init_db()
    conn = get_db()
    try:
        assert table_names(conn) == ["expenses", "users"]
    finally:
        conn.close()


def test_init_db_is_idempotent():
    init_db()
    init_db()
    conn = get_db()
    try:
        assert table_names(conn) == ["expenses", "users"]
    finally:
        conn.close()


def test_seed_db_inserts_demo_user_and_eight_expenses():
    init_db()
    seed_db()
    conn = get_db()
    try:
        assert counts(conn) == (1, 8)

        user = conn.execute("SELECT * FROM users").fetchone()
        assert user["name"] == "Demo User"
        assert user["email"] == "demo@spendly.com"
        assert check_password_hash(user["password_hash"], "demo123")
        assert user["password_hash"] != "demo123"

        seeded = {r["category"] for r in conn.execute("SELECT category FROM expenses")}
        assert seeded == set(CATEGORIES)

        today = date.today()
        for row in conn.execute("SELECT date, amount FROM expenses"):
            parsed = date.fromisoformat(row["date"])
            assert (parsed.year, parsed.month) == (today.year, today.month)
            assert isinstance(row["amount"], float)
    finally:
        conn.close()


def test_seed_db_does_not_duplicate_on_repeat_calls():
    init_db()
    seed_db()
    seed_db()
    seed_db()
    conn = get_db()
    try:
        assert counts(conn) == (1, 8)
    finally:
        conn.close()


def test_description_is_nullable():
    """The spec makes `description` the one optional expense column."""
    init_db()
    seed_db()
    conn = get_db()
    try:
        user_id = conn.execute("SELECT id FROM users").fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
            (user_id, 42.0, "Other", date.today().isoformat()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT description FROM expenses WHERE amount = ?", (42.0,)
        ).fetchone()
        assert row["description"] is None
    finally:
        conn.close()


def test_duplicate_email_raises_integrity_error():
    init_db()
    seed_db()
    conn = get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Clone", "demo@spendly.com", "x"),
            )
    finally:
        conn.close()


def test_expense_with_invalid_user_id_raises_integrity_error():
    init_db()
    seed_db()
    conn = get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date) "
                "VALUES (?, ?, ?, ?)",
                (9999, 10.0, "Food", date.today().isoformat()),
            )
    finally:
        conn.close()


def test_create_user_returns_new_id_and_persists_row():
    init_db()
    user_id = create_user("Nitish Kumar", "nitish@example.com", "supersecret")
    assert isinstance(user_id, int)
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row["name"] == "Nitish Kumar"
        assert row["email"] == "nitish@example.com"
        assert row["created_at"]
    finally:
        conn.close()


def test_create_user_hashes_the_password():
    init_db()
    user_id = create_user("Nitish Kumar", "nitish@example.com", "supersecret")
    conn = get_db()
    try:
        stored = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()["password_hash"]
        assert stored != "supersecret"
        assert stored.startswith("scrypt:")
        assert check_password_hash(stored, "supersecret")
    finally:
        conn.close()


def test_create_user_returns_none_for_duplicate_email():
    init_db()
    assert create_user("First", "taken@example.com", "supersecret") is not None
    assert create_user("Second", "taken@example.com", "supersecret") is None
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    finally:
        conn.close()


def test_create_user_rejects_the_seeded_demo_email():
    init_db()
    seed_db()
    assert create_user("Clone", "demo@spendly.com", "supersecret") is None
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    finally:
        conn.close()


def test_get_user_by_email_returns_row_for_existing_user():
    init_db()
    seed_db()
    user = get_user_by_email("demo@spendly.com")
    assert user["name"] == "Demo User"


def test_get_user_by_email_returns_none_for_unknown_email():
    init_db()
    seed_db()
    assert get_user_by_email("nobody@example.com") is None


def test_get_user_by_email_does_not_match_other_casing():
    """SQLite compares TEXT case-sensitively — the caller normalises first."""
    init_db()
    seed_db()
    assert get_user_by_email("DEMO@spendly.com") is None


def test_create_user_reraises_integrity_errors_that_are_not_duplicates():
    """Only an email collision means "taken" — other constraints are bugs."""
    init_db()
    with pytest.raises(sqlite3.IntegrityError):
        create_user(None, "nameless@example.com", "supersecret")


# ------------------------------------------------------------------ #
# Profile reads (Step 5)                                              #
# ------------------------------------------------------------------ #


def _add_expense(user_id, amount, category, day, description="x"):
    """Insert one expense on 2026-09-<day> for `user_id`, return its new id."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, f"2026-09-{day:02d}", description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def test_get_user_by_id_returns_row_for_existing_user():
    init_db()
    seed_db()
    user = get_user_by_id(1)
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"


def test_get_user_by_id_returns_none_for_unknown_id():
    init_db()
    seed_db()
    assert get_user_by_id(9999) is None


def test_get_user_by_id_does_not_expose_the_password_hash():
    """The view renders this row's fields — the hash must never be one of them."""
    init_db()
    seed_db()
    user = get_user_by_id(1)
    assert "password_hash" not in user.keys()


def test_get_recent_expenses_returns_only_the_given_users_rows():
    init_db()
    seed_db()  # user 1, 8 expenses
    other = create_user("Other", "other@example.com", "supersecret")
    _add_expense(other, 10.0, "Food", 3, "not mine")

    rows = get_recent_expenses(1)

    assert len(rows) == 8
    assert all(r["description"] != "not mine" for r in rows)


def test_get_recent_expenses_orders_newest_first_then_by_id():
    init_db()
    user = create_user("Solo", "solo@example.com", "supersecret")
    first = _add_expense(user, 1.0, "Food", 10, "older")
    second = _add_expense(user, 2.0, "Food", 20, "newer")
    same_day = _add_expense(user, 3.0, "Food", 20, "newer same day")

    rows = get_recent_expenses(user)

    assert [r["id"] for r in rows] == [same_day, second, first]


def test_get_recent_expenses_respects_the_limit():
    init_db()
    user = create_user("Solo", "solo@example.com", "supersecret")
    for day in range(1, 16):
        _add_expense(user, 1.0, "Food", day)

    assert len(get_recent_expenses(user, limit=10)) == 10
    assert len(get_recent_expenses(user, limit=3)) == 3


def test_get_expense_summary_counts_and_sums_the_users_expenses():
    init_db()
    seed_db()

    summary = get_expense_summary(1)

    assert summary["tx_count"] == 8
    assert summary["total"] == pytest.approx(6848.75)


def test_get_expense_summary_is_zero_for_a_user_with_no_expenses():
    init_db()
    user = create_user("Fresh", "fresh@example.com", "supersecret")

    summary = get_expense_summary(user)

    assert summary["tx_count"] == 0
    assert summary["total"] == 0.0


def test_get_category_breakdown_groups_by_category_ordered_by_total_desc():
    init_db()
    user = create_user("Solo", "solo@example.com", "supersecret")
    _add_expense(user, 100.0, "Food", 1)
    _add_expense(user, 50.0, "Food", 2)
    _add_expense(user, 400.0, "Shopping", 3)
    _add_expense(user, 20.0, "Transport", 4)

    breakdown = get_category_breakdown(user)

    assert [(r["category"], r["total"]) for r in breakdown] == [
        ("Shopping", 400.0),
        ("Food", 150.0),
        ("Transport", 20.0),
    ]


def test_get_category_breakdown_omits_categories_with_no_spend():
    init_db()
    user = create_user("Solo", "solo@example.com", "supersecret")
    _add_expense(user, 10.0, "Food", 1)

    breakdown = get_category_breakdown(user)

    assert [r["category"] for r in breakdown] == ["Food"]
