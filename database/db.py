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


# ------------------------------------------------------------------ #
# Users — registration (Step 2) and, later, login                     #
# ------------------------------------------------------------------ #


def get_user_by_email(email):
    """Return the user row for `email`, or None if no such account exists.

    `email` must arrive already normalised — stripped and lowercased by the
    caller. SQLite's default TEXT collation is case-sensitive, so "A@b.com"
    and "a@b.com" are distinct keys to both this lookup and the UNIQUE index
    on users.email; normalising in one place is what keeps them the same
    account.

    The returned row stays readable after the connection closes.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()


def create_user(name, email, password):
    """Hash `password`, insert the user, and return the new row's id.

    Returns None if the email is already registered. `created_at` is left to
    the schema default.

    The UNIQUE index on users.email is the real authority here: a caller's
    duplicate check can go stale between its lookup and this insert, so the
    IntegrityError is handled rather than allowed to escape as a 500. Only the
    email collision is swallowed — a NOT NULL violation is a caller's bug and
    is re-raised rather than reported as a taken email.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        if "users.email" not in str(exc):
            raise
        conn.rollback()
        return None
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Return the user row for `user_id`, or None if no such account exists.

    The session carries `user_id` (Step 3); a page that needs the full record —
    name, email, created_at — looks it up here rather than widening what the
    session stores. This is the id-keyed companion to get_user_by_email(), which
    Step 3 deliberately deferred until a step needed it.

    The column list is explicit on purpose: `password_hash` must never travel
    out of the data layer toward a template context, so it is not selected.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Expenses — profile reads (Step 5), optional date filter (Step 6)    #
# ------------------------------------------------------------------ #


def _date_range_sql(date_from, date_to):
    """SQL fragment and params for an optional inclusive date range.

    The fragment is meant to be appended straight after an existing
    ``WHERE user_id = ?`` clause. It is all-or-nothing: unless *both* bounds
    are given this returns ``("", [])``, so an unfiltered call emits the exact
    same query it did before Step 6. `date_from`/`date_to` are ISO
    `YYYY-MM-DD` strings — `expenses.date` is TEXT and SQLite compares it
    lexicographically, so `BETWEEN` on zero-padded ISO is a calendar compare.
    """
    if date_from is None or date_to is None:
        return "", []
    return " AND date BETWEEN ? AND ?", [date_from, date_to]


def get_recent_expenses(user_id, limit=10, date_from=None, date_to=None):
    """Return `user_id`'s most recent expenses, newest first, capped at `limit`.

    Ordered by `date` then `id` so that expenses sharing a date fall in
    insertion order with the newest first. Powers the profile page's "Recent
    transactions" table, which shows only a recent window rather than the whole
    history. When `date_from` and `date_to` are both given, the window is
    further narrowed to that inclusive range (Step 6's date filter); the
    `limit` still applies within it.
    """
    frag, date_params = _date_range_sql(date_from, date_to)
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, amount, category, date, description "
            "FROM expenses WHERE user_id = ?" + frag +
            " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *date_params, limit),
        ).fetchall()
    finally:
        conn.close()


def get_expense_summary(user_id, date_from=None, date_to=None):
    """Return a single row of (`tx_count`, `total`) for `user_id`'s expenses.

    COALESCE keeps `total` a float `0.0` rather than NULL when the user has no
    expenses yet, so the caller never has to special-case the empty account.
    When `date_from` and `date_to` are both given, only expenses in that
    inclusive range are counted (Step 6's date filter).
    """
    frag, date_params = _date_range_sql(date_from, date_to)
    conn = get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS tx_count, COALESCE(SUM(amount), 0.0) AS total "
            "FROM expenses WHERE user_id = ?" + frag,
            (user_id, *date_params),
        ).fetchone()
    finally:
        conn.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Return `user_id`'s spend per category as rows of (`category`, `total`).

    Largest total first; ties broken alphabetically for a stable order.
    Categories the user has never spent in are absent from the result, so the
    first row is both the top category and the denominator for the profile
    page's breakdown bars. When `date_from` and `date_to` are both given, only
    expenses in that inclusive range feed the totals (Step 6's date filter).
    """
    frag, date_params = _date_range_sql(date_from, date_to)
    conn = get_db()
    try:
        return conn.execute(
            "SELECT category, SUM(amount) AS total "
            "FROM expenses WHERE user_id = ?" + frag +
            " GROUP BY category ORDER BY total DESC, category ASC",
            (user_id, *date_params),
        ).fetchall()
    finally:
        conn.close()


def create_expense(user_id, amount, category, expense_date, description=None):
    """Insert one expense for `user_id` and return the new row's id.

    `amount` is rounded to 2 decimals here so paise precision is enforced in the
    data layer — the same way password hashing lives in create_user(). A
    `description` of None lands as SQL NULL (the column is nullable). `created_at`
    is left to the schema default.

    The parameter is `expense_date`, not `date`: this module does
    `from datetime import date` at import time, so a `date` parameter would
    shadow it. The stored column is still named `date`.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, round(amount, 2), category, expense_date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()
