"""Spec-derived HTTP tests for Step 6 — date filter on the profile page.

These are written from `.claude/specs/06-date-filter-profile-page.md`, not from
the implementation. The spec says:

* `GET /profile` takes two optional query params, `date_from` / `date_to`
  (ISO `YYYY-MM-DD`, inclusive bounds). No new routes.
* The filter applies only when both params are present and well-formed;
  otherwise the page falls back to the full unfiltered ("All Time") view.
* An inverted range (`date_from > date_to`) additionally flashes
  "Start date must be before end date."
* A filter bar renders four quick-select presets — "This Month",
  "Last 3 Months", "Last 6 Months", "All Time" — plus a custom `method="get"`
  sub-form with two `<input type="date">` fields and an "Apply" button.
* The active preset (or custom range) is visually highlighted; the custom
  inputs re-populate from the active values.
* All three data sections — summary stats, recent transactions, category
  breakdown — respect the active filter.

The seeded demo user's eight expenses all land in the current calendar month
and drift with the clock, so only their count (8) and total (₹6,848.75) are
treated as fixed. Every assertion about *filtered* values uses a freshly
registered user with expenses at fixed absolute dates, or at month offsets
recomputed here with `_shift_months` (a copy of the spec's preset math).
"""

import calendar
import html
import re
from datetime import date

import pytest

import database.db as db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

SEED_EXPENSE_COUNT = 8
SEED_TOTAL = "₹6,848.75"  # ₹6,848.75


# ------------------------------------------------------------------ #
# Helpers — same conventions as the other tests/test_profile*.py     #
# ------------------------------------------------------------------ #

def _sign_in(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})


def _register_and_sign_in(client, name, email, password="password123"):
    client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )
    client.post("/login", data={"email": email, "password": password})
    return db.get_user_by_email(email)["id"]


def _add_expense(user_id, amount, category, iso_date, description):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, iso_date, description),
        )
        conn.commit()
    finally:
        conn.close()


def _shift_months(anchor, months):
    """`anchor` moved `months` calendar months earlier, day-clamped.

    Mirrors the spec's "N-month window ending today" math so preset windows can
    be recomputed in-test without importing app internals.
    """
    index = anchor.year * 12 + (anchor.month - 1) - months
    year, month_zero = divmod(index, 12)
    month = month_zero + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _this_month_bounds(today=None):
    today = today or date.today()
    first = today.replace(day=1)
    last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    return first.isoformat(), last.isoformat()


def _preset_href(body, label):
    """The (HTML-unescaped) URL the preset anchor labelled `label` points at."""
    match = re.search(
        r'<a href="([^"]+)"\s+class="profile-filter-preset[^"]*">\s*' + re.escape(label),
        body,
    )
    assert match, f"no preset anchor found for {label!r}"
    return html.unescape(match.group(1))


def _anchor_tag(body, label):
    """The opening `<a ...>` tag immediately preceding the text `label`."""
    end = body.index(label)
    start = body.rindex("<a ", 0, end)
    return body[start:body.index(">", start) + 1]


# ------------------------------------------------------------------ #
# The unfiltered page is unchanged from Step 5                        #
# ------------------------------------------------------------------ #

def test_unfiltered_profile_matches_step5(client):
    """No query params -> same data as Step 5 (all expenses, unfiltered)."""
    _sign_in(client)

    response = client.get("/profile")
    body = response.data.decode()

    assert response.status_code == 200, "signed-in /profile should render"
    assert body.count('class="profile-badge"') == SEED_EXPENSE_COUNT, (
        "all eight seed transactions should be listed when unfiltered"
    )
    assert SEED_TOTAL in body, "unfiltered total should still be ₹6,848.75"
    assert "Start date must be before end date." not in body, (
        "no params must not trigger the range-order flash"
    )


# ------------------------------------------------------------------ #
# Filter bar markup                                                   #
# ------------------------------------------------------------------ #

