# Spec: Registration

## Overview

Turn `/register` into a working account-creation flow. Today the route is `GET`-only and simply renders `register.html`, so the form — which already posts to itself and already renders `{{ error }}` — returns a 405. This step fulfils that contract: accept the `POST`, validate the submitted fields, hash the password with werkzeug, insert the user through a new function in `database/db.py`, and send the visitor on to the login page. It is Step 2 of the Spendly roadmap and the first step that writes user data at runtime; login (Step 3) and everything gated behind a session depend on real accounts existing, and `seed_db()`'s demo user is not enough to build those against.

---

## Depends on

- **Step 1 — Database setup** (complete). Requires `get_db()`, `init_db()`, the `users` table with its `UNIQUE` email constraint, and the startup hook in `app.py` that creates the database.

No other steps are required. Registration must **not** log the new user in — sessions arrive in Step 3.

---

## Routes

- **GET `/register`** — render the empty registration form — public
- **POST `/register`** — validate input, create the user, redirect to `/login` on success; re-render `register.html` with `error` on failure — public

This is one view function with `methods=["GET", "POST"]`, not two. No other routes change.

---

## Database changes

**No database changes.** The `users` table already defined in `database/db.py` covers this feature exactly:

| Column | Used by registration |
| --- | --- |
| `id` | autoincrement, returned via `cursor.lastrowid` |
| `name` | from the `name` form field |
| `email` | from the `email` form field; `UNIQUE` already enforced |
| `password_hash` | `generate_password_hash(password)` |
| `created_at` | left to the schema default `datetime('now')` |

No new tables, columns, indexes, or constraints. Two **new functions** are added to `database/db.py` (see *Files to change*) — the schema itself is untouched.

---

## Templates

**Create:** None.

**Modify:**

- `templates/register.html` — change the form's hardcoded `action="/register"` to `action="{{ url_for('register') }}"`. CLAUDE.md forbids hardcoded internal URLs, and this is the only violation on the page. Nothing else changes: the `{% if error %}` block, the field names (`name`, `email`, `password`), and the `.auth-error` styling in `style.css` are already in place and correct.

---

## Files to change

- **`database/db.py`** — add two functions beside the existing ones:
  - `get_user_by_email(email)` — parameterized `SELECT` returning a `sqlite3.Row` or `None`. Used here for the duplicate-email check and reused by login in Step 3.
  - `create_user(name, email, password)` — hashes the password with `generate_password_hash`, inserts the row, commits, returns the new `id`. Both open a connection with `get_db()` and close it in a `finally:` block.
- **`app.py`** —
  - extend the imports to include `redirect`, `request`, and `url_for` from `flask`, and the two new db functions.
  - change `@app.route("/register")` to `@app.route("/register", methods=["GET", "POST"])` and implement the POST branch.

## Files to create

- None. (Tests for this step, if added, belong in the existing `tests/` directory and inherit the `temp_db` fixture from `conftest.py`.)

## New dependencies

**No new dependencies.** `flask` and `werkzeug` are already in `requirements.txt`; `werkzeug.security.generate_password_hash` is already imported and used in `database/db.py`.

---

## Rules for implementation

- **No SQLAlchemy or ORMs** — `sqlite3` only.
- **Parameterised queries only** — `?` placeholders, never f-strings or `%` formatting in SQL.
- **Passwords hashed with werkzeug** — `generate_password_hash`; never store or log the plaintext password.
- **Use CSS variables — never hardcode hex values.** No CSS is expected in this step; if any is added, pull from the `:root` block in `static/css/style.css`.
- **All templates extend `base.html`** — `register.html` already does; keep it that way.
- **No DB logic in route functions** — every query lives in `database/db.py`. The view calls `get_user_by_email()` / `create_user()` and nothing else touches SQLite.
- **Failures re-render, they do not redirect** — `return render_template("register.html", error="…")`, matching the contract the template already speaks. Only success redirects.
- **Use `url_for()`** for the post-success redirect (`url_for("login")`) and in the template's form action.
- **Callers close their connections** — `get_db()` hands back an open connection; wrap use in `try/finally: conn.close()`. `with conn:` is a transaction block and does *not* close it.
- **Do not implement session login here.** No `session[...]` writes, no `flash()`, no logout wiring — that is Step 3.
- **Do not touch other stub routes.** `/logout`, `/profile`, and the expense routes keep their placeholder strings.
- Validation rules, checked in this order, each re-rendering with a single message:
  1. `name`, `email`, `password` all present after `.strip()` → "All fields are required."
  2. password at least 8 characters (the field's placeholder promises this) → "Password must be at least 8 characters."
  3. email not already registered → "An account with that email already exists."
- Store the email lowercased and stripped so the `UNIQUE` constraint is not defeated by casing; the duplicate check must compare the same normalised form.
- The form does not repopulate fields after an error — the template has no `value=` bindings and adding them is out of scope for this step.

---

## Definition of done

Verified by running `venv/bin/python app.py` and using the app at `http://127.0.0.1:5001`:

- [ ] `GET /register` renders the form as before — no regression, page returns 200.
- [ ] Submitting the form no longer returns **405 Method Not Allowed**.
- [ ] Submitting valid details redirects to `/login` (browser URL ends in `/login`, not `/register`).
- [ ] The new account appears in the database with a hashed `password_hash` (starts with `scrypt:`), the given name, the lowercased email, and a populated `created_at`.
- [ ] Registering the **same email twice** re-renders the registration page showing "An account with that email already exists." — no second row is created, and no 500 from the `UNIQUE` constraint.
- [ ] Submitting a password shorter than 8 characters re-renders with the password error and creates no row.
- [ ] Submitting with a blank field (via a request that bypasses the browser's `required` attribute) re-renders with the required-fields error and creates no row.
- [ ] Every error case renders the styled `.auth-error` box inside the page — never a bare string, never a redirect.
- [ ] The rendered form's action points at `/register` via `url_for` — `grep -n 'action=' templates/register.html` shows no hardcoded path.
- [ ] `grep -n 'sqlite3\|SELECT\|INSERT' app.py` returns nothing — all SQL still lives in `database/db.py`.
- [ ] `venv/bin/pytest` passes.
