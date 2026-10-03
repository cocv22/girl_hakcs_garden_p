import os
import sqlite3
import numpy
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-development-only-change-me")
DATABASE = Path(__file__).with_name("garden.db")


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
                FOREIGN KEY (user_id) REFERENCES users (id)
            )"""
        )


init_db()
def ChooseRandomTile():
    x = numpy.random.randint(1, 19)
    y = numpy.random.randint(1, 19)
    return (x, y)

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
def ChangeGardenOversVars(NegativeTotal1,NegativeTotal2,PositiveTotal,Decay,Garden):
    while PositiveTotal > 0:
        x, y = ChooseRandomTile()
    if (PositiveTotal > 6):
            # add circle adder
            AddStuffToTileCircleR2(x, y, Garden)
            PositiveTotal -= 6
    else:
            AddStuffToTile(x, y, PositiveTotal, Garden)
            PositiveTotal -= 1 
    while NegativeTotal1 > 0:
        x, y = ChooseRandomTile()
        RemoveStuffFromTile(x, y, 1, Garden)
        NegativeTotal1 -= 1
    while NegativeTotal2 >= 50:
        StrikeStuffFromTile(x, y, 50, Garden)
        NegativeTotal2 -= 50
    while Decay > 0:
        x, y = ChooseRandomTile()
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
    for x in range(20):
        for y in range(20):
            if GetTier(Garden[x][y][0]) > GetTier(Garden[x][y][0] - Garden[x][y][2]):
               Garden[x][y][0] = Garden[x][y][0] - Garden[x][y][2]

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
    return render_template("questions.html")


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

    if request.method == "GET":
        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            preferences = connection.execute(
                "SELECT sun, water, experience FROM gardens WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if preferences is None:
            plants = ["Basil", "Lettuce", "Marigolds"]
            needs_setup = True
        else:
            plants = recommend_plants(
                preferences["sun"], preferences["water"], preferences["experience"]
            )
            needs_setup = False
        return render_template("garden.html", plants=plants, needs_setup=needs_setup)

    sun = request.form.get("sun")
    water = request.form.get("water")
    experience = request.form.get("experience")

    if sun not in {"sunny", "shady"} or water not in {"low", "high"} or experience not in {"beginner", "experienced"}:
        flash("Please answer each question to set up your garden.", "error")
        return redirect(url_for("questions"))

    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """INSERT INTO gardens (user_id, sun, water, experience)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   sun = excluded.sun,
                   water = excluded.water,
                   experience = excluded.experience""",
            (user_id, sun, water, experience),
        )
    return redirect(url_for("garden"))


if __name__ == "__main__":
    app.run(debug=True)
