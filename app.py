import calendar
import math
import os
from datetime import date

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    CATEGORIES,
    create_expense,
    create_user,
    get_category_breakdown,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
# Signs the session cookie. Real deployments set SPENDLY_SECRET_KEY; the
# fallback exists so the teaching scaffold runs with no configuration.
app.config["SECRET_KEY"] = os.environ.get(
    "SPENDLY_SECRET_KEY", "dev-only-secret-change-in-production"
)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# A precomputed hash with no matching account, spent on every login attempt
# for an unknown email so that path costs the same as a wrong-password check
# against a real user — otherwise the missing check_password_hash() call is a
# timing oracle that lets an attacker enumerate registered emails.
_DUMMY_HASH = generate_password_hash("dummy-password-for-constant-time-login")


# ------------------------------------------------------------------ #
# Startup — ensure the database exists and has demo data              #
# ------------------------------------------------------------------ #

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # A signed-in user has nothing to do on the registration form.
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        # The password is hashed exactly as typed, but it is *judged* on its
        # stripped value — otherwise " 1234567 " would buy a 7-character
        # password past the length check.
        password = request.form.get("password", "")

        if not name or not email or not password.strip():
            return render_template("register.html", error="All fields are required.")

        if len(password.strip()) < 8:
            return render_template(
                "register.html", error="Password must be at least 8 characters."
            )

        if get_user_by_email(email) is not None:
            return render_template(
                "register.html", error="An account with that email already exists."
            )

        if create_user(name, email, password) is None:
            # Lost a race with a concurrent signup for the same email.
            return render_template(
                "register.html", error="An account with that email already exists."
            )

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Already signed in — /login has nothing to offer, so send them to their
    # profile rather than showing a sign-in form to someone already signed in.
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        # Verified exactly as typed — stripping here would lock out any
        # account whose password was registered with padding.
        password = request.form.get("password", "")

        if not email or not password.strip():
            return render_template(
                "login.html", error="All fields are required.", email=email
            )

        user = get_user_by_email(email)

        # One message for both failures. A distinct "no such account" would
        # tell an attacker which emails are registered. check_password_hash
        # is evaluated first (left operand of `or`) so an unknown email
        # always pays the same hashing cost as a wrong password — otherwise
        # the short-circuit on `user is None` is a timing oracle.
        pwhash = user["password_hash"] if user is not None else _DUMMY_HASH
        if not check_password_hash(pwhash, password) or user is None:
            return render_template(
                "login.html", error="Incorrect email or password.", email=email
            )

        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        # Post-login home. Step 3 parked this on the landing page because no
        # signed-in page existed yet; Step 4's /profile is now that page.
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    # clear(), not pop("user_id") — a partial clear leaves user_name behind
    # and the navbar keeps rendering a signed-in state.
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))


# ------------------------------------------------------------------ #
# Profile                                                            #
# ------------------------------------------------------------------ #

# Profile view-model helpers. The template renders pre-formatted strings and
# plain dicts (Jinja's `row.attr` does not work on a sqlite3.Row), so the view
# shapes raw DB rows into exactly what profile.html expects. Presentation only —
# no database access lives here.

def _rupees(value):
    """Format a number as Spendly currency: 6848.75 -> '₹6,848.75'."""
    return "₹" + f"{value:,.2f}"


def _initials(name):
    """First letter of each of the first two name words, uppercased.

    'Demo User' -> 'DU'. Falls back to '?' for an empty name so the avatar is
    never blank.
    """
    letters = [word[0] for word in name.split()[:2]]
    return "".join(letters).upper() or "?"


def _month_year(created_at):
    """A users.created_at ('2026-09-01 12:34:56') -> 'September 2026'.

    Only the date half is needed; slicing keeps this independent of whether the
    stored stamp carries a time component.
    """
    return date.fromisoformat(created_at[:10]).strftime("%B %Y")


def _tx_date(iso_date):
    """An expenses.date ('2026-09-02') -> '2 Sep 2026' — no leading-zero day."""
    d = date.fromisoformat(iso_date)
    return f"{d.day} {d:%b %Y}"


def _user_card(user_row):
    """Shape a users row into the template's `user` dict."""
    return {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": _initials(user_row["name"]),
        "member_since": _month_year(user_row["created_at"]),
    }


