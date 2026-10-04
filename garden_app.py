import os
import hmac
import json
import secrets
import sqlite3
import numpy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DATABASE = Path(__file__).with_name("garden.db")


@app.context_processor
def inject_csrf_token():
    token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return {"csrf_token": token}


@app.before_request
def validate_csrf_token():
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        provided = request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return "Invalid or missing CSRF token", 400


def init_db():
    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS gardens (
                user_id INTEGER PRIMARY KEY,
                sun TEXT NOT NULL,
                water TEXT NOT NULL,
                experience TEXT NOT NULL,
                rows INTEGER NOT NULL DEFAULT 20,
                columns INTEGER NOT NULL DEFAULT 20,
                description TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS buddy_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                recipient_id INTEGER,
                recipient_accepted INTEGER NOT NULL DEFAULT 0,
                owner_confirmed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (owner_id) REFERENCES users (id),
                FOREIGN KEY (recipient_id) REFERENCES users (id)
            )"""
        )
        garden_columns = {row[1] for row in connection.execute("PRAGMA table_info(gardens)")}
        if "rows" not in garden_columns:
            connection.execute("ALTER TABLE gardens ADD COLUMN rows INTEGER NOT NULL DEFAULT 20")
        if "columns" not in garden_columns:
            connection.execute("ALTER TABLE gardens ADD COLUMN columns INTEGER NOT NULL DEFAULT 20")
        if "description" not in garden_columns:
            connection.execute("ALTER TABLE gardens ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        for column, definition in {
            "daily_goal": "TEXT NOT NULL DEFAULT ''",
            "daily_limit": "INTEGER NOT NULL DEFAULT 0",
            "grid_state": "TEXT NOT NULL DEFAULT ''",
            "goal_tile_row": "INTEGER NOT NULL DEFAULT 1",
            "goal_tile_column": "INTEGER NOT NULL DEFAULT 1",
            "last_checkin": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in garden_columns:
                connection.execute(f"ALTER TABLE gardens ADD COLUMN {column} {definition}")
        if "habit_timer_started_at" not in garden_columns:
            connection.execute("ALTER TABLE gardens ADD COLUMN habit_timer_started_at TEXT NOT NULL DEFAULT ''")
        connection.execute(
            "UPDATE gardens SET habit_timer_started_at = ? WHERE daily_goal != '' AND habit_timer_started_at = ''",
            (datetime.now(timezone.utc).isoformat(),),
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                timer_started_at TEXT NOT NULL,
                last_checkin TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS habits_user_id_idx ON habits (user_id, id)"
        )
        connection.execute(
            """INSERT INTO habits (user_id, name, timer_started_at, last_checkin)
               SELECT g.user_id, g.daily_goal, g.habit_timer_started_at, g.last_checkin
               FROM gardens g
               WHERE TRIM(g.daily_goal) != ''
                 AND NOT EXISTS (
                     SELECT 1 FROM habits h WHERE h.user_id = g.user_id
                 )"""
        )
        connection.execute(
            """UPDATE gardens
               SET daily_goal = '', habit_timer_started_at = ''
               WHERE daily_goal != ''
                 AND EXISTS (
                     SELECT 1 FROM habits h WHERE h.user_id = gardens.user_id
                 )"""
        )


init_db()


def ensure_default_garden(user_id):
    """Create a fixed 20 by 20 garden when an account has none."""
    grid = build_garden_grid({"rows": 20, "columns": 20}, user_id).tolist()
    tile_row, tile_column = choose_random_tile_for_grid(numpy.asarray(grid), numpy.random)
    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """INSERT OR IGNORE INTO gardens
               (user_id, sun, water, experience, rows, columns, grid_state,
                goal_tile_row, goal_tile_column)
               VALUES (?, 'sunny', 'high', 'beginner', 20, 20, ?, ?, ?)""",
            (user_id, json.dumps(grid), tile_row, tile_column),
        )


def choose_random_tile_for_grid(garden, rng):
    """Return a valid tile while avoiding index errors on small grids."""
    if garden is None or len(garden.shape) < 2:
        raise ValueError("Garden must be a 2D array-like grid.")
    rows, columns = garden.shape[:2]
    if rows <= 0 or columns <= 0:
        raise ValueError("Garden grid cannot be empty.")

    draw = rng.randint if rng is numpy.random else rng.integers
    row_start = 0 if rows <= 2 else 1
    row_end = rows if rows <= 2 else rows - 1
    column_start = 0 if columns <= 2 else 1
    column_end = columns if columns <= 2 else columns - 1
    row = draw(row_start, row_end)
    column = draw(column_start, column_end)
    return int(row), int(column)


def build_garden_grid(preferences, user_id):
    """Create a sized garden grid with the simulation's base growth per tile."""
    rows = preferences["rows"]
    columns = preferences["columns"]
    garden_grid = numpy.zeros((rows, columns, 3), dtype=int)
    garden_grid[:, :, 0] = 5
    return garden_grid