def test_filter_bar_renders_above_stats_with_four_presets(client):
    """The filter bar renders the four named quick-select presets."""
    _sign_in(client)

    body = client.get("/profile").data.decode()

    assert 'class="profile-filter"' in body, "a filter bar section should exist"
    # Exact-quote match so the "profile-filter-presets" wrapper div is not counted.
    preset_anchors = (
        body.count('"profile-filter-preset"')
        + body.count('"profile-filter-preset is-active"')
    )
    assert preset_anchors == 4, (
        "exactly four quick-select preset links should render"
    )
    for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
        assert label in body, f"preset {label!r} should be present"
    # The bar sits above the summary stats row.
    assert body.index('class="profile-filter"') < body.index('class="profile-stats"'), (
        "the filter bar must appear above the summary stats"
    )


def test_custom_subform_is_a_get_to_profile_with_date_inputs_and_apply(client):
    """Custom range sub-form: GET to url_for('profile'), two date inputs, Apply."""
    _sign_in(client)

    body = client.get("/profile").data.decode()
    start = body.index("profile-filter-custom")
    form = body[start:body.index("</form>", start)]

    assert 'method="get"' in form, "the custom range form must submit with GET"
    assert 'action="/profile"' in form, "the form action must be url_for('profile')"
    assert form.count('type="date"') == 2, "two <input type=date> fields expected"
    assert 'name="date_from"' in form and 'name="date_to"' in form, (
        "the two inputs must be named date_from and date_to"
    )
    assert 'type="submit"' in form, "an Apply submit button is required"
    assert "Apply" in form, "the submit button should be labelled 'Apply'"


# ------------------------------------------------------------------ #
# Preset link URLs carry the right params                             #
# ------------------------------------------------------------------ #

def test_preset_links_carry_expected_date_params(client):
    """Each dated preset link carries the correct computed date_from/date_to."""
    _sign_in(client)
    today = date.today()
    first_iso, last_iso = _this_month_bounds(today)

    body = client.get("/profile").data.decode()

    assert f"date_from={first_iso}&amp;date_to={last_iso}" in body, (
        "'This Month' must span the whole current calendar month"
    )
    assert (
        f"date_from={_shift_months(today, 3).isoformat()}"
        f"&amp;date_to={today.isoformat()}" in body
    ), "'Last 3 Months' must be the 3-month window ending today"
    assert (
        f"date_from={_shift_months(today, 6).isoformat()}"
        f"&amp;date_to={today.isoformat()}" in body
    ), "'Last 6 Months' must be the 6-month window ending today"


def test_all_time_preset_links_to_bare_profile(client):
    """The 'All Time' preset passes no query params — a clean /profile URL."""
    _sign_in(client)

    body = client.get("/profile").data.decode()
    tag = _anchor_tag(body, "All Time")

    assert 'href="/profile"' in tag, "'All Time' must be a bare /profile link"
    assert "date_from" not in tag and "date_to" not in tag, (
        "'All Time' must not carry any date params"
    )
    assert "profile-filter-preset" in tag, "'All Time' is one of the preset buttons"


# ------------------------------------------------------------------ #
# A preset / custom range narrows every data section                  #
# ------------------------------------------------------------------ #

def test_this_month_preset_narrows_all_sections(client):
    """'This Month' filters stats, transactions and breakdown to this month."""
    uid = _register_and_sign_in(client, "Manny Month", "manny@example.com")
    today = date.today()
    _add_expense(uid, 100.00, "Food", today.isoformat(), "ThisMonthTx")
    _add_expense(uid, 999.00, "Shopping", _shift_months(today, 2).isoformat(), "OldTx")

    href = _preset_href(client.get("/profile").data.decode(), "This Month")
    body = client.get(href).data.decode()

    assert "ThisMonthTx" in body, "a row dated today must survive the This Month filter"
    assert "OldTx" not in body, "a row two months back must be filtered out"
    assert '<span class="profile-stat-value">1</span>' in body, (
        "the transaction count stat must reflect the filter"
    )
    assert body.count('class="profile-bar-row"') == 1, (
        "the category breakdown must reflect the filter"
    )
    assert "is-active" in _anchor_tag(body, "This Month"), (
        "the This Month preset should be highlighted while it is applied"
    )


