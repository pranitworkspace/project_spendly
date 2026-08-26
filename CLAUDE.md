# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Spendly is a lightweight personal expense tracker built with Flask and SQLite. This is a **teaching scaffold** (CampusX course): the entire frontend (templates, CSS) is complete and polished, while the backend is a set of numbered exercises left for students to implement.

---

## Architecture

```
spendly/
├── app.py              # All routes — single file, no blueprints
├── database/
│   ├── __init__.py
│   └── db.py            # SQLite helpers: get_db(), init_db(), seed_db() — currently just comments
├── templates/
│   ├── base.html         # Shared layout — all templates must extend this
│   └── *.html            # One template per page (landing, login, register, terms, privacy)
├── static/
│   ├── css/style.css     # Single global stylesheet, banner-commented sections
│   └── js/main.js        # Vanilla JS only — currently a placeholder
└── requirements.txt
```

**Where things belong:**
- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` only, never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → add a section to `style.css` (there is currently no per-page CSS file split), not inline `<style>` tags

**`app.py`** is split into two clearly marked sections: working GET routes (`/`, `/register`, `/login`, `/terms`, `/privacy`) that `render_template(...)`, and placeholder routes that return a literal string like `"Add expense — coming in Step 7"`.

**Templates use Jinja2 inheritance.** Every page extends `base.html`, which defines the shell (navbar, `<main>`, footer, script tag) and four blocks: `title`, `head`, `content`, `scripts`. Links and static assets are built with `url_for()` (e.g. `url_for('login')`, `url_for('static', filename='css/style.css')`) — never hardcoded paths.

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
# Setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run dev server (port 5001, not the Flask default 5000 — don't change this)
python app.py

# Tests (pytest + pytest-flask installed, no test files exist yet)
pytest
pytest path/to/test_file.py::test_name   # a single test, once tests exist
pytest -k "test_name"
pytest -s                                # with output visible
```

No linter/formatter is configured in this repo.

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET /register` | Implemented (GET only) — renders `register.html` |
| `GET /login` | Implemented (GET only) — renders `login.html` |
| `GET /terms` | Implemented — renders `terms.html` |
| `GET /privacy` | Implemented — renders `privacy.html` |
| `GET /logout` | Stub — Step 3 |
| `GET /profile` | Stub — Step 4 |
| `GET /expenses/add` | Stub — Step 7 |
| `GET /expenses/<id>/edit` | Stub — Step 8 |
| `GET /expenses/<id>/delete` | Stub — Step 9 |

There is no expense-listing route yet at all. Because routes depend on `get_db()`, the natural build order is: `database/db.py` first, then register → login → session/logout, then expense CRUD.

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for a stub route** once its step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **`database/db.py` is currently just comments** — do not assume `get_db()`/`init_db()`/`seed_db()` exist until the step that implements them
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- The DB file will be `expense_tracker.db` (already gitignored, not yet created by any code)
