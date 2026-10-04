import os
import hmac
import secrets
import sqlite3
import numpy
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
        # Add grid dimensions for databases created by earlier versions.
        garden_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(gardens)")
        }
        if "rows" not in garden_columns:
            connection.execute("ALTER TABLE gardens ADD COLUMN rows INTEGER NOT NULL DEFAULT 20")
        if "columns" not in garden_columns:
            connection.execute("ALTER TABLE gardens ADD COLUMN columns INTEGER NOT NULL DEFAULT 20")


init_db()
def ChooseRandomTile(rng=None):
    rng = rng or numpy.random
    x = rng.randint(1, 19) if rng is numpy.random else rng.integers(1, 19)
    y = rng.randint(1, 19) if rng is numpy.random else rng.integers(1, 19)
    return (x, y)

def choose_random_tile_for_grid(garden, rng):
    """Choose an interior tile so neighborhood operations stay inside the grid."""
    draw = rng.randint if rng is numpy.random else rng.integers
    row = draw(1, garden.shape[0] - 1)
    column = draw(1, garden.shape[1] - 1)
    return row, column

def AddStuffToTileCircleR2(x, y, Garden):
    #sorry to your eyes, Its not easy on my eyes
    AddStuffToTile(x, y, 2, Garden)
    AddStuffToTile(x + 1, y,1, Garden)
    AddStuffToTile(x - 1, y,1, Garden)
    AddStuffToTile(x, y + 1,1, Garden)
    AddStuffToTile(x, y - 1,1, Garden)

def AddStuffToTile(x, y, Amount, Garden):
    if Garden[x][y][1] > 0:
        Garden[x][y][1] -= Amount
    elif Garden[x][y][2] < 0:
        Garden[x][y][2] -= Amount
    else:
        Garden[x][y][0] += Amount

def RemoveStuffFromTile(x, y, Amount, Garden):
    if Garden[x][y][0] > 0:
        Garden[x][y][0] -= Amount
    else:
        Garden[x][y][1] += Amount

def StrikeStuffFromTile(x, y, Amount, Garden):
    if Garden[x][y][0] < 35:
        Garden[x][y][0] = 0
        Garden[x][y][1] = 20
    else:
        Garden[x][y][0] -= 20

    if Garden[x-1][y][0] < 10:
        Garden[x-1][y][0] = 0
        Garden[x-1][y][1] = 5
    else:
        Garden[x-1][y][0] -= 5

    if Garden[x+1][y][0] < 10:
        Garden[x+1][y][0] = 0
        Garden[x+1][y][1] = 5
    else:
        Garden[x+1][y][0] -= 5

    if Garden[x][y+1][0] < 10:
        Garden[x][y+1][0] = 0
        Garden[x][y+1][1] = 5
    else:
        Garden[x][y+1][0] -= 5

    if Garden[x][y-1][0] < 10:
        Garden[x][y-1][0] = 0
        Garden[x][y-1][1] = 5
    else:
        Garden[x][y-1][0] -= 5

def DecayStuffFromTile(x, y, Amount, Garden):
    Garden[x][y][2] += Amount
def ChangeGardenOversVars(NegativeTotal1,NegativeTotal2,PositiveTotal,Decay,Garden,rng=None):
    if rng is None:
        rng = numpy.random.default_rng()
    while PositiveTotal > 0:
        x, y = choose_random_tile_for_grid(Garden, rng)
        if PositiveTotal > 6:
            # add circle adder
            AddStuffToTileCircleR2(x, y, Garden)
            PositiveTotal -= 6
        else:
            AddStuffToTile(x, y, PositiveTotal, Garden)
            PositiveTotal = 0
    while NegativeTotal1 > 0:
        x, y = choose_random_tile_for_grid(Garden, rng)
        RemoveStuffFromTile(x, y, 1, Garden)
        NegativeTotal1 -= 1
    while NegativeTotal2 >= 50:
        x, y = choose_random_tile_for_grid(Garden, rng)
        StrikeStuffFromTile(x, y, 50, Garden)
        NegativeTotal2 -= 50
    while Decay > 0:
        x, y = choose_random_tile_for_grid(Garden, rng)
        DecayStuffFromTile(x, y, 1, Garden)
        Decay -= 1

    return(NegativeTotal1,NegativeTotal2,PositiveTotal,Decay)