@pytest.mark.parametrize(
    "label, in_offset, out_offset",
    [("Last 3 Months", 1, 5), ("Last 6 Months", 4, 9)],
)
def test_rolling_window_preset_narrows_page(client, label, in_offset, out_offset):
    """'Last 3/6 Months' keep only rows inside the N-month window ending today."""
    uid = _register_and_sign_in(client, "Wanda Window", "wanda@example.com")
    today = date.today()
    _add_expense(
        uid, 50.00, "Food", _shift_months(today, in_offset).isoformat(), "InWindowTx"
    )
    _add_expense(
        uid, 60.00, "Bills", _shift_months(today, out_offset).isoformat(), "OutOfWindowTx"
    )

    href = _preset_href(client.get("/profile").data.decode(), label)
    body = client.get(href).data.decode()

    assert "InWindowTx" in body, f"{label}: a row inside the window must be kept"
    assert "OutOfWindowTx" not in body, f"{label}: a row before the window must drop"


def test_all_time_preset_clears_an_active_filter(client):
    """'All Time' removes any active filter and shows every expense again."""
    uid = _register_and_sign_in(client, "Tina Time", "tina@example.com")
    _add_expense(uid, 10.00, "Food", "2019-01-01", "AncientTx")
    _add_expense(uid, 20.00, "Bills", "2025-06-15", "RecentTx")

    narrowed = client.get("/profile?date_from=2025-01-01&date_to=2025-12-31").data.decode()
    assert "AncientTx" not in narrowed, "the range should hide the 2019 row first"

    href = _preset_href(narrowed, "All Time")
    assert href == "/profile", "'All Time' must link to a param-free /profile"

    body = client.get(href).data.decode()
    assert "AncientTx" in body and "RecentTx" in body, (
        "following 'All Time' must restore the full unfiltered list"
    )


def test_custom_range_narrows_all_three_sections(client):
    """A valid custom range shows only in-range rows in all three sections."""
    uid = _register_and_sign_in(client, "Cara Custom", "cara@example.com")
    _add_expense(uid, 111.00, "Food", "2020-01-10", "TooEarly")
    _add_expense(uid, 222.00, "Transport", "2020-06-15", "InWindow")
    _add_expense(uid, 333.00, "Shopping", "2020-12-20", "TooLate")

    response = client.get("/profile?date_from=2020-05-01&date_to=2020-09-01")
    body = response.data.decode()

    assert response.status_code == 200
    # Transactions section
    assert "InWindow" in body, "the in-range transaction must be listed"
    assert "TooEarly" not in body and "TooLate" not in body, (
        "out-of-range transactions must be hidden"
    )
    # Summary stats section
    assert '<span class="profile-stat-value">1</span>' in body, "count stat -> 1"
    assert '<span class="profile-stat-value">₹222.00</span>' in body, (
        "total-spent stat -> ₹222.00"
    )
    assert '<span class="profile-stat-value">Transport</span>' in body, (
        "top-category stat -> Transport"
    )
    # Category breakdown section
    assert body.count('class="profile-bar-row"') == 1, "one breakdown bar only"
    assert "₹222.00" in body, "the breakdown amount stays rupee-formatted"


# ------------------------------------------------------------------ #
# Active-state highlighting and input re-population                   #
# ------------------------------------------------------------------ #

def test_active_preset_button_is_highlighted(client):
    """Params matching a preset highlight that preset, not the custom form."""
    _sign_in(client)
    first_iso, last_iso = _this_month_bounds()

    body = client.get(
        f"/profile?date_from={first_iso}&date_to={last_iso}"
    ).data.decode()

    assert "is-active" in _anchor_tag(body, "This Month"), (
        "the matched preset button must carry the active state"
    )
    assert 'class="profile-filter-custom is-active"' not in body, (
        "the custom form must not be marked active when a preset matches"
    )
    assert body.count("is-active") == 1, "exactly one control is highlighted"


