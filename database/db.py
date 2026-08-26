"""SQLite data layer for Spendly.

All database access lives here — never inline in route functions.
Every query is parameterized with `?` placeholders.
"""

import calendar
import sqlite3
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

# Project root is the parent of the `database/` package directory.
# Resolved from __file__ so the path is stable regardless of the caller's cwd.
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "expense_tracker.db"

CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (id)
);
"""


def get_db():
    """Open and return a new SQLite connection to the project database.

    Sets `row_factory` so rows support access by column name, and enables
    foreign key enforcement — SQLite disables it by default on every new
    connection, so this must run each time.

    The caller owns the connection and is responsible for closing it.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the tables if they do not exist yet. Safe to call repeatedly."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert demo data on first run only. No-op if any user already exists."""
    conn = get_db()
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return

        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cursor.lastrowid

        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]

        # (day, amount, category, description) — 8 expenses across the 7
        # categories, so Food appears twice. Days stay <= 21 so they are valid
        # in every month; the clamp below keeps that true if one is ever raised.
        samples = (
            (2, 450.00, "Food", "Groceries"),
            (4, 120.50, "Transport", "Metro card top-up"),
            (7, 1899.00, "Bills", "Electricity bill"),
            (9, 650.00, "Health", "Pharmacy"),
            (12, 399.00, "Entertainment", "Movie tickets"),
            (15, 2250.00, "Shopping", "Running shoes"),
            (18, 780.25, "Food", "Dinner out"),
            (21, 300.00, "Other", "Gift"),
        )
        rows = [
            (
                user_id,
                amount,
                category,
                today.replace(day=min(day, last_day)).isoformat(),
                description,
            )
            for day, amount, category, description in samples
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
