import os
import sqlite3
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

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


init_db()


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
            connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
    except sqlite3.IntegrityError:
        flash("An account with that email already exists.", "error")
        return render_template("signup.html"), 409

    flash("Your account was created! You can start planning your garden.", "success")
    return redirect(url_for("questions"))


@app.route("/questions")
def questions():
    return render_template("questions.html")


@app.route("/garden", methods=["POST"])
def garden():
    sun = request.form.get("sun")
    water = request.form.get("water")
    experience = request.form.get("experience")

    if sun == "sunny":
        plants = ["Tomatoes", "Basil", "Marigolds"]
    else:
        plants = ["Lettuce", "Spinach", "Mint"]

    if water == "low":
        plants.append("A drought-tolerant plant, such as rosemary")
    if experience == "beginner":
        plants.append("Try starting with easy-to-grow herbs")

    return render_template("garden.html", plants=plants)


if __name__ == "__main__":
    app.run(debug=True)