def test_active_custom_range_is_highlighted(client):
    """A non-preset range highlights the custom form, not any preset."""
    _sign_in(client)

    body = client.get(
        "/profile?date_from=2020-05-01&date_to=2020-09-01"
    ).data.decode()

    assert 'class="profile-filter-custom is-active"' in body, (
        "a custom range must highlight the custom sub-form"
    )
    assert "profile-filter-preset is-active" not in body, (
        "no preset button should be highlighted for a custom range"
    )


def test_all_time_is_the_active_preset_by_default(client):
    """With no params, 'All Time' is the highlighted preset."""
    _sign_in(client)

    body = client.get("/profile").data.decode()

    assert "is-active" in _anchor_tag(body, "All Time"), (
        "'All Time' should be active when no filter is applied"
    )
    assert body.count("is-active") == 1, "only 'All Time' is highlighted by default"


def test_custom_form_prefills_inputs_from_active_range(client):
    """The custom date inputs re-populate from the validated active values."""
    _sign_in(client)

    body = client.get(
        "/profile?date_from=2021-03-01&date_to=2021-04-15"
    ).data.decode()

    assert re.search(r'name="date_from"[^>]*value="2021-03-01"', body), (
        "date_from input should be pre-filled with the active lower bound"
    )
    assert re.search(r'name="date_to"[^>]*value="2021-04-15"', body), (
        "date_to input should be pre-filled with the active upper bound"
    )


def test_custom_form_inputs_are_empty_without_a_filter(client):
    """With no active range, both custom date inputs render empty."""
    _sign_in(client)

    body = client.get("/profile").data.decode()

    assert re.search(r'name="date_from"[^>]*value=""', body), (
        "date_from input should be blank when unfiltered"
    )
    assert re.search(r'name="date_to"[^>]*value=""', body), (
        "date_to input should be blank when unfiltered"
    )


# ------------------------------------------------------------------ #
# Inclusive bounds and single-day edge case                          #
# ------------------------------------------------------------------ #

def test_range_bounds_are_inclusive_on_both_ends(client):
    """Rows dated exactly on date_from and on date_to are kept."""
    uid = _register_and_sign_in(client, "Ida Edge", "ida@example.com")
    _add_expense(uid, 11.00, "Food", "2020-05-31", "DayBefore")
    _add_expense(uid, 22.00, "Bills", "2020-06-01", "OnLowerBound")
    _add_expense(uid, 33.00, "Health", "2020-06-30", "OnUpperBound")
    _add_expense(uid, 44.00, "Other", "2020-07-01", "DayAfter")

    body = client.get(
        "/profile?date_from=2020-06-01&date_to=2020-06-30"
    ).data.decode()

    assert "OnLowerBound" in body, "a row on date_from is inside the range"
    assert "OnUpperBound" in body, "a row on date_to is inside the range"
    assert "DayBefore" not in body and "DayAfter" not in body, (
        "rows one day outside either bound must be excluded"
    )
    assert '<span class="profile-stat-value">2</span>' in body, "count stat -> 2"
    assert '<span class="profile-stat-value">₹55.00</span>' in body, (
        "total spent -> ₹55.00 (22.00 + 33.00)"
    )


def test_single_day_range_when_from_equals_to(client):
    """date_from == date_to is a valid one-day window, not an inverted range."""
    uid = _register_and_sign_in(client, "Sol Single", "sol@example.com")
    _add_expense(uid, 10.00, "Food", "2020-06-14", "Eve")
    _add_expense(uid, 20.00, "Bills", "2020-06-15", "TheDay")
    _add_expense(uid, 30.00, "Health", "2020-06-16", "Morrow")

    response = client.get("/profile?date_from=2020-06-15&date_to=2020-06-15")
    body = response.data.decode()

    assert response.status_code == 200
    assert "Start date must be before end date." not in body, (
        "an equal-bounds range is not inverted and must not flash"
    )
    assert "TheDay" in body, "the single in-range row must be kept"
    assert "Eve" not in body and "Morrow" not in body, (
        "the days either side must be excluded"
    )


# ------------------------------------------------------------------ #
# Bad input falls back to the full unfiltered page                    #
# ------------------------------------------------------------------ #

