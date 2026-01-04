import requests
import os
from dotenv import load_dotenv
import json
import time

# Load environment variables
load_dotenv()

# Get the Spoonacular API key from .env
API_KEY = os.getenv('SPOONACULAR_API_KEY')

# Function to fetch recipes from the Spoonacular API
def fetch_recipes(number):
    url = f"https://api.spoonacular.com/recipes/random?apiKey={API_KEY}&number={number}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json().get('recipes', [])
    else:
        print("Error fetching recipes:", response.content)
        return []

# Function to determine if a recipe is vegetarian
def is_vegetarian(recipe):
    non_vegetarian_ingredients = [
        "chicken", "egg", "fish", "beef", "pork", "sausage", "lamb", "ham", "bacon", "duck", "shrimp", "meat"
    ]
    for ingredient in recipe.get("extendedIngredients", []):
        ingredient_name = ingredient["name"].lower()
        if any(non_veg in ingredient_name for non_veg in non_vegetarian_ingredients):
            return False
    if "vegetarian" in recipe.get("diets", []):
        return True
    return False

# Function to format recipes for storage
def format_recipes(recipes):
    formatted = []
    for recipe in recipes:
        # Format ingredient amounts and units properly
        ingredients = []
        for ingredient in recipe.get("extendedIngredients", []):
            amount = ingredient.get("amount", 0)
            unit = ingredient.get("unit", "").strip()
            ingredients.append(f"{amount} {unit} of {ingredient['name']}")

        # Clean cooking instructions for better readability
        instructions = recipe.get("instructions", "No instructions available.")
        if instructions.startswith("<ol>"):
            instructions = instructions.replace("<ol>", "").replace("</ol>", "").replace("<li>", "- ").replace("</li>", "")

        formatted.append({
            "name": recipe.get("title", "No title"),
            "type": "dinner",
            "diet": "vegetarian" if is_vegetarian(recipe) else "non-vegetarian",
            "ingredients": ingredients,
            "image": recipe.get("image", "No image available"),
            "prep_time": recipe.get("preparationMinutes", 0),
            "cook_time": recipe.get("cookingMinutes", 0),
            "instructions": instructions
        })
    return formatted

# Function to save recipes to file
def save_recipes_to_file(total_recipes, batch_size):
    all_recipes = []

    try:
        with open("recipes.json", "r") as f:
            existing_recipes = json.load(f)
            all_recipes.extend(existing_recipes)
    except (json.JSONDecodeError, FileNotFoundError):
        print("No existing recipes found. Starting fresh.")

    remaining = total_recipes - len(all_recipes)

    while remaining > 0:
        batch_size = min(batch_size, remaining)
        recipes = fetch_recipes(batch_size)
        formatted_recipes = format_recipes(recipes)
        all_recipes.extend(formatted_recipes)

        with open("recipes.json", "w") as f:
            json.dump(all_recipes, f, indent=4)

        remaining -= len(formatted_recipes)
        print(f"Fetched {len(formatted_recipes)} recipes. Remaining: {remaining}.")
        time.sleep(2)

if __name__ == "__main__":
    TOTAL_RECIPES = 100  # Total number of recipes to fetch
    BATCH_SIZE = 20
    save_recipes_to_file(TOTAL_RECIPES, BATCH_SIZE)
    print("Recipes saved to recipes.json")