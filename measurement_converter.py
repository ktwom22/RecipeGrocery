import json
from fractions import Fraction
import re

# Conversion table for metric to imperial units
CONVERSION_TABLE = {
    "ml": {"factor": 0.033814, "to": "fl oz"},  # 1 ml = 0.033814 fluid ounces
    "liter": {"factor": 4.22675, "to": "cups"},  # 1 liter = 4.22675 cups
    "g": {"factor": 0.035274, "to": "oz"},  # 1 gram = 0.035274 ounces
    "kg": {"factor": 2.20462, "to": "lb"},  # 1 kg = 2.20462 lbs
    "tbsp": {"factor": 1, "to": "tbsp"},  # Standardize tablespoons
    "tsp": {"factor": 1, "to": "tsp"},  # Standardize teaspoons
    "cup": {"factor": 1, "to": "cup"},  # Standardize cups
    "oz": {"factor": 1, "to": "oz"},  # Standardize ounces
    "lb": {"factor": 1, "to": "lb"},  # Standardize pounds
}

# List of ignored/common ingredients for tags generation
IGNORED_INGREDIENTS = {
    "salt", "pepper", "flour", "sugar", "butter", "oil", "water", "milk", "egg", "eggs",
    "vanilla", "yeast", "baking soda", "baking powder", "cream", "parsley", "stock",
    "broth", "spices", "olive oil", "garlic", "panko", "onion", "green onions",
    "half and half", "carrots", "spinach",
}

# Convert amounts to fractions when possible
def convert_to_fraction(amount, max_denominator=16):
    try:
        # Convert float amount to a fraction with limited denominator
        fraction = Fraction(amount).limit_denominator(max_denominator)

        # Handle whole numbers
        if fraction.denominator == 1:
            return str(fraction.numerator)

        # Handle mixed fractions (e.g., 4/3 → 1 1/3)
        if fraction.numerator > fraction.denominator:
            whole_number = fraction.numerator // fraction.denominator
            remainder = fraction.numerator % fraction.denominator
            if remainder == 0:
                return str(whole_number)
            return f"{whole_number} {Fraction(remainder, fraction.denominator)}"

        # Return proper fraction (e.g., 2/3)
        return str(fraction)
    except (ValueError, ZeroDivisionError):
        # If conversion fails, fallback to the original amount
        return str(amount)

# Standardize ingredients and convert to imperial units
def standardize_ingredient(ingredient):
    # Split ingredient into amount, unit, and name
    parts = ingredient.split(" ", 2)
    if len(parts) < 3:
        return ingredient  # Return as is if the format is invalid

    try:
        amount = eval(parts[0])  # Use eval for handling strings like "3/2"
    except (ValueError, SyntaxError):
        return ingredient  # Skip invalid amounts

    unit = parts[1].strip().lower()  # Extract and clean the unit
    name = parts[2].strip()  # Extract the core ingredient name

    # Clean redundant terms like "of of"
    name = re.sub(r"\bof\b", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip()

    # Convert the amount to fractions
    formatted_amount = convert_to_fraction(amount)

    # Return the standardized ingredient with fractional amounts
    return f"{formatted_amount} {unit} {name}"

# Generate clean tags for ingredients
def generate_tags(ingredients):
    tags = set()  # Use a set to ensure tags are unique
    for ingredient in ingredients:
        # Extract name only, skipping amount and unit
        _, _, name = ingredient.partition(" ")
        name = name.strip().lower()

        # Remove ignored/common ingredients
        if any(ignored in name for ignored in IGNORED_INGREDIENTS):
            continue

        # Clean the name
        name = re.sub(r"[^\w\s]", "", name).strip()

        if name:  # Add valid names to the tags
            tags.add(name)

    return sorted(tags)

# Load recipes from a JSON file
def load_recipes(file_path):
    with open(file_path, "r") as file:
        return json.load(file)

# Save recipes back to a JSON file
def save_recipes(file_path, recipes):
    with open(file_path, "w") as file:
        json.dump(recipes, file, indent=4)

# Process recipes to standardize ingredients and generate tags
def process_recipes(file_path):
    # Load recipe data
    recipes = load_recipes(file_path)

    for recipe in recipes:
        # Standardize ingredients
        standardized_ingredients = [
            standardize_ingredient(ingredient) for ingredient in recipe["ingredients"]
        ]
        recipe["ingredients"] = standardized_ingredients

        # Generate unique tags for non-ignored ingredients
        recipe["tags"] = generate_tags(standardized_ingredients)

    # Save the updated recipes
    save_recipes(file_path, recipes)
    print(f"Processed recipes saved to {file_path}.")

# Main function
if __name__ == "__main__":
    # Define path for JSON file
    JSON_FILE = "recipes.json"

    # Process recipes file
    process_recipes(JSON_FILE)