def test_inverted_range_flashes_exact_message_and_falls_back(client):
    """date_from > date_to flashes the exact message and shows everything."""
    _sign_in(client)

    response = client.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
    body = response.data.decode()

    assert response.status_code == 200
    assert "Start date must be before end date." in body, (
        "an inverted range must flash the spec's exact error text"
    )
    assert body.count('class="profile-badge"') == SEED_EXPENSE_COUNT, (
        "an inverted range must fall back to the unfiltered list"
    )
    assert SEED_TOTAL in body, "the fallback total is the full ₹6,848.75"


def test_malformed_dates_fall_back_silently_without_flash(client):
    """A malformed date string does not crash — silent unfiltered fallback."""
    _sign_in(client)

    response = client.get("/profile?date_from=not-a-date&date_to=also-bad")
    body = response.data.decode()

    assert response.status_code == 200, "malformed dates must not raise"
    assert "Start date must be before end date." not in body, (
        "malformed dates fall back silently — no flash"
    )
    assert body.count('class="profile-badge"') == SEED_EXPENSE_COUNT, (
        "malformed dates leave the page unfiltered"
    )
    assert "is-active" in _anchor_tag(body, "All Time"), (
        "the silent fallback is the 'All Time' state"
    )


def test_one_valid_one_malformed_bound_falls_back(client):
    """If either bound is malformed, the filter is not applied."""
    uid = _register_and_sign_in(client, "Ola OneBad", "ola@example.com")
    _add_expense(uid, 10.00, "Food", "2020-06-15", "KeepA")
    _add_expense(uid, 20.00, "Bills", "2025-06-15", "KeepB")

    response = client.get("/profile?date_from=2019-01-01&date_to=nonsense")
    body = response.data.decode()

    assert response.status_code == 200
    assert "KeepA" in body and "KeepB" in body, (
        "one malformed bound -> unfiltered, both rows shown"
    )
    assert "Start date must be before end date." not in body


def test_only_one_param_present_falls_back(client):
    """If either param is absent, the page falls back to unfiltered."""
    uid = _register_and_sign_in(client, "Pat Partial", "pat@example.com")
    _add_expense(uid, 10.00, "Food", "2020-06-15", "KeepA")
    _add_expense(uid, 20.00, "Bills", "2025-06-15", "KeepB")

    body = client.get("/profile?date_from=2021-01-01").data.decode()

    assert "KeepA" in body and "KeepB" in body, (
        "a one-sided range must not filter anything"
    )
    assert "Start date must be before end date." not in body


# ------------------------------------------------------------------ #
# Auth guard and empty results                                        #
# ------------------------------------------------------------------ #

def test_logged_out_profile_with_filter_params_redirects_to_login(client):
    """An unauthenticated GET /profile?date_from=...&date_to=... -> 302 /login."""
    response = client.get("/profile?date_from=2026-01-01&date_to=2026-06-01")

    assert response.status_code == 302, "protected route redirects when logged out"
    assert response.headers["Location"].endswith("/login"), (
        "the redirect target is the login page"
    )


def test_filtered_range_with_no_expenses_shows_zeros(client):
    """A range with no expenses -> ₹0.00, 0 transactions, empty breakdown, no error."""
    uid = _register_and_sign_in(client, "Ned None", "ned@example.com")
    _add_expense(uid, 40.00, "Food", "2024-03-03", "OutsideRange")

    response = client.get("/profile?date_from=2020-01-01&date_to=2020-12-31")
    body = response.data.decode()

    assert response.status_code == 200
    assert "Start date must be before end date." not in body, "valid range, no flash"
    assert '<span class="profile-stat-value">₹0.00</span>' in body, (
        "total spent must be ₹0.00 for an empty range"
    )
    assert '<span class="profile-stat-value">0</span>' in body, "0 transactions"
    assert '<span class="profile-stat-value">—</span>' in body, (
        "top category falls back to an em dash"
    )
    assert 'class="profile-badge"' not in body, "no transaction rows in an empty range"
    assert 'class="profile-bar-row"' not in body, "no breakdown bars in an empty range"


