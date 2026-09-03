# Spec: Edit Expense

## Overview
Step 8 lets a logged-in user edit any of their own expenses via a pre-populated
form at `/expenses/<id>/edit`. The GET handler loads the existing expense from
the database and renders the form with its current values; the POST handler
validates the submission and updates the row in place. Ownership is enforced:
a user can only edit expenses that belong to them. Ownership is enforced in SQL, not in the view: both new helpers scope on
`WHERE id = ? AND user_id = ?`, so a foreign or missing id is a 404 either way.
Two new helpers are added to `database/db.py`: `get_expense_by_id` and
`update_expense`. The transactions table in `profile.html` gains an "Edit"
action link per row, which requires `_build_transactions()` in `app.py` to carry
the expense `id` through to the template (`get_recent_expenses()` already
selects it).

## Depends on
- Step 1: Database setup (`expenses` table exists with all required columns)
- Step 3: Login / Logout (`session["user_id"]` is set and enforced)
- Step 5: Profile page renders transactions (the edit link lives there)
- Step 7: Add Expense (establishes the form pattern this step follows)

## Routes
- `GET /expenses/<int:id>/edit` — render edit form pre-populated with existing
  expense values — logged-in only
- `POST /expenses/<int:id>/edit` — validate and save updated expense — logged-in only

## Database changes
No new tables or columns. All required columns already exist in `expenses`:
`id`, `user_id`, `amount`, `category`, `date`, `description`.

## Templates
- **Create**: `templates/edit_expense.html`
  - Extends `base.html`
  - Form with `method="POST"` and
    `action="{{ url_for('edit_expense', id=expense_id) }}"` — never a hardcoded path
  - Same fields as `add_expense.html`:
    - `amount` — number input, `step="0.01"`, `min="0.01"`, required, pre-filled
    - `category` — `<select>` with the 7 fixed options, pre-selected to current value
    - `date` — `<input type="date">`, required, pre-filled to current value
    - `description` — text input, optional, max 200 chars, pre-filled
  - Submit button ("Save Changes") and a cancel link back to `/profile`
  - Display error message when validation fails, re-populating submitted values

- **Modify**: `templates/profile.html`
  - Add an "Actions" column header to the transactions table `<thead>`
  - Add an "Edit" link cell per transaction row:
    `<a href="{{ url_for('edit_expense', id=tx.id) }}">Edit</a>`

## Files to change
- `database/db.py` (the project's only data-access module — there is no
  `database/queries.py`)
  - Add `get_expense_by_id(expense_id, user_id)` — fetches a single expense
    row only if it belongs to the given user; returns `None` otherwise
  - Add `update_expense(expense_id, user_id, amount, category, expense_date, description)`
    — a parameterised `UPDATE` scoped to both `id` and `user_id` for ownership
    safety; returns `True` when a row changed. The parameter is `expense_date`,
    not `date`, because the module does `from datetime import date` at import
    time — same convention as `create_expense()`
  - `get_recent_expenses()` needs **no change** — it already selects `id`
- `app.py`
  - Import `abort` from `flask`, and `get_expense_by_id` / `update_expense`
    from `database.db`
  - Add `"id": row["id"]` to the dicts `_build_transactions()` builds, so the
    profile template can construct the edit link
  - Replace the GET-only placeholder at `/expenses/<int:id>/edit` with a
    full GET + POST handler:
    - GET: call `get_expense_by_id`; `abort(404)` if not found or not owned;
      render `edit_expense.html` with `categories`, `expense_id`, and the flat
      `amount` / `category` / `expense_date` / `description` values
    - POST: validate with the existing `_clean_expense_form()`, call
      `update_expense`, flash and redirect to `/profile` on success; re-render
      the form with the error and the submitted values otherwise
  - Change the route decorator to accept both methods:
    `@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])`

- `templates/profile.html`
  - Add `<th class="profile-tx-actions">Actions</th>` to the table header
  - Add an actions cell per row linking via `url_for('edit_expense', id=tx.id)`