def _build_transactions(expense_rows):  # SUBAGENT 1 — transaction history
    """Shape recent-expenses rows into the template's `transactions` list."""
    return [
        {
            "date": _tx_date(row["date"]),
            "description": row["description"] or "",
            "category": row["category"],
            "amount": _rupees(row["amount"]),
        }
        for row in expense_rows
    ]


def _build_stats(summary, category_rows):  # SUBAGENT 2 — summary stats
    """Shape the expense summary and category rows into the template's `stats` list."""
    return [
        {"label": "Total spent", "value": _rupees(summary["total"])},
        {"label": "Transactions", "value": str(summary["tx_count"])},
        {
            "label": "Top category",
            "value": category_rows[0]["category"] if category_rows else "—",
        },
    ]


def _build_breakdown(category_rows):  # SUBAGENT 3 — category breakdown
    """Shape category-total rows into the template's `breakdown` list, `pct` scaled to the top category."""
    if not category_rows:
        return []
    max_total = category_rows[0]["total"]
    return [
        {
            "category": row["category"],
            "amount": _rupees(row["total"]),
            "pct": round(row["total"] / max_total * 100),
        }
        for row in category_rows
    ]


# Date-filter helpers for /profile (Step 6). Controller logic — they read the
# query string and do calendar arithmetic, no DB access and no currency/date
# string formatting (that stays with the builders above).

def _parse_iso_date(value):
    """`value` as a `date` if it is a well-formed ISO YYYY-MM-DD string, else
    None. Covers the missing (`""`), malformed (`"not-a-date"`) and None cases
    in one place so the view never has to.
    """
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _month_last_day(year, month):
    """The last calendar day (28-31) of `year`-`month`."""
    return calendar.monthrange(year, month)[1]


def _months_before(anchor, months):
    """The date `months` calendar months before `anchor`, day-clamped.

    Zero-based month-index arithmetic (`year*12 + (month - 1)`) plus `divmod`
    handles the year rollover, including a negative index (Jan minus 3 months
    -> Oct last year): `divmod` yields a 0-11 remainder that `+ 1` turns back
    into a 1-12 month. The day is clamped to the target month's length so
    31 May minus 3 months is 28/29 Feb, never an invalid date.
    """
    index = anchor.year * 12 + (anchor.month - 1) - months
    year, month_zero = divmod(index, 12)
    month = month_zero + 1
    day = min(anchor.day, _month_last_day(year, month))
    return date(year, month, day)


def _preset_ranges(today):
    """The filter bar's four quick-select ranges, in display order.

    Each entry is a dict of `key`, `label`, and ISO `date_from`/`date_to`
    strings — both None for "All Time", which renders as a bare `/profile` link.
    """
    first = today.replace(day=1)
    last = today.replace(day=_month_last_day(today.year, today.month))
    return [
        {
            "key": "this_month",
            "label": "This Month",
            "date_from": first.isoformat(),
            "date_to": last.isoformat(),
        },
        {
            "key": "last_3_months",
            "label": "Last 3 Months",
            "date_from": _months_before(today, 3).isoformat(),
            "date_to": today.isoformat(),
        },
        {
            "key": "last_6_months",
            "label": "Last 6 Months",
            "date_from": _months_before(today, 6).isoformat(),
            "date_to": today.isoformat(),
        },
        {
            "key": "all_time",
            "label": "All Time",
            "date_from": None,
            "date_to": None,
        },
    ]


def _active_preset(date_from, date_to, presets):
    """Which filter-bar entry the current (`date_from`, `date_to`) ISO strings
    select. An exact match on both bounds returns that preset's key — including
    "all_time" when both are None. A live filter that matches no preset is
    "custom".
    """
    for preset in presets:
        if preset["date_from"] == date_from and preset["date_to"] == date_to:
            return preset["key"]
    return "custom"