def GetTier(value, tiers):
    low = 0
    high = len(tiers)  # exclusive upper bound

    while low < high:
        mid = (low + high) // 2

        if tiers[mid] <= value:
            low = mid + 1
        else:
            high = mid

    return max(0, low - 1)


def RealizeDecay(Garden,Tiers):
    for x in range(Garden.shape[0]):
        for y in range(Garden.shape[1]):
            remaining = max(0, Garden[x][y][0] - Garden[x][y][2])
            if GetTier(Garden[x][y][0], Tiers) > GetTier(remaining, Tiers):
               Garden[x][y][0] = remaining


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
    flash("Your account was created! You can start planning your garden.", "success")
    return redirect(url_for("questions"))


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
    flash("Welcome back!", "success")
    return redirect(url_for("garden"))


@app.route("/questions")
def questions():
    if "user_id" not in session:
        return redirect(url_for("login"))
    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        preferences = connection.execute(
            "SELECT sun, water, experience, rows, columns FROM gardens WHERE user_id = ?",
            (session["user_id"],),
        ).fetchone()
    return render_template("questions.html", preferences=preferences)


def recommend_plants(sun, water, experience):
    plants = ["Tomatoes", "Basil", "Marigolds"] if sun == "sunny" else ["Lettuce", "Spinach", "Mint"]
    if water == "low":
        plants.append("Rosemary, a drought-tolerant choice")
    if experience == "beginner":
        plants.append("Easy-to-grow herbs are a good place to start")
    return plants


@app.route("/garden", methods=["GET", "POST"])
def garden():
    user_id = session.get("user_id")
    if user_id is None:
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action")
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

    if request.method == "GET":
        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            preferences = connection.execute(
                "SELECT sun, water, experience, rows, columns FROM gardens WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if preferences is None:
            plants = ["Basil", "Lettuce", "Marigolds"]
            needs_setup = True
            grid = None
        else:
            plants = recommend_plants(preferences["sun"], preferences["water"], preferences["experience"])
            needs_setup = False
            grid = build_garden_grid(preferences, user_id).tolist()
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
                    "SELECT rows, columns FROM gardens WHERE user_id = ?", (viewing,)
                ).fetchone() if authorized else None
                buddy = connection.execute("SELECT name FROM users WHERE id = ?", (viewing,)).fetchone() if authorized else None
            if not authorized:
                flash("You can only view a confirmed buddy's garden.", "error")
                return redirect(url_for("garden"))
            if shared_preferences:
                grid = build_garden_grid(shared_preferences, viewing).tolist()
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
                               offers=offers, buddies=buddies, viewing_name=viewing_name)

    try:
        rows = int(request.form.get("rows", "20"))
        columns = int(request.form.get("columns", "20"))
    except ValueError:
        rows = columns = 0

    if not 3 <= rows <= 30 or not 3 <= columns <= 30:
        flash("Choose grid dimensions from 3 to 30.", "error")
        return redirect(url_for("questions"))

    sun = request.form.get("sun", "sunny")
    water = request.form.get("water", "high")
    experience = request.form.get("experience", "beginner")
    if sun not in {"sunny", "shady"} or water not in {"low", "high"} or experience not in {"beginner", "experienced"}:
        flash("Choose valid garden preferences.", "error")
        return redirect(url_for("questions"))

    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """INSERT INTO gardens (user_id, sun, water, experience, rows, columns)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   sun = excluded.sun,
                   water = excluded.water,
                   experience = excluded.experience,
                   rows = excluded.rows,
                   columns = excluded.columns""",
            (user_id, sun, water, experience, rows, columns),
        )
    return redirect(url_for("garden"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