def test_amounts_keep_rupee_symbol_under_active_filter(client):
    """All amounts keep the ₹ symbol while a filter is active."""
    uid = _register_and_sign_in(client, "Ravi Rupee", "ravi@example.com")
    _add_expense(uid, 1500.00, "Food", "2022-02-02", "Lunch")

    body = client.get(
        "/profile?date_from=2022-01-01&date_to=2022-12-31"
    ).data.decode()

    assert "₹1,500.00" in body, "filtered amounts still render with ₹"


# ------------------------------------------------------------------ #
# Data layer — the db.py helpers accept and honour the range         #
# ------------------------------------------------------------------ #

def test_query_helpers_narrow_to_the_given_range(client):
    """get_expense_summary / get_recent_expenses / get_category_breakdown all
    narrow to an inclusive two-sided date range."""
    uid = _register_and_sign_in(client, "Dana Data", "dana@example.com")
    _add_expense(uid, 10.00, "Food", "2020-06-10", "InA")
    _add_expense(uid, 20.00, "Bills", "2020-06-20", "InB")
    _add_expense(uid, 30.00, "Health", "2021-06-10", "OutOfRange")

    summary = db.get_expense_summary(uid, "2020-01-01", "2020-12-31")
    assert summary["tx_count"] == 2, "only two expenses fall in 2020"
    assert summary["total"] == 30.0, "their amounts sum to 30.0"

    recent = db.get_recent_expenses(
        uid, limit=10, date_from="2020-01-01", date_to="2020-12-31"
    )
    assert {r["description"] for r in recent} == {"InA", "InB"}, (
        "recent-expenses list is confined to the range"
    )

    breakdown = db.get_category_breakdown(
        uid, date_from="2020-01-01", date_to="2020-12-31"
    )
    assert {r["category"] for r in breakdown} == {"Food", "Bills"}, (
        "category breakdown is confined to the range"
    )


def test_query_helpers_ignore_one_sided_or_absent_range(client):
    """With a bound missing, every helper behaves exactly as in Step 5."""
    uid = _register_and_sign_in(client, "Ivy Ignore", "ivy@example.com")
    _add_expense(uid, 10.00, "Food", "2020-06-10", "RowA")
    _add_expense(uid, 20.00, "Bills", "2021-06-10", "RowB")

    # Both bounds absent -> unfiltered.
    assert db.get_expense_summary(uid)["tx_count"] == 2
    assert dict(db.get_expense_summary(uid)) == dict(
        db.get_expense_summary(uid, None, None)
    ), "passing None, None must equal the no-arg call"
    assert len(db.get_recent_expenses(uid)) == 2
    assert len(db.get_category_breakdown(uid)) == 2

    # Only one bound -> still unfiltered (the filter needs both).
    assert db.get_expense_summary(uid, "2020-01-01", None)["tx_count"] == 2
    assert db.get_expense_summary(uid, None, "2020-12-31")["tx_count"] == 2
    assert len(db.get_recent_expenses(uid, date_from="2020-01-01")) == 2
    assert len(db.get_category_breakdown(uid, date_to="2020-12-31")) == 2


def test_recent_expenses_limit_applies_within_the_range(client):
    """The 10-row cap on get_recent_expenses is applied *after* the date
    filter — the newest 10 rows in the window, not a pre-capped slice."""
    uid = _register_and_sign_in(client, "Lena Limit", "lena@example.com")
    for day in range(1, 13):  # 12 in-range rows, 2020-06-01 .. 2020-06-12
        _add_expense(uid, 5.00, "Food", f"2020-06-{day:02d}", f"In{day}")
    _add_expense(uid, 5.00, "Food", "2019-01-01", "OutBefore")
    _add_expense(uid, 5.00, "Food", "2021-01-01", "OutAfter")

    rows = db.get_recent_expenses(
        uid, limit=10, date_from="2020-06-01", date_to="2020-06-30"
    )

    assert len(rows) == 10
    assert all("2020-06-01" <= r["date"] <= "2020-06-30" for r in rows)
    # Newest-first within the window: the 12th is kept, the 1st and 2nd fall off.
    assert rows[0]["date"] == "2020-06-12"
