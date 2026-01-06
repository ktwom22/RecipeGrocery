import requests
import os
from dotenv import load_dotenv
import json
import time

load_dotenv()
API_KEY = os.getenv('SPOONACULAR_API_KEY')


def fetch_recipes(number):
    # random?number=X is the best way to get fresh data
    url = f"https://api.spoonacular.com/recipes/random?apiKey={API_KEY}&number={number}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get('recipes', [])
    return []


def is_vegetarian(recipe):
    # Check both the API flag and the ingredient list for accuracy
    if recipe.get("vegetarian"): return True
    non_veg = ["chicken", "beef", "pork", "fish", "meat", "bacon", "shrimp"]
    for ing in recipe.get("extendedIngredients", []):
        if any(nv in ing["name"].lower() for nv in non_veg):
            return False
    return False


def format_recipes(recipes):
    formatted = []
    for r in recipes:
        # 1. Clean Instructions: Convert string to a LIST to fix character-stacking bug
        raw_instructions = r.get("instructions", "No instructions available.")
        if raw_instructions:
            # Split by periods or newlines to create a clean list for your frontend loop
            instruction_list = [step.strip() for step in
                                raw_instructions.replace('<li>', '').replace('</li>', '').split('.') if
                                len(step.strip()) > 5]
        else:
            instruction_list = ["Step-by-step instructions not provided."]

        # 2. Smart Time Calculation: Ensure we never have 'null'
        total_time = r.get("readyInMinutes", 30)
        prep = r.get("preparationMinutes")
        cook = r.get("cookingMinutes")

        # If Spoonacular gives us 0 or None, we estimate it
        if not prep or prep <= 0: prep = 10
        if not cook or cook <= 0: cook = total_time - prep if total_time > prep else 20

        formatted.append({
            "name": r.get("title"),
            "type": "dinner",
            "diet": "vegetarian" if is_vegetarian(r) else "non-vegetarian",
            "ingredients": [f"{i['original']}" for i in r.get("extendedIngredients", [])],
            "image": r.get("image"),
            "prep_time": prep,
            "cook_time": cook,
            "instructions": instruction_list  # Now a list of strings!
        })
    return formatted


def append_recipes(total_to_add, batch_size):
    all_recipes = []

    # LOAD EXISTING DATA (So we don't delete it)
    if os.path.exists("recipes.json"):
        with open("recipes.json", "r") as f:
            try:
                all_recipes = json.load(f)
                print(f"Loaded {len(all_recipes)} existing recipes.")
            except:
                print("Fresh start.")

    added = 0
    while added < total_to_add:
        current_batch = min(batch_size, total_to_add - added)
        raw = fetch_recipes(current_batch)
        if not raw: break

        formatted = format_recipes(raw)
        all_recipes.extend(formatted)

        # SAVE EVERYTHING BACK
        with open("recipes.json", "w") as f:
            json.dump(all_recipes, f, indent=4)

        added += len(formatted)
        print(f"Progress: {added}/{total_to_add} added.")
        time.sleep(1)  # Be nice to the API


if __name__ == "__main__":
    append_recipes(10, 5)  # Adds 10 more recipes to your current file