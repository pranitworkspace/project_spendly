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

`app.py` used to mark its unbuilt routes with a literal string naming the step that would implement them (`"Delete expense — coming in Step 9"`), collected under a `# Placeholder routes` banner at the foot of the file. Step 9 emptied that section, so the banner is gone and there is no stub string left to read the build state from. Every route sits under its own `# <Feature> (Step N)` banner, in step order.

Steps 1-9 are done: Step 1 (`database/db.py`), Step 2 (registration), Step 3 (login, session, logout), Step 4 (profile page UI), Step 5 (profile page wired to the database), Step 6 (the `/profile` date filter), Step 7 (add expense), Step 8 (edit expense) and Step 9 (delete expense). `/profile` renders its four sections (user card, summary stats, transaction table, category breakdown) from **live `users`/`expenses` queries** via `database/db.py` — `templates/profile.html` was not changed to get there. **The numbered build is complete; nothing in `app.py` is a placeholder any more.** As of Step 4 `/profile` is the post-login home: a successful login, and a signed-in visitor hitting `/login` or `/register`, all redirect to `url_for("profile")` (Step 3 parked these on the landing page only because no signed-in page existed yet). The signed-in navbar name links to `/profile`. Logout still redirects to the landing page.

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

**Convention Step 5 established:**
- `database/db.py` gained four read helpers for `/profile`: `get_user_by_id(user_id)` (explicit column list — `id, name, email, created_at` — never `SELECT *`, so `password_hash` can't reach a template context), `get_recent_expenses(user_id, limit=10)` (`ORDER BY date DESC, id DESC LIMIT ?`, newest first, capped), `get_expense_summary(user_id)` (`COUNT`/`COALESCE(SUM(...), 0.0)` in one row), and `get_category_breakdown(user_id)` (`GROUP BY category ORDER BY total DESC`). All aggregation is SQL, in `db.py` — a view never sums or groups rows itself.
- The `/profile` view passes the template **plain dicts**, never a raw `sqlite3.Row` — Jinja's `row.attr` access fails silently on a `Row` (only `row["attr"]` works).
- Presentation formatting lives as `_`-prefixed module-level functions in `app.py` (`_rupees`, `_initials`, `_month_year`, `_tx_date`, plus the `_user_card`/`_build_stats`/`_build_transactions`/`_build_breakdown` view-model builders) — not in `db.py`, not in the template. Currency is `"₹" + f"{v:,.2f}"`; transaction dates are `f"{d.day} {d:%b %Y}"` (no leading-zero day); `member_since` is `"%B %Y"`.
- Category-breakdown `pct` is each category's share of the **largest** category (top row = 100), not a share of the grand total — that's what makes the top bar render full-width.
- A `session["user_id"]` that matches no row (deleted account) clears the session and redirects to `/login`, same as an absent one.

**Conventions Steps 7-8 established (expense writes):**
- Form validation for both add and edit lives in **one** helper, `_clean_expense_form(form)` in `app.py`. It returns `(fields, amount, error)`; `fields` holds the four stripped raw strings under the keys `amount`, `category`, `expense_date`, `description`. Note the HTML field is `name="date"` but the dict key is `expense_date` — do not "fix" that mismatch. A new expense route reuses this helper rather than restating the rules.
- Both expense form templates speak the same **flat** context: `categories`, `amount`, `category`, `expense_date`, `description`, optional `error` (plus `expense_id` for edit). This is what lets a bounced POST re-render with `**fields` and echo the **submitted** values rather than the stored row — never pass a `sqlite3.Row` as an `expense` object, since Jinja's `row.attr` fails silently on one.
- An `<input type="number">` is pre-filled with a bare `f"{value:.2f}"`, never `_rupees()` — the browser silently blanks the field for `₹450.00`.
- **Ownership is enforced in SQL, not in the view.** Any helper reaching a row by its id takes `user_id` too and puts both in the `WHERE` clause (`get_expense_by_id`, `update_expense`). A view must never fetch by id alone and then compare `row["user_id"]` itself.
- A row that does not exist and a row belonging to another user are answered **identically, with `abort(404)`** — never 403, which would confirm the id exists and turn the id space into an enumeration oracle. The ownership lookup happens before the GET/POST branch, so a POST at a foreign id is a 404 whatever its payload says.
- The auth guard runs **before** the ownership lookup, so a signed-out probe gets the same 302 for every id.
- `update_expense()` returns `True`/`False` from `cursor.rowcount`, never raises, and the view treats `False` as a 404 (the row was deleted between lookup and write). It rewrites only the four editable columns — `user_id`, `id` and `created_at` are left alone, so an edit can never move an expense to another account or restamp when it was logged.
- Edit flashes `"Expense updated."` on success; add stays silent. `/profile` lists only the 10 most recent rows, so an edited expense can move or drop out of view and a bare redirect would look like a no-op — a new expense is dated today and lands at the top, so it needs no such confirmation.
- `_build_transactions()` carries a raw `id` through to the template alongside the pre-formatted display strings; it is what each row's action link feeds to `url_for('edit_expense', id=...)` and what the Delete form posts to `url_for('delete_expense', id=...)`. Row actions live in a trailing `.profile-tx-actions` cell — as of Step 9 that cell holds both.

**Conventions Step 9 established (destructive actions):**
- `/expenses/<int:id>/delete` is **POST-only** (`methods=["POST"]`). A destructive action must not be reachable by following a link: a GET-able delete can be fired by a link prefetcher, a crawler or a cross-site `<img src>` with no click at all. Method routing runs **before** the view, so a `GET` here is a **405** — including for a signed-out visitor, who gets a 405 rather than the 302 every other guarded route gives. A test that probes this route signed out must use `POST`.
- **The scoped `DELETE` is the only ownership check.** `delete_expense()` in `database/db.py` runs `WHERE id = ? AND user_id = ?` and returns `cursor.rowcount > 0`; the view calls it directly and turns `False` into `abort(404)`. There is deliberately **no `get_expense_by_id()` pre-check**, unlike edit — a read before the write would only add a query and a window between the check and the delete, and answer nothing the rowcount does not. A missing row and another user's row stay indistinguishable, both 404, never 403.
- The `database.db` helper and the `app.py` view are **both** named `delete_expense`, so the import is **aliased**: `from database.db import delete_expense as db_delete_expense`. Without the alias, the `def delete_expense(id)` further down the module silently rebinds the name and the view recurses into itself — Python warns about nothing, and `@app.route` / `url_for('delete_expense')` both keep working, because Flask registers the endpoint from `__name__` at decoration time.
- Delete flashes `"Expense deleted."` on success, for the same reason edit flashes `"Expense updated."`: `/profile` re-renders ten rows with no other sign that one is gone, so a bare redirect reads as a no-op.
- Confirmation is a browser `confirm()` in an inline `onsubmit` on the row's form — no interstitial page, no new template, nothing added to `main.js`. Returning `false` from `onsubmit` is what makes Cancel a genuine no-op. With JavaScript off the form submits unconfirmed; that is accepted, not overlooked.
- The `.profile-tx-actions` cell **stays a `table-cell`** — never `display: flex`, never a wrapper `<div>` — so `text-align: right` and `width: 1%` keep working (both are table-layout behaviours a flex box discards). The delete `<form>` is `display: inline` and carries the gap; the `<button>` is reset with `font: inherit; border: none; background: none; padding: 0; vertical-align: baseline` so it measures exactly like the Edit anchor and the row height does not move. `white-space: nowrap` on `.profile-tx-table td` keeps the pair on one line. The class is on the `<th>` too, so pair-layout rules hang off the button and the form, not off it.
- CSRF defence is `SESSION_COOKIE_SAMESITE = "Lax"` plus the POST-only route — there is no token and no dependency available to add one, which is what makes POST-only load-bearing rather than stylistic. Do not relax `SameSite` without adding a token first.

**No stub routes remain.** Anything new is a feature, not a numbered step — give it its own spec under `.claude/specs/` before writing code.

---

## Warnings and things to avoid

- **Never return a bare string from a route** — render a template, redirect, or `abort()`
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- **`get_db()` returns a fresh connection and does not close it** — callers must `try/finally: conn.close()`. Note `with conn:` is a *transaction* context manager and leaves the connection open
- The DB file is `expense_tracker.db` at the project root, gitignored and recreated (and reseeded) on startup if deleted
