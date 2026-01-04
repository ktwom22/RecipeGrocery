from flask import Flask, render_template, redirect, url_for, request, session
from fractions import Fraction
from datetime import datetime
import json
import urllib.parse

app = Flask(__name__)
app.secret_key = "super_secret_key"

# ------------------------------------
#       Utility Functions
# ------------------------------------
@app.template_filter("fraction")
def fraction_formatter(amount, max_denominator=8):
    """
    Convert numbers into fractions or mixed number strings.
    """
    try:
        fraction = Fraction(amount).limit_denominator(max_denominator)
        if fraction.denominator == 1:
            return str(fraction.numerator)
        if fraction.numerator > fraction.denominator:
            whole = fraction.numerator // fraction.denominator
            remainder = fraction.numerator % fraction.denominator
            if remainder == 0:
                return str(whole)
            return f"{whole} {Fraction(remainder, fraction.denominator)}"
        return str(fraction)
    except (ValueError, ZeroDivisionError):
        return str(amount)


def load_recipes(file_path="recipes.json"):
    """
    Load recipes from a JSON file. Returns an empty list if the file doesn't exist.
    """
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return []


def split_ingredient(ingredient):
    """
    Parses a string like '2 cups sugar' into (2, "cups", "sugar").
    """
    parts = ingredient.split(" ", 2)
    if len(parts) < 3:
        raise ValueError("Invalid ingredient format")
    amount = eval(parts[0])
    unit = parts[1].strip()
    name = parts[2].strip()
    return amount, unit, name


def add_to_shopping_list(recipe=None, plates=1, manual_item=None, recipe_id=None):
    """
    Add ingredients from a recipe or manual items to the shopping list.
    """
    if "shopping_list" not in session:
        session["shopping_list"] = {}
    if "shopping_list_recipes" not in session:
        session["shopping_list_recipes"] = {}

    # Add ingredients from a recipe
    if recipe and recipe_id is not None:
        for ingredient in recipe["ingredients"]:
            try:
                amount, unit, name = split_ingredient(ingredient)
                key = f"{unit} {name}".strip()
                session["shopping_list"][key] = session["shopping_list"].get(key, 0) + amount * plates
                session["shopping_list_recipes"].setdefault(key, []).append(recipe_id)
            except ValueError:
                pass

    # Add a manually entered item
    if manual_item:
        try:
            quantity = float(manual_item["quantity"])
            unit = manual_item["unit"].strip()
            name = manual_item["name"].strip()
            key = f"{unit} {name}".strip()
            session["shopping_list"][key] = session["shopping_list"].get(key, 0) + quantity
        except ValueError:
            pass

    session.modified = True


def clear_shopping_list():
    """
    Clears all items in the shopping list.
    """
    session.pop("shopping_list", None)
    session.pop("shopping_list_recipes", None)
    session.modified = True

# ------------------------------------
#       Application Routes
# ------------------------------------
@app.route("/", methods=["GET"])
def main_page():
    """
    Display the main page with an optional search bar to find recipes.
    """
    # Load recipes (modify this to load your actual recipe data)
    recipes = load_recipes()

    # Get the search query from the request
    query = request.args.get("q", "").lower().strip()

    # If a search term is entered, filter recipes
    if query:
        filtered_recipes = []
        for recipe in recipes:
            # Check if the query matches the recipe name or any ingredient
            if query in recipe["name"].lower() or any(query in ingredient.lower() for ingredient in recipe["ingredients"]):
                filtered_recipes.append(recipe)
        recipes = filtered_recipes

    # Pass the filtered recipes to the template
    return render_template("main_page.html", recipes=recipes)


