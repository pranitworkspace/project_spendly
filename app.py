import os

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import create_user, get_user_by_email, init_db, seed_db

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
        return redirect(url_for("landing"))

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
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
