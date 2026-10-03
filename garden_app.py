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