@app.route("/")
def home():
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or not password:
        flash("Please fill in every field.", "error")
        return render_template("signup.html"), 400
    if len(password) < 8:
        flash("Your password must be at least 8 characters.", "error")
        return render_template("signup.html"), 400

    try:
        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
    except sqlite3.IntegrityError:
        flash("An account with that email already exists.", "error")
        return render_template("signup.html"), 409

    session.clear()
    session["user_id"] = cursor.lastrowid
    ensure_default_garden(cursor.lastrowid)
    flash("Your account was created! Set your first habit in your garden.", "success")
    return redirect(url_for("garden"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("The email or password you entered is incorrect.", "error")
        return render_template("login.html"), 401

    session.clear()
    session["user_id"] = user["id"]
    ensure_default_garden(user["id"])
    flash("Welcome back!", "success")
    return redirect(url_for("garden"))


@app.route("/questions")
def questions():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("garden"))


@app.route("/garden", methods=["GET", "POST"])
def garden():
    user_id = session.get("user_id")
    if user_id is None:
        return redirect(url_for("login"))

    action = request.form.get("action")
    if request.method == "POST" and action == "advance_timer":
        habit_id = request.form.get("habit_id", type=int)
        if habit_id is None:
            flash("Select a habit to advance.", "error")
            return redirect(url_for("garden"))
        with sqlite3.connect(DATABASE) as connection:
            connection.execute(
                "UPDATE habits SET timer_started_at = ? WHERE id = ? AND user_id = ?",
                ((datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(), habit_id, user_id),
            )
        flash("Timer moved forward.", "success")
        return redirect(url_for("garden", habit=habit_id))

    if request.method == "POST" and action == "checkin":
        completed_value = request.form.get("completed")
        habit_id = request.form.get("habit_id", type=int)
        if completed_value not in {"yes", "no"}:
            flash("Choose whether you completed this habit.", "error")
            return redirect(url_for("garden", habit=habit_id) if habit_id else url_for("garden"))
        completed = completed_value == "yes"
        now = datetime.now(timezone.utc)
        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            preferences = connection.execute(
                "SELECT * FROM gardens WHERE user_id = ?", (user_id,)
            ).fetchone()
            habit = connection.execute(
                "SELECT id, timer_started_at FROM habits WHERE id = ? AND user_id = ?",
                (habit_id, user_id),
            ).fetchone() if habit_id else None
            if (preferences is None or habit is None or not habit["timer_started_at"]
                    or now < datetime.fromisoformat(habit["timer_started_at"]) + timedelta(hours=24)):
                flash("There is no daily check-in due yet.", "error")
                return redirect(url_for("garden", habit=habit_id) if habit_id else url_for("garden"))
            grid = json.loads(preferences["grid_state"]) if preferences["grid_state"] else build_garden_grid(preferences, user_id).tolist()
            row, column = preferences["goal_tile_row"], preferences["goal_tile_column"]
            if completed:
                grid[row][column][0] = max(0, grid[row][column][0] + 1)
            else:
                row, column = choose_random_tile_for_grid(numpy.asarray(grid), numpy.random)
                grid[row][column][0] = max(0, grid[row][column][0] - 1)
            next_row, next_column = choose_random_tile_for_grid(numpy.asarray(grid), numpy.random)
            connection.execute(
                "UPDATE gardens SET grid_state = ?, goal_tile_row = ?, goal_tile_column = ?, last_checkin = ?, habit_timer_started_at = ? WHERE user_id = ?",
                (json.dumps(grid), next_row, next_column, date.today().isoformat(), now.isoformat(), user_id),
            )
            connection.execute(
                "UPDATE habits SET timer_started_at = ?, last_checkin = ? WHERE id = ? AND user_id = ?",
                (now.isoformat(), date.today().isoformat(), habit_id, user_id),
            )
        flash("Nice work! Your garden grew by 1 point." if completed else "Your garden lost 1 point. A new 24-hour cycle has started.", "success" if completed else "error")
        return redirect(url_for("garden", habit=habit_id))

    if request.method == "POST" and action == "save_goal":
        daily_goal = request.form.get("daily_goal", "").strip()
        if not daily_goal:
            flash("Enter a habit or goal to track.", "error")
            return redirect(url_for("garden"))
        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.execute(
                "INSERT INTO habits (user_id, name, timer_started_at) VALUES (?, ?, ?)",
                (user_id, daily_goal[:200], datetime.now(timezone.utc).isoformat()),
            )
            habit_id = cursor.lastrowid
        flash("Habit added. Your 24-hour cycle starts now.", "success")
        return redirect(url_for("garden", habit=habit_id))

    if request.method == "POST" and action == "delete_goal":
        habit_id = request.form.get("habit_id", type=int)
        if habit_id is None:
            flash("Select a habit to delete.", "error")
            return redirect(url_for("garden"))
        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.execute(
                "DELETE FROM habits WHERE id = ? AND user_id = ?",
                (habit_id, user_id),
            )
        if cursor.rowcount != 1:
            flash("That habit could not be found.", "error")
        else:
            flash("Habit deleted.", "success")
        return redirect(url_for("garden"))

    if request.method == "POST" and action in {"offer", "request", "accept", "confirm"}:
        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            try:
                if action == "offer":
                    description = request.form.get("description", "").strip()
                    if not description:
                        raise ValueError("Add a short note about the kind of garden buddy you want.")
                    connection.execute(
                        "INSERT INTO buddy_offers (owner_id, description) VALUES (?, ?)",
                        (user_id, description[:300]),
                    )
                    flash("Your buddy offer is now visible to other gardeners.", "success")
                elif action == "request":
                    offer_id = int(request.form.get("offer_id", ""))
                    offer = connection.execute(
                        "SELECT owner_id, recipient_id FROM buddy_offers WHERE id = ?", (offer_id,)
                    ).fetchone()
                    if offer is None or offer["recipient_id"] is not None or offer["owner_id"] == user_id:
                        raise ValueError("That buddy offer is no longer available.")
                    cursor = connection.execute(
                        "UPDATE buddy_offers SET recipient_id = ? WHERE id = ? AND recipient_id IS NULL",
                        (user_id, offer_id),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("That buddy offer is no longer available.")
                    flash("Request sent. The offer owner can confirm after you accept.", "success")
                elif action in {"accept", "confirm"}:
                    offer_id = int(request.form.get("offer_id", ""))
                    offer = connection.execute(
                        "SELECT owner_id, recipient_id, recipient_accepted FROM buddy_offers WHERE id = ?", (offer_id,)
                    ).fetchone()
                    if offer is None:
                        raise ValueError("Buddy offer not found.")
                    if action == "accept" and offer["recipient_id"] == user_id:
                        connection.execute("UPDATE buddy_offers SET recipient_accepted = 1 WHERE id = ?", (offer_id,))
                        flash("You accepted the buddy request. The owner can confirm it now.", "success")
                    elif action == "confirm" and offer["owner_id"] == user_id and offer["recipient_accepted"]:
                        connection.execute("UPDATE buddy_offers SET owner_confirmed = 1 WHERE id = ?", (offer_id,))
                        flash("You are connected! You can now view each other's garden grids.", "success")
                    else:
                        raise ValueError("This action is not available for your account yet.")
                else:
                    raise ValueError("Unknown buddy action.")
            except (ValueError, TypeError):
                flash("That buddy action could not be completed. Refresh and try again.", "error")
        return redirect(url_for("garden"))

    if request.method == "POST" and action != "setup":
        flash("Unknown garden action.", "error")
        return redirect(url_for("garden"))

    if request.method == "GET":
        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            preferences = connection.execute(
                "SELECT * FROM gardens WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if preferences is None:
            ensure_default_garden(user_id)
            return redirect(url_for("garden"))
        else:
            plants = []
            needs_setup = False
            grid = json.loads(preferences["grid_state"]) if preferences["grid_state"] else build_garden_grid(preferences, user_id).tolist()

        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            habits = [
                dict(habit)
                for habit in connection.execute(
                    "SELECT id, name, timer_started_at, last_checkin FROM habits WHERE user_id = ? ORDER BY id DESC",
                    (user_id,),
                ).fetchall()
            ]

        now = datetime.now(timezone.utc)
        for habit in habits:
            started_at = datetime.fromisoformat(habit["timer_started_at"])
            next_checkin_at = started_at + timedelta(hours=24)
            habit["next_checkin_at"] = next_checkin_at.isoformat()
            habit["checkin_due"] = now >= next_checkin_at

        requested_habit_id = request.args.get("habit", type=int)
        selected_habit = next(
            (habit for habit in habits if habit["id"] == requested_habit_id),
            habits[0] if habits else None,
        )

        timer_started_at = (
            datetime.fromisoformat(selected_habit["timer_started_at"])
            if selected_habit else None
        )
        next_checkin_at = timer_started_at + timedelta(hours=24) if timer_started_at else None
        checkin_due = bool(selected_habit and selected_habit["checkin_due"])
        daily_goal = selected_habit["name"] if selected_habit else ""
        timer_deadline = next_checkin_at.isoformat() if next_checkin_at else ""

        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            offers = connection.execute(
                """SELECT b.*, owner.name AS owner_name, recipient.name AS recipient_name
                   FROM buddy_offers b JOIN users owner ON owner.id = b.owner_id
                   LEFT JOIN users recipient ON recipient.id = b.recipient_id
                   WHERE b.owner_id = ? OR b.recipient_id = ? OR b.recipient_id IS NULL
                   ORDER BY b.id DESC""",
                (user_id, user_id),
            ).fetchall()
            buddies = connection.execute(
                """SELECT CASE WHEN b.owner_id = ? THEN b.recipient_id ELSE b.owner_id END AS buddy_id,
                          u.name AS buddy_name
                   FROM buddy_offers b JOIN users u
                     ON u.id = CASE WHEN b.owner_id = ? THEN b.recipient_id ELSE b.owner_id END
                   WHERE (b.owner_id = ? OR b.recipient_id = ?)
                     AND b.recipient_accepted = 1 AND b.owner_confirmed = 1""",
                (user_id, user_id, user_id, user_id),
            ).fetchall()

        viewing = request.args.get("buddy", type=int)
        if viewing:
            authorized = any(row["buddy_id"] == viewing for row in buddies)
            with sqlite3.connect(DATABASE) as connection:
                connection.row_factory = sqlite3.Row
                shared_preferences = connection.execute(
                    "SELECT rows, columns, grid_state FROM gardens WHERE user_id = ?", (viewing,)
                ).fetchone() if authorized else None
                buddy = connection.execute("SELECT name FROM users WHERE id = ?", (viewing,)).fetchone() if authorized else None
            if not authorized:
                flash("You can only view a confirmed buddy's garden.", "error")
                return redirect(url_for("garden"))
            if shared_preferences:
                grid = json.loads(shared_preferences["grid_state"]) if shared_preferences["grid_state"] else build_garden_grid(shared_preferences, viewing).tolist()
                plants = []
                needs_setup = False
            else:
                grid = None
                plants = []
                needs_setup = True
            viewing_name = buddy["name"]
        else:
            viewing_name = None

        return render_template("garden.html", plants=plants, needs_setup=needs_setup, grid=grid,
                               offers=offers, buddies=buddies, viewing_name=viewing_name,
                               habits=habits, selected_habit=selected_habit,
                               checkin_due=checkin_due,
                               next_checkin_at=next_checkin_at.isoformat() if next_checkin_at else "",
                               timer_deadline=timer_deadline,
                               timer_started_at=timer_started_at.isoformat() if timer_started_at else "",
                               habit_timer_started_at=timer_started_at.isoformat() if timer_started_at else "",
                               daily_goal=daily_goal,
                               daily_limit=preferences["daily_limit"] if preferences else 0,
                               preferences=preferences)

    return redirect(url_for("garden"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
