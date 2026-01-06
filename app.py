from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from fractions import Fraction
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


# --- DATABASE MODELS ---
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


class RecipeStats(db.Model):
    recipe_id = db.Column(db.Integer, primary_key=True)
    view_count = db.Column(db.Integer, default=0)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- TEMPLATE FILTERS ---
@app.template_filter("fraction")
def fraction_formatter(amount):
    try:
        if amount is None or amount == 0: return ""
        fraction = Fraction(str(amount)).limit_denominator(8)
        if fraction.denominator == 1: return str(fraction.numerator)
        if fraction.numerator > fraction.denominator:
            whole = fraction.numerator // fraction.denominator
            remainder = fraction.numerator % fraction.denominator
            return f"{whole} {Fraction(remainder, fraction.denominator)}"
        return str(fraction)
    except:
        return str(amount)


# --- UTILITY FUNCTIONS ---
def load_recipes():
    try:
        with open("recipes.json", "r") as file:
            data = json.load(file)
            for i, r in enumerate(data):
                r['original_index'] = i
                r['total_time'] = (r.get('prep_time') or 0) + (r.get('cook_time') or 0)
                if r['total_time'] == 0: r['total_time'] = 30
            return data
    except Exception as e:
        print(f"Error loading recipes: {e}")
        return []


def split_ingredient(ingredient):
    parts = ingredient.split(" ", 2)
    if len(parts) < 3: return 1.0, "", ingredient
    try:
        amount = float(Fraction(parts[0]))
        return amount, parts[1].strip(), parts[2].strip()
    except:
        return 1.0, "pcs", ingredient


def get_category(item_name):
    item_name = item_name.lower()
    categories = {
        "Produce": ["apple", "onion", "garlic", "spinach", "tomato", "potato", "carrot", "lime", "lemon", "herb"],
        "Meat/Seafood": ["chicken", "beef", "pork", "shrimp", "salmon", "steak", "bacon"],
        "Dairy/Refrigerated": ["milk", "cheese", "butter", "eggs", "yogurt", "cream"],
        "Pantry": ["flour", "sugar", "salt", "pepper", "oil", "pasta", "syrup", "vinegar"],
        "Frozen": ["frozen", "ice cream", "pizza"]
    }
    for category, keywords in categories.items():
        if any(kw in item_name for kw in keywords): return category
    return "Other"


# --- CORE ROUTES ---

@app.route("/")
def main_page():
    all_recipes = load_recipes()
    search_query = request.args.get('search', '').lower()

    # 1. Aggregate Community Stats
    all_users = User.query.all()
    global_fav_counts = {}
    global_save_counts = {}
    view_stats = {s.recipe_id: s.view_count for s in RecipeStats.query.all()}

    for u in all_users:
        for fid in json.loads(u.favorite_ids or '[]'):
            global_fav_counts[fid] = global_fav_counts.get(fid, 0) + 1
        for sid in json.loads(u.ready_to_cook_ids or '[]'):
            global_save_counts[sid] = global_save_counts.get(sid, 0) + 1

    # 2. Map Stats to Recipes
    for r in all_recipes:
        idx = r['original_index']
        r['global_favs'] = global_fav_counts.get(idx, 0)
        r['global_saves'] = global_save_counts.get(idx, 0)
        r['global_views'] = view_stats.get(idx, 0)

    # 3. Apply Search Filter
    if search_query:
        recipes = [r for r in all_recipes if search_query in r['name'].lower() or
                   any(search_query in ing.lower() for ing in r.get('ingredients', []))]
    else:
        recipes = all_recipes

    return render_template("main_page.html", recipes=recipes)


@app.route("/recipe/<int:recipe_id>", methods=["GET", "POST"])
def recipe_details(recipe_id):
    all_recipes = load_recipes()
    recipe = next((r for r in all_recipes if r['original_index'] == recipe_id), None)

    if not recipe:
        flash("Recipe not found!")
        return redirect(url_for('main_page'))

    # Update Views
    stats = RecipeStats.query.get(recipe_id)
    if not stats:
        stats = RecipeStats(recipe_id=recipe_id, view_count=1)
        db.session.add(stats)
    else:
        stats.view_count += 1
    db.session.commit()

    # Community counts for display
    all_users = User.query.all()
    recipe['global_favs'] = sum(1 for u in all_users if recipe_id in json.loads(u.favorite_ids or '[]'))
    recipe['global_saves'] = sum(1 for u in all_users if recipe_id in json.loads(u.ready_to_cook_ids or '[]'))
    recipe['global_views'] = stats.view_count

    if request.method == "POST":
        if not current_user.is_authenticated:
            return redirect(url_for('login'))

        for ing in recipe.get("ingredients", []):
            amt, unit, name = split_ingredient(ing)
            db.session.add(
                ShoppingItem(name=name, quantity=amt, unit=unit, category=get_category(name), user_id=current_user.id))

        ready_ids = json.loads(current_user.ready_to_cook_ids or '[]')
        if recipe_id not in ready_ids:
            ready_ids.append(recipe_id)
            current_user.ready_to_cook_ids = json.dumps(ready_ids)

        db.session.commit()
        return redirect(url_for('shopping_list'))

    return render_template("recipe_details.html", recipe=recipe)


