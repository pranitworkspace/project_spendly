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

**The templates already speak a contract the backend hasn't fulfilled:** `register.html` and `login.html` submit `POST` to their own routes and render `{{ error }}` if the view passes one (e.g. failing registration is expected to be `render_template("register.html", error="...")`, not a redirect). Posting to either currently 405s because those routes only accept `GET`.

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

Step 1 (`database/db.py`) is done. The remaining order is: register → login → session/logout, then expense CRUD. There is no expense-listing route yet at all.

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
