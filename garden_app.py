from flask import Flask, render_template, request

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/questions")
def questions():
    return render_template("questions.html")


@app.route("/garden", methods=["POST"])
def garden():
    answers = {
        "sun": request.form.get("sun"),
        "water": request.form.get("water"),
        "experience": request.form.get("experience")
    }

    plants = recommend_plants(answers)

    return render_template(
        "garden.html",
        plants=plants
    )


def recommend_plants(answers):
    plants = []

    if answers["sun"] == "sunny":
        plants.append("Tomatoes")
        plants.append("Basil")

    elif answers["sun"] == "shady":
        plants.append("Lettuce")
        plants.append("Spinach")

    else:
        plants.append("Mint")

    if answers["water"] == "low":
        plants.append("Rosemary")

    if answers["experience"] == "beginner":
        plants.append("Green Beans")

    return plants


if __name__ == "__main__":
    app.run(debug=True)