# --- SHOPPING LIST ROUTES ---

@app.route("/shopping-list")
@login_required
def shopping_list():
    items = ShoppingItem.query.filter_by(user_id=current_user.id).all()
    categories = ["Produce", "Meat/Seafood", "Dairy/Refrigerated", "Pantry", "Frozen", "Other"]
    grouped_items = {cat: [i for i in items if i.category == cat] for cat in categories}
    filtered_grouped = {k: v for k, v in grouped_items.items() if v}
    return render_template("shopping_list.html", grouped_items=filtered_grouped)


@app.route("/add-custom-item", methods=["POST"])
@login_required
def add_custom_item():
    item_name = request.form.get("item_name")
    category = request.form.get("category", "Other")
    if item_name:
        db.session.add(
            ShoppingItem(name=item_name, quantity=1.0, unit="pc", category=category, user_id=current_user.id))
        db.session.commit()
    return redirect(url_for('shopping_list'))


@app.route("/delete-item/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    item = ShoppingItem.query.get_or_404(item_id)
    if item.user_id == current_user.id:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for('shopping_list'))


@app.route("/clear-list", methods=["POST"])
@login_required
def clear_list():
    ShoppingItem.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for('shopping_list'))


@app.route("/share-list")
@login_required
def share_list():
    items = ShoppingItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash("Your list is empty!")
        return redirect(url_for('shopping_list'))

    # 1. Group and Combine Quantities
    # We use a key of (name, unit, category) to make sure we combine correctly
    combined = {}
    for item in items:
        key = (item.name.lower().strip(), item.unit.lower().strip(), item.category)
        if key not in combined:
            combined[key] = 0
        combined[key] += item.quantity

    # 2. Sort by Category
    # Convert dictionary back to a list of objects/dicts for sorting
    final_list = []
    for (name, unit, cat), qty in combined.items():
        final_list.append({'name': name, 'unit': unit, 'category': cat, 'quantity': qty})

    final_list.sort(key=lambda x: x['category'])

    # 3. Build the Formatted Text
    share_text = "🛒 *My ChefPlanner Shopping List*\n"
    current_cat = ""

    for item in final_list:
        if item['category'] != current_cat:
            current_cat = item['category']
            share_text += f"\n*{current_cat.upper()}*\n"

        # Format quantity: remove .0 if it's a whole number
        q = int(item['quantity']) if item['quantity'] % 1 == 0 else round(item['quantity'], 2)
        share_text += f"- {item['name']} ({q} {item['unit']})\n"

    # 4. Encode for URL
    encoded_text = urllib.parse.quote(share_text)
    sms_link = f"sms:?&body={encoded_text}"
    whatsapp_link = f"https://wa.me/?text={encoded_text}"

    return render_template("share_options.html", sms_link=sms_link, whatsapp_link=whatsapp_link, plain_text=share_text)


# --- USER LIST ROUTES ---

@app.route("/ready-to-cook", methods=["GET", "POST"])
@login_required
def saved_recipes():
    all_recipes = load_recipes()
    ready_ids = json.loads(current_user.ready_to_cook_ids or '[]')
    fav_ids = json.loads(current_user.favorite_ids or '[]')

    if request.method == "POST":
        recipe_id = int(request.form.get("recipe_id"))
        if "toggle_fav" in request.form:
            if recipe_id in fav_ids:
                fav_ids.remove(recipe_id)
            else:
                fav_ids.append(recipe_id)
            current_user.favorite_ids = json.dumps(fav_ids)
        elif "remove_ready" in request.form:
            if recipe_id in ready_ids: ready_ids.remove(recipe_id)
            current_user.ready_to_cook_ids = json.dumps(ready_ids)
        db.session.commit()
        return redirect(url_for('saved_recipes'))

    display_saved = [r for r in all_recipes if r.get('original_index') in ready_ids]
    return render_template("saved_recipes.html", saved_recipes=display_saved, fav_ids=fav_ids)


@app.route("/favorites")
@login_required
def favorite_recipes():
    all_recipes = load_recipes()
    fav_ids = json.loads(current_user.favorite_ids or '[]')
    display_favorites = [r for r in all_recipes if r.get('original_index') in fav_ids]
    return render_template("favorite_recipes.html", favorite_recipes=display_favorites)


# --- AUTH ROUTES ---

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        hashed_pw = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256')
        db.session.add(User(email=request.form.get("email"), password=hashed_pw))
        db.session.commit()
        return redirect(url_for('login'))
    return render_template("auth.html", action="Register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email")).first()
        if user and check_password_hash(user.password, request.form.get("password")):
            login_user(user);
            return redirect(url_for('main_page'))
    return render_template("auth.html", action="Login")


@app.route("/logout")
def logout():
    logout_user();
    return redirect(url_for('login'))


# --- GLOBAL CONTEXT ---

@app.context_processor
def inject_global_counts():
    if current_user.is_authenticated:
        return {
            'ready_count': len(json.loads(current_user.ready_to_cook_ids or '[]')),
            'fav_count': len(json.loads(current_user.favorite_ids or '[]'))
        }
    return {'ready_count': 0, 'fav_count': 0}


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)