@app.route("/recipe/<int:recipe_id>", methods=["GET", "POST"])
def recipe_details(recipe_id):
    """
    View recipe details, track views, and optionally add ingredients to a shopping list.
    """
    recipes = load_recipes()

    # Ensure valid recipe_id
    if 0 <= recipe_id < len(recipes):
        recipe = recipes[recipe_id]

        # Initialize views in session if not set
        if "recipe_views" not in session:
            session["recipe_views"] = {}

        # Sanitize session keys (ensure consistent types)
        session["recipe_views"] = {int(k): v for k, v in session["recipe_views"].items()}
        session["recipe_views"][recipe_id] = session["recipe_views"].get(recipe_id, 0) + 1
        session.modified = True

        # Attach views count directly to the recipe so it's passed to the template
        recipe["views"] = session["recipe_views"].get(recipe_id, 0)

        # Handle POST requests for adding to shopping list
        if request.method == "POST":
            plates = int(request.form.get("plates", 1))
            add_to_shopping_list(recipe=recipe, plates=plates, recipe_id=recipe_id)

            # Initialize saved recipes if not set
            if "saved_recipes" not in session:
                session["saved_recipes"] = {}

            session["saved_recipes"] = {int(k): v for k, v in session["saved_recipes"].items()}
            session["saved_recipes"][recipe_id] = session["saved_recipes"].get(
                recipe_id,
                {"date_saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
            )
            session.modified = True
            return redirect(url_for("shopping_list"))

        # Render recipe details with views count
        return render_template("recipe_details.html", recipe=recipe)

    # Handle invalid recipe_id
    return render_template("error.html", message="Recipe not found."), 404

@app.route("/shopping-list", methods=["GET", "POST"])
def shopping_list():
    """
    Manage the shopping list. Supports manual item additions and clearing the list.
    """
    if request.method == "POST":
        if "add_manual_item" in request.form:
            quantity = request.form.get("quantity", "").strip()
            unit = request.form.get("unit", "").strip()
            name = request.form.get("name", "").strip()
            if quantity.replace('.', '', 1).isdigit():
                manual_item = {"quantity": quantity, "unit": unit, "name": name}
                add_to_shopping_list(manual_item=manual_item)

        if "clear" in request.form:
            clear_shopping_list()

    return render_template(
        "shopping_list.html",
        shopping_list=session.get("shopping_list", {}),
        shopping_list_recipes=session.get("shopping_list_recipes", {}),
    )


@app.route("/saved-recipes", methods=["GET", "POST"])
def saved_recipes():
    """
    View and manage saved recipes. Users can favorite or remove recipes.
    """
    recipes = load_recipes()
    saved_recipes_data = session.get("saved_recipes", {})

    # Ensure saved_recipes keys are integers
    saved_recipes_data = {int(k): v for k, v in saved_recipes_data.items()}
    session["saved_recipes"] = saved_recipes_data
    session.modified = True

    favorite_ids = session.get("favorite_recipes", [])

    if request.method == "POST":
        recipe_id = int(request.form["recipe_id"])

        if "remove_recipe" in request.form:
            saved_recipes_data.pop(recipe_id, None)
        elif "favorite_recipe" in request.form:
            if recipe_id in favorite_ids:
                favorite_ids.remove(recipe_id)
            else:
                favorite_ids.append(recipe_id)

        session["saved_recipes"] = saved_recipes_data
        session["favorite_recipes"] = favorite_ids
        session.modified = True

    saved_recipes = [
        {
            "id": recipe_id,
            "name": recipes[recipe_id]["name"],
            "image": recipes[recipe_id].get("image"),
            "date_saved": metadata["date_saved"],
            "is_favorite": recipe_id in favorite_ids,
        }
        for recipe_id, metadata in saved_recipes_data.items()
        if recipe_id < len(recipes)
    ]

    return render_template("saved_recipes.html", saved_recipes=saved_recipes)


@app.route("/remove-item/<path:item_key>", methods=["POST"])
def remove_item(item_key):
    """
    Remove an item from the shopping list.
    """
    item_key = urllib.parse.unquote(item_key).strip()
    if "shopping_list" in session:
        session["shopping_list"].pop(item_key, None)
        session["shopping_list_recipes"].pop(item_key, None)
        session.modified = True
    return redirect(url_for("shopping_list"))

@app.route("/favorites", methods=["GET", "POST"])
def favorite_recipes():
    """
    View and manage favorite recipes.
    """
    recipes = load_recipes()
    favorite_ids = session.get("favorite_recipes", [])
    saved_recipes_data = session.get("saved_recipes", {})

    # Filter favorite recipes from the saved recipes
    favorite_recipes = [
        {
            "id": recipe_id,
            "name": recipes[recipe_id]["name"],
            "image": recipes[recipe_id].get("image"),
            "date_saved": saved_recipes_data.get(recipe_id, {}).get("date_saved", "Unknown"),
        }
        for recipe_id in favorite_ids if recipe_id in saved_recipes_data
    ]

    return render_template("favorite_recipes.html", favorite_recipes=favorite_recipes)
# ------------------------------------
#       Run Application
# ------------------------------------
if __name__ == "__main__":
    app.run(debug=True)