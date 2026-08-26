"""Tests for the Step 1 data layer (database/db.py)."""

import sqlite3
from datetime import date

import pytest
from werkzeug.security import check_password_hash

from database.db import CATEGORIES, get_db, init_db, seed_db


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
