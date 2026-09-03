# spendly-test-writer — institutional memory

## Fixtures / harness
- Root `conftest.py`: autouse `temp_db` monkeypatches `database.db.DB_PATH` to a
  tmp_path file. No schema is created by it.
- `tests/conftest.py`: `client` fixture depends on `temp_db`, imports `app`,
  calls `db.init_db()` + `db.seed_db()`, sets `TESTING=True`, yields
  `app.test_client()`. Use this fixture for everything, including DB-helper tests
  (it is the only thing that builds the schema + demo data).
- No `app` / `auth_client` fixtures exist. Sign in manually.

## Auth
- Login: `client.post("/login", data={"email": ..., "password": ...})`.
- Seeded demo user: `demo@spendly.com` / `demo123` (name "Demo User").
- Register: `client.post("/register", data={"name","email","password"})`,
  password min 8 chars. Register does NOT auto-login; POST /login after.
- Helpers copied from `tests/test_profile_transactions.py`: `_sign_in`,
  `_register_and_sign_in` (returns new user id via `db.get_user_by_email`).
- Protected routes use an inline guard (no decorator) → 302 to `/login` when
  `session["user_id"]` absent, and also `session.clear()` + 302 when the id
  matches no user row. Protected: `/profile`, `/analytics`, `/expenses/add`
  (GET+POST). `/expenses/<id>/edit` and `/delete` are still raw-string stubs
  (Steps 8/9) — do not test yet.

## Conventions that hold across the suite
- Tests use string-literal URLs ("/login", "/profile", ...) — matches existing
  files; `url_for` not used in test scope.
- Raw SQL in test helpers uses `?` placeholders, `db.get_db()` with
  `try/finally: conn.close()`.
- Assertions are on `response.data` bytes; redirects checked via
  `response.status_code == 302` and substring of `response.headers["Location"]`
  (may be absolute or relative depending on Werkzeug — use `in`, not `==`).
- Currency renders as `"₹" + f"{v:,.2f}"` (e.g. `"₹450.00".encode()`).
- Transaction dates on /profile: `"2 Sep 2026"` (no leading-zero day).
- /profile transaction rows carry `class="profile-badge"` (count them for row
  counts); seed has 8 expenses, table caps at 10 (`get_recent_expenses` LIMIT).

## Data layer (`database/db.py`)
- Spec text says `database/queries.py` / `insert_expense` — THAT FILE DOES NOT
  EXIST. Real helper: `create_expense(user_id, amount, category, expense_date,
  description=None)` → returns new row id (`lastrowid`), rounds amount to 2 dp,
  stores `description=None` as SQL NULL. Param is `expense_date` not `date`.
- `CATEGORIES` tuple in `database/db.py`: Food, Transport, Bills, Health,
  Entertainment, Shopping, Other (7). Tests hardcode this list as the contract.
- Read helpers: `get_user_by_email`, `get_user_by_id` (no password_hash),
  `get_recent_expenses`, `get_expense_summary`, `get_category_breakdown`
  (last three take optional `date_from`/`date_to` ISO strings, all-or-nothing).

## Test files → coverage
- `tests/test_profile_transactions.py` — /profile transaction-history section.
- `tests/test_07-add-expense.py` — Step 7 Add Expense: `create_expense` persist
  + NULL description; GET/POST `/expenses/add` auth guard; GET form has POST
  method, category `<select>` w/ all 7, amount/category/date/description fields;
  POST valid → 302 /profile + 1 row; validation (missing/zero/non-numeric
  amount, bad category, bad date) → 200 + `b"error"` + no row; value
  preservation on bounce; blank/omitted description → NULL; navbar + profile
  link to `/expenses/add`. Filename intentionally hyphenated (still matches
  `test_*.py` collection; not importable as a module).

## Notes / gotchas
- Add-expense form re-render error assertion: `b"error" in response.data.lower()`
  — spec-level ("contains an error message"), tolerant of flash-error class or a
  templated `{{ error }}`. Revisit if implementation uses different wording.
- `_parse_iso_date` in app.py rejects "not-a-date" (ValueError→None). Use that
  string for invalid-date cases; "2026-02-30" also raises on py3.11+.
