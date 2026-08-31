# Spec: Login and Logout

## Overview
Spendly can create accounts but cannot let anyone back into one. `/login` currently renders its form and accepts `GET` only, so submitting it returns a 405; `/logout` is still the raw placeholder string `"Logout — coming in Step 3"`. This step closes the auth loop: it gives the app a `SECRET_KEY` (nothing in the codebase has one yet, so `session[...]` and `flash()` both raise at request time today), verifies a submitted password against the stored hash with `check_password_hash`, writes the signed-in user into `session`, and clears that session on logout. It also makes the app *look* signed in — the navbar in `base.html` currently always shows "Sign in / Get started" with no conditional — and adds the flash-message surface that every later step will reuse. This is the last piece of the auth foundation: expense CRUD (Steps 7–9) has no meaning until a request can say who it belongs to.

---

## Depends on
- **Step 1 — Database setup.** `get_db()`, `init_db()`, `seed_db()`, and the `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) must exist. Login reads the seeded demo account `demo@spendly.com` / `demo123`.
- **Step 2 — Registration.** `get_user_by_email()` and `create_user()` exist, and the email-normalisation convention (stored and looked up **stripped and lowercased**) is already established. Login must follow the same convention or accounts created in Step 2 will be unreachable.

---

## Routes

- `GET /login` — render the sign-in form. **Public.** *(already exists — unchanged)*
- `POST /login` — validate credentials, start the session, redirect on success; re-render `login.html` with `error` on failure. **Public.** *(new — the route currently accepts `GET` only)*
- `GET /logout` — clear the session and redirect to the landing page. **Logged-in** (harmless if called while signed out — it clears an already-empty session). *(replaces the placeholder string)*

No other routes change. `/profile` keeps `"Profile page — coming in Step 4"` and the expense routes keep their Step 7–9 placeholders.

**Where a successful login lands:** there is no dashboard or expense-listing route in the app yet, so login redirects to `url_for("landing")`. The navbar will render the signed-in state there. When Step 4+ introduces a real post-login page, this redirect target moves.

---

## Database changes
No database changes. The `users` table already stores `password_hash` (written by `create_user()` via `generate_password_hash`), and `get_user_by_email()` already does the parameterised lookup login needs.

One addition to `database/db.py` is **out of scope**: there is no `get_user_by_id()` in the repo. This step avoids needing one by storing both `user_id` and `user_name` in the session at login, so the navbar can greet the user without a per-request query. If a later step needs a fresh user row from `session["user_id"]`, it adds `get_user_by_id()` then.

---

## Templates

**Create:** none.

**Modify:**
- `templates/login.html` — change `<form method="POST" action="/login">` to `action="{{ url_for('login') }}"`. The hardcoded path violates the `url_for()` rule in CLAUDE.md and is the same fix Step 2 applied to `register.html`. Also add `value="{{ email or '' }}"` to the email input so a failed attempt does not wipe what was typed. The existing `{% if error %}<div class="auth-error">{{ error }}</div>{% endif %}` block and all `name` attributes (`email`, `password`) stay exactly as they are.
- `templates/base.html` — two additions:
  1. **Conditional nav.** `.nav-links` currently hardcodes "Sign in" and "Get started". Wrap them so a signed-out visitor sees those two links, and a signed-in user sees their name plus a "Sign out" link to `url_for('logout')` instead.
  2. **Flash block.** Add a `get_flashed_messages(with_categories=true)` loop above `{% block content %}` so `flash()` calls render. Nothing in any template renders flashes today.

---

## Files to change
- `app.py` — import `session`, `flash`, and `os`; set `app.config["SECRET_KEY"]`; add `POST` to the `/login` route and implement the credential check; implement `logout()`.
- `database/db.py` — import `check_password_hash` alongside `generate_password_hash` **only if** the hash comparison lives here. Preferred: leave `db.py` untouched and call `check_password_hash` in the view, matching Step 2, where `generate_password_hash` lives in `create_user()` but all validation lives in `register()`. *(Decide once; do not do both.)*
- `templates/login.html` — `url_for()` form action, sticky email value.
- `templates/base.html` — conditional nav links, flash-message block.
- `static/css/style.css` — new section for `.flash` / `.flash-success` / `.flash-error` and for the signed-in nav (`.nav-user`). Reuse the existing tokens; do not add hex literals.
- `CLAUDE.md` — mark Step 3 done in **Build order**, remove the "there is still no `SECRET_KEY`" warning, and record the session conventions this step establishes.

## Files to create
- `.claude/specs/03-login-and-logout.md` — this spec.

No new Python modules, no new templates, no new CSS file (page styles go in a new section of `style.css`, per CLAUDE.md).

---

## New dependencies
No new dependencies. `session` and `flash` are Flask core, `check_password_hash` ships in the already-pinned `werkzeug==3.1.6`, and `os` is stdlib. `requirements.txt` is unchanged.

---

## Rules for implementation

**Mandatory project rules**
- No SQLAlchemy or ORMs — raw `sqlite3` through `database/db.py` only.
- Parameterised queries only (`?` placeholders) — never f-strings in SQL.
- Passwords hashed and verified with **werkzeug** (`generate_password_hash` / `check_password_hash`) — never a hand-rolled or plaintext comparison.
- Use CSS variables from `:root` — never hardcode hex values in new CSS.
- All templates extend `base.html`.

**Step-3 specific**
- **Normalise the email, not the password.** Read the email as `request.form.get("email", "").strip().lower()` before calling `get_user_by_email()` — SQLite compares TEXT case-sensitively, so this is the only thing keeping `A@b.com` and `a@b.com` one account. Read the password as `request.form.get("password", "")` and pass it to `check_password_hash` **exactly as typed**. Judge emptiness on `password.strip()`, but never strip the value you verify, or accounts registered with padded passwords can never sign in.
- **Use `request.form.get(key, "")`, never `request.form[key]`** — the subscript form raises a 400 page instead of re-rendering the form with an error.
- **A failed login re-renders, it does not redirect.** `return render_template("login.html", error="...")` with a `200`. Only success redirects. This is the contract `login.html` already speaks.
- **One generic failure message for both cases.** An unknown email and a wrong password must both produce `"Incorrect email or password."` — a distinct "no such account" message tells an attacker which emails are registered. Empty fields get `"All fields are required."`.
- **Check the user exists before checking the hash.** `get_user_by_email()` returns `None` for an unknown email; passing `None["password_hash"]` to `check_password_hash` is a `TypeError`, not a failed login.
- **`SECRET_KEY` comes from the environment with a dev fallback:** `app.config["SECRET_KEY"] = os.environ.get("SPENDLY_SECRET_KEY", "<dev fallback>")`. Do not commit a real production secret. Set it once, near `app = Flask(__name__)`, before any route.
- **Session contents are fixed here:** `session["user_id"]` (int, from the row's `id`) and `session["user_name"]` (str). Nothing else. Later steps read `session["user_id"]` to scope expenses — do not store the email or the hash.
- **Logout clears everything.** `session.clear()`, not `session.pop("user_id")` — a partial clear leaves `user_name` behind and the navbar renders a signed-in state for a signed-out visitor. Then `flash(...)` and `redirect(url_for("landing"))`.
- **No raw string returns.** `/logout` must stop returning `"Logout — coming in Step 3"`; it redirects.
- **Do not touch the other stub routes.** `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete` keep their placeholder strings — those are Steps 4 and 7–9.
- **Do not add a `@login_required` decorator or protect any route yet.** Nothing worth protecting exists; route guarding belongs with the first real logged-in page.
- **Do not log the user in from `/register`.** Step 2 deliberately redirects to `/login`; leave that behaviour alone.
- Keep DB access in `database/db.py` — the view calls `get_user_by_email()`, it does not open a connection.

---

## Definition of done

Verified by running `venv/bin/python app.py` and using the app at `http://127.0.0.1:5001`:

