from flask import Flask, render_template, redirect, url_for, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from fractions import Fraction
from datetime import datetime
import json
import os
import urllib.parse

app = Flask(__name__)
app.secret_key = "super_secret_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mealplanner.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# --- 1. DATABASE MODELS (Persistent Storage) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    ready_to_cook_ids = db.Column(db.Text, default='[]')
    favorite_ids = db.Column(db.Text, default='[]')
    items = db.relationship('ShoppingItem', backref='owner', lazy=True)


class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(50))
    category = db.Column(db.String(50), default="Other")
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- 2. UTILITY FUNCTIONS (Your Original Logic) ---
@app.template_filter("fraction")
def fraction_formatter(amount, max_denominator=8):
    try:
        if not amount or amount == 0: return "1"
        fraction = Fraction(str(amount)).limit_denominator(max_denominator)
        if fraction.denominator == 1: return str(fraction.numerator)
        if fraction.numerator > fraction.denominator:
            whole = fraction.numerator // fraction.denominator
            remainder = fraction.numerator % fraction.denominator
            return f"{whole} {Fraction(remainder, fraction.denominator)}"
        return str(fraction)
    except:
        return "1"


def load_recipes():
    try:
        with open("recipes.json", "r") as file:
            data = json.load(file)
            for i, r in enumerate(data): r['original_index'] = i
            return data
    except:
        return []


def split_ingredient(ingredient):
    parts = ingredient.split(" ", 2)
    if len(parts) < 3: return 0.0, "", ingredient
    try:
        amount = float(Fraction(parts[0]))
        return amount, parts[1].strip(), parts[2].strip()
    except:
        return 0.0, parts[1], parts[2]


def get_category(item_name):
    item_name = item_name.lower()
    categories = {
        "Produce": ["apple", "onion", "garlic", "spinach", "tomato", "potato", "carrot", "lime", "lemon", "lettuce"],
        "Meat/Seafood": ["chicken", "beef", "pork", "shrimp", "salmon", "steak", "bacon"],
        "Dairy/Refrigerated": ["milk", "cheese", "butter", "eggs", "yogurt", "cream"],
        "Pantry": ["flour", "sugar", "salt", "pepper", "oil", "baking powder", "pasta", "mustard", "syrup"],
        "Frozen": ["ice cream", "frozen veggies", "pizza"]
    }
    for category, keywords in categories.items():
        if any(kw in item_name for kw in keywords): return category
    return "Other"


# --- 3. ROUTES ---

@app.route("/")
def main_page():
    all_recipes = load_recipes()
    views = session.get("recipe_views", {})
    favs = json.loads(current_user.favorite_ids) if current_user.is_authenticated else []
    ready = json.loads(current_user.ready_to_cook_ids) if current_user.is_authenticated else []

    for r in all_recipes:
        idx = r['original_index']
        r['views_count'] = views.get(str(idx), 0)
        r['is_favorite'] = idx in favs
        r['is_saved'] = idx in ready

    query = request.args.get("q", "").lower().strip()
    recipes = [r for r in all_recipes if query in r["name"].lower()] if query else all_recipes
    return render_template("main_page.html", recipes=recipes)


@app.route("/recipe/<int:recipe_id>", methods=["GET", "POST"])
def recipe_details(recipe_id):
    recipes = load_recipes()
    recipe = recipes[recipe_id]

    # Session-based view counter
    views = session.get("recipe_views", {})
    views[str(recipe_id)] = views.get(str(recipe_id), 0) + 1
    session["recipe_views"] = views

    if request.method == "POST":
        if not current_user.is_authenticated: return redirect(url_for('login'))

        plates = int(request.form.get("plates", 1))
        for ing in recipe.get("ingredients", []):
            amt, unit, name = split_ingredient(ing)
            actual_amt = (amt if amt > 0 else 1.0) * plates

            # Smart Merge: check if item exists for user
            existing = ShoppingItem.query.filter_by(user_id=current_user.id, name=name, unit=unit).first()
            if existing:
                existing.quantity += actual_amt
            else:
                new_item = ShoppingItem(name=name, quantity=actual_amt, unit=unit,
                                        category=get_category(name), owner=current_user)
                db.session.add(new_item)

        # Update Ready to Cook list in DB
        ready_list = json.loads(current_user.ready_to_cook_ids)
        if recipe_id not in ready_list:
            ready_list.append(recipe_id)
            current_user.ready_to_cook_ids = json.dumps(ready_list)

        db.session.commit()
        return redirect(url_for('shopping_list'))

    return render_template("recipe_details.html", recipe=recipe)


@app.route("/shopping-list", methods=["GET", "POST"])
@login_required
def shopping_list():
    if request.method == "POST" and "clear" in request.form:
        ShoppingItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return redirect(url_for('shopping_list'))

    items = ShoppingItem.query.filter_by(user_id=current_user.id).all()
    grouped = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)

    # Sort categories in specific order
    custom_order = ["Produce", "Meat/Seafood", "Dairy/Refrigerated", "Pantry", "Frozen", "Other"]
    sorted_groups = {cat: grouped[cat] for cat in custom_order if cat in grouped}

    return render_template("shopping_list.html", grouped_list=sorted_groups)


@app.route("/remove-item/<int:item_id>", methods=["POST"])
@login_required
def remove_item(item_id):
    item = ShoppingItem.query.get_or_404(item_id)
    if item.user_id == current_user.id:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for('shopping_list'))


@app.route("/ready-to-cook", methods=["GET", "POST"])
@login_required
def saved_recipes():
    all_recipes = load_recipes()
    ready_ids = json.loads(current_user.ready_to_cook_ids)
    fav_ids = json.loads(current_user.favorite_ids)

    if request.method == "POST":
        rid = int(request.form.get("recipe_id"))
        if "remove_recipe" in request.form and rid in ready_ids:
            ready_ids.remove(rid)
        elif "favorite_recipe" in request.form:
            if rid in fav_ids:
                fav_ids.remove(rid)
            else:
                fav_ids.append(rid)

        current_user.ready_to_cook_ids = json.dumps(ready_ids)
        current_user.favorite_ids = json.dumps(fav_ids)
        db.session.commit()
        return redirect(url_for('saved_recipes'))

    display = [all_recipes[rid] for rid in ready_ids if rid < len(all_recipes)]
    return render_template("saved_recipes.html", saved_recipes=display)


@app.route("/favorites")
@login_required
def favorite_recipes():
    all_recipes = load_recipes()
    # Pull the heart-ed IDs from the database
    fav_ids = json.loads(current_user.favorite_ids)

    display = []
    for rid in fav_ids:
        # rid is the original_index
        if 0 <= rid < len(all_recipes):
            r = all_recipes[rid]
            r['original_index'] = rid
            display.append(r)

    return render_template("favorite_recipes.html", favorite_recipes=display)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        hashed_pw = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256')
        new_user = User(email=request.form.get("email"), password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template("auth.html", action="Register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email")).first()
        if user and check_password_hash(user.password, request.form.get("password")):
            login_user(user)
            return redirect(url_for('main_page'))
    return render_template("auth.html", action="Login")


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)