@app.route("/profile")
def profile():
    # Inline guard, matching the /register and /login style already in this
    # file (not a decorator).
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_row = get_user_by_id(session["user_id"])
    if user_row is None:
        # Session points at a deleted account — treat as signed out.
        session.clear()
        return redirect(url_for("login"))

    uid = user_row["id"]

    # Step 6 date filter — two optional query params, applied only when both
    # are present and valid. Anything else (missing, malformed, one-sided)
    # falls back to the full unfiltered page; an inverted range also flashes.
    date_from = _parse_iso_date(request.args.get("date_from", ""))
    date_to = _parse_iso_date(request.args.get("date_to", ""))
    if date_from is None or date_to is None:
        date_from = date_to = None
    elif date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = date_to = None

    # Back to ISO text: the `date_from > date_to` check above wants real dates,
    # but the DB layer and the template both take ISO strings (or None).
    from_str = date_from.isoformat() if date_from else None
    to_str = date_to.isoformat() if date_to else None

    summary = get_expense_summary(uid, date_from=from_str, date_to=to_str)
    category_rows = get_category_breakdown(uid, date_from=from_str, date_to=to_str)
    expense_rows = get_recent_expenses(
        uid, limit=10, date_from=from_str, date_to=to_str
    )

    presets = _preset_ranges(date.today())
    date_filter = {
        "date_from": from_str or "",
        "date_to": to_str or "",
        "active": _active_preset(from_str, to_str, presets),
        "presets": presets,
    }

    return render_template(
        "profile.html",
        user=_user_card(user_row),
        stats=_build_stats(summary, category_rows),
        transactions=_build_transactions(expense_rows),
        breakdown=_build_breakdown(category_rows),
        date_filter=date_filter,
    )


@app.route("/analytics")
def analytics():
    # Signed-in-only placeholder page. Same inline guard as /profile — a
    # logged-out visitor is bounced to /login, not shown the page.
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template("analytics.html")


# ------------------------------------------------------------------ #
# Add expense (Step 7)                                                #
# ------------------------------------------------------------------ #

# Controller helper for the add-expense form. Validates the submitted fields and
# hands the view exactly what it needs: the stripped values to echo into a
# re-render, the parsed amount, and the first error (or None). No DB access, no
# rendering — same split as _parse_iso_date and the /profile builders above.

def _clean_expense_form(form):
    """Validate the add-expense form.

    Returns ``(fields, amount, error)``:
      * ``fields`` — the four stripped raw strings, echoed back into a bounced
        form (keys: ``amount``, ``category``, ``expense_date``, ``description``)
      * ``amount`` — the parsed float, or None when validation failed
      * ``error``  — the first failure message, or None when the form is valid
    """
    fields = {
        "amount": form.get("amount", "").strip(),
        "category": form.get("category", "").strip(),
        "expense_date": form.get("date", "").strip(),
        "description": form.get("description", "").strip(),
    }

    if not fields["amount"]:
        return fields, None, "Amount is required."
    try:
        amount = float(fields["amount"])
    except ValueError:
        return fields, None, "Amount must be a number."
    # float() also parses "nan"/"inf"/"1e999"; nan <= 0 and inf <= 0 are both
    # False, so a non-finite amount would slip past the check below and then
    # either break the NOT NULL insert or poison every SUM(amount) on /profile.
    if not math.isfinite(amount) or amount <= 0:
        return fields, None, "Amount must be greater than 0."
    if fields["category"] not in CATEGORIES:
        return fields, None, "Choose a valid category."
    if _parse_iso_date(fields["expense_date"]) is None:
        return fields, None, "Enter a valid date."
    if len(fields["description"]) > 200:
        return fields, None, "Description must be 200 characters or fewer."

    return fields, amount, None


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    # Inline guard, matching /profile and /analytics (not a decorator).
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if get_user_by_id(session["user_id"]) is None:
        # Session points at a deleted account — treat as signed out.
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        fields, amount, error = _clean_expense_form(request.form)
        if error:
            return render_template(
                "add_expense.html", categories=CATEGORIES, **fields, error=error
            )

        create_expense(
            session["user_id"],
            amount,
            fields["category"],
            fields["expense_date"],
            fields["description"] or None,
        )
        return redirect(url_for("profile"))

    # GET — an empty form; same key shape the re-render path uses.
    fields = {
        "amount": "",
        "category": "",
        "expense_date": date.today().isoformat(),
        "description": "",
    }
    return render_template("add_expense.html", categories=CATEGORIES, **fields)


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