- [ ] `venv/bin/pytest` passes — all 18 existing `tests/test_db.py` tests still green.
- [ ] `POST /login` no longer returns 405; the sign-in form submits.
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects to the landing page and the navbar shows the user's name and a "Sign out" link instead of "Sign in / Get started".
- [ ] `DEMO@Spendly.com` (mixed case) with the correct password signs in successfully — email normalisation works.
- [ ] `  demo@spendly.com  ` (padded with spaces) signs in successfully.
- [ ] A wrong password renders `login.html` with `"Incorrect email or password."` in the `.auth-error` box, stays on `/login` with a `200`, and does **not** redirect.
- [ ] An email with no account produces the **same** `"Incorrect email or password."` message — the two failures are indistinguishable.
- [ ] Submitting an empty form produces `"All fields are required."` and no 400 page.
- [ ] After a failed attempt the email field still contains what was typed; the password field is empty.
- [ ] Registering a new account at `/register`, then signing in with those exact credentials, works end to end — including a password with leading/trailing spaces.
- [ ] Visiting `/logout` while signed in clears the session, shows a flash message, and returns the navbar to "Sign in / Get started".
- [ ] Visiting `/logout` while signed out does not error.
- [ ] After logout, the browser back button does not restore a signed-in navbar on a fresh request (the server renders signed-out).
- [ ] `/logout` returns no raw string anywhere — it redirects.
- [ ] `/profile` still returns `"Profile page — coming in Step 4"` and the three expense routes still return their Step 7–9 placeholders.
- [ ] `grep -n 'action="/' templates/*.html` returns nothing — every form action goes through `url_for()`.
- [ ] No new hex literals in `static/css/style.css` outside `:root`.
- [ ] `requirements.txt` is unchanged.
- [ ] `CLAUDE.md` **Build order** marks Step 3 complete and no longer claims there is no `SECRET_KEY`.