- `static/css/style.css` — add a `.profile-tx-actions` rule (the class does not
  exist yet); CSS variables only, no hex literals
- `CLAUDE.md` — record Steps 6-8 as done and add a "Convention Step 8
  established" block

## Files to create
- `templates/edit_expense.html` — the edit-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in `get_db()`)
- `get_expense_by_id` must scope its query to `id = ? AND user_id = ?` to prevent
  one user editing another user's expense — return `None` if not found
- `update_expense` must also include `user_id = ?` in its `WHERE` clause as a
  second ownership guard
- Unauthenticated access to both GET and POST must redirect to `/login`
- If the expense does not exist or belongs to another user, return a 404
- **Reuse `_clean_expense_form()` from Step 7 verbatim** — do not fork a second
  copy of these rules. It already enforces all of them:
  - `amount`: required, must be a positive number > 0 (parse with `float()`; catch `ValueError`)
  - `category`: required, must be one of the 7 fixed categories
  - `date`: required, must be a valid `YYYY-MM-DD` string (via the existing
    `_parse_iso_date()` helper, not a fresh `datetime.strptime` call)
  - `description`: optional; strip whitespace; store `None` if blank
  - On any validation error, re-render the form with the error message and the
    submitted (not original) values pre-filled
- After a successful update, `flash("Expense updated.", "success")` then
  redirect to `url_for("profile")` — do NOT render the form again. The flash
  matters here in a way it did not for Step 7: `/profile` lists only the 10 most
  recent rows, so an edited expense can move or drop out of view and a silent
  redirect would look like nothing happened
- Never hardcode a URL in a template — `url_for()` for every internal link
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $

## Tests to write
File: `tests/test_edit_expense.py`

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `get_expense_by_id` | valid `expense_id`, correct `user_id` | returns the matching row as a dict-like object |
| `get_expense_by_id` | valid `expense_id`, wrong `user_id` | returns `None` |
| `get_expense_by_id` | non-existent `expense_id` | returns `None` |
| `update_expense` | valid `expense_id`, correct `user_id`, new `amount=99.0` | returns `True`; row in DB reflects updated amount |
| `update_expense` | valid `expense_id`, wrong `user_id` | returns `False`; row in DB unchanged, no error raised |
| `update_expense` | `amount=12.345` | stored as `12.35` — rounded in the data layer |

### Route tests
`GET /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302)

`GET /expenses/<id>/edit` — authenticated, own expense:
- Returns 200
- Response body contains form pre-filled with the expense's current values
- Response body contains `<select>` with the correct category pre-selected

`GET /expenses/<id>/edit` — authenticated, other user's expense:
- Returns 404

`GET /expenses/<id>/edit` — authenticated, non-existent id:
- Returns 404

`POST /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302)

`POST /expenses/<id>/edit` — authenticated, valid data:
- Redirects to `/profile` (302)
- Updated values are reflected in the database

`POST /expenses/<id>/edit` — authenticated, other user's expense:
- Returns 404

`POST /expenses/<id>/edit` — authenticated, missing amount:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, amount = 0:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, non-numeric amount:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, invalid category:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, invalid date string:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, no description:
- Redirects to `/profile` (302)
- Row updated with `description = NULL`

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for a non-existent or other user's expense returns 404
- [ ] Visiting `/expenses/<id>/edit` while logged in shows a form pre-filled with the expense's current values
- [ ] The category dropdown has the correct category pre-selected
- [ ] Submitting valid changes redirects to `/profile`, shows the "Expense updated." flash, and the updated values appear in the transaction list
- [ ] Submitting with a missing or zero amount re-renders the form with an error and the submitted values retained
- [ ] Submitting with an invalid category re-renders the form with an error
- [ ] Submitting with an invalid date re-renders the form with an error
- [ ] Submitting without a description saves the expense with no description (no error)
- [ ] Each row in the profile transaction table has an "Edit" link pointing to the correct URL
- [ ] Clearing the description saves NULL — the profile row shows an empty cell, not the word "None"
- [ ] `venv/bin/pytest` still passes the Step 1-7 suites