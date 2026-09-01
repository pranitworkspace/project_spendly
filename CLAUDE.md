# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Spendly is a lightweight personal expense tracker built with Flask and SQLite. This is a **teaching scaffold** (CampusX course): the entire frontend (templates, CSS) is complete and polished, while the backend is a set of numbered exercises left for students to implement.

---

## Architecture

**Where things belong:**
- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` only, never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → add a section to `style.css` (there is currently no per-page CSS file split), not inline `<style>` tags

**Templates use Jinja2 inheritance** — every page extends `base.html`. Links and static assets are built with `url_for()` (e.g. `url_for('login')`, `url_for('static', filename='css/style.css')`) — never hardcoded paths.

**The auth templates speak a contract the view must honour:** `register.html` and `login.html` submit `POST` to their own routes and render `{{ error }}` if the view passes one — a failed attempt is `render_template("login.html", error="...")`, never a redirect. Only success redirects. Both `/register` and `/login` fulfil this as of Steps 2 and 3.

---

## Code style

- Python: PEP 8, snake_case for variables and functions
- Templates: `url_for()` for every internal link — never hardcode URLs
- Route functions: one responsibility — fetch data, render template, done
- DB queries: always parameterized (`?` placeholders) — never f-strings in SQL
- Error handling: use `abort()` for HTTP errors, not bare `return "error string"`

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks
- **SQLite only** — no PostgreSQL, no SQLAlchemy ORM, no external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages
- **No new pip packages** — work within `requirements.txt` as-is unless explicitly told otherwise

---

## Subagent policy

- Always use a builtin Explore subagent for codebase exploration before implementing any new feature
- Always use a subagent to verify test results after any implementation
- When asked to plan, delegate codebase research to a subagent before presenting the plan
- Always use a builtin Plan subagent in plan mode

---

## Commands

Claude Code should invoke the venv's binaries directly (`venv/bin/python`, `venv/bin/pytest`) since shell state doesn't persist across tool calls; `source venv/bin/activate` is for interactive human use.

```bash
# Run dev server (port 5001, not the Flask default 5000 — don't change this)
venv/bin/python app.py

# Tests
venv/bin/pytest
venv/bin/pytest tests/test_db.py::test_name   # a single test
```

No linter/formatter is configured in this repo.

---

## Build order

`app.py` marks its stub routes with a literal string naming the step that implements them (`"Add expense — coming in Step 7"`), so the current state is always readable from the file itself.

Step 1 (`database/db.py`), Step 2 (registration), Step 3 (login, session, logout), and Step 4 (profile page) are done. `/profile` renders its four sections (user card, summary stats, transaction table, category breakdown) from **hardcoded dicts/lists in `app.py`** — Step 5 swaps that context for real `users`/`expenses` queries via `database/db.py` with no template change. The remaining order is: wire the profile DB (Step 5), then expense CRUD. As of Step 4 `/profile` is the post-login home: a successful login, and a signed-in visitor hitting `/login` or `/register`, all redirect to `url_for("profile")` (Step 3 parked these on the landing page only because no signed-in page existed yet). The signed-in navbar name links to `/profile`. Logout still redirects to the landing page.

**Conventions Steps 2-3 established, which everything after must match:**
- Emails are stored and looked up **stripped and lowercased**. SQLite compares TEXT case-sensitively, so normalising in the view is the only thing keeping `A@b.com` and `a@b.com` one account. `get_user_by_email()` expects an already-normalised value.
- Passwords are hashed **exactly as typed**, but validated on the stripped value — so login must not strip before calling `check_password_hash`, or padded passwords will never match.
- `create_user()` returns `None` for a taken email rather than raising, so the view never has to import `sqlite3`. It re-raises any other `IntegrityError`.
- Form fields are read with `request.form.get(key, "")` — the subscript form raises a 400 page instead of re-rendering with an error.
- `SECRET_KEY` is read from `SPENDLY_SECRET_KEY` with a dev fallback, set in `app.py` right after `app = Flask(__name__)`. `session[...]` and `flash()` work.
- The session holds exactly `user_id` (int) and `user_name` (str) — never the email, never the hash. `base.html` branches on `session.user_id`; expense routes will scope on `session["user_id"]`.
- Logout uses `session.clear()`, never a partial `pop()`.
- Auth failures use one generic message, `"Incorrect email or password."`, for both an unknown email and a wrong password — do not add a message that reveals whether an account exists.
- `flash(message, "success"|"error")` renders through the `.flash-stack` block in `base.html`; the CSS classes are `.flash-success` and `.flash-error`.

**Convention Step 4 established:**
- The signed-in navbar renders the user's name as `<a href="{{ url_for('profile') }}" class="nav-user">`, not a `<span>` — keep `class="nav-user"` as the last attribute. Its ink colour / 600 weight come from `.nav-links a.nav-user`, a specificity-bumped selector that beats the generic muted `.nav-links a` rule. A signed-in-only page guards with an inline `if not session.get("user_id"): return redirect(url_for("login"))` at the top of the view (no decorator).

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for a stub route** once its step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- **`get_db()` returns a fresh connection and does not close it** — callers must `try/finally: conn.close()`. Note `with conn:` is a *transaction* context manager and leaves the connection open
- The DB file is `expense_tracker.db` at the project root, gitignored and recreated (and reseeded) on startup if deleted
