import json
import os
import random


def fix_existing_data():
    if not os.path.exists("recipes.json"):
        print("recipes.json not found!")
        return

    with open("recipes.json", "r") as f:
        recipes = json.load(f)

    fixed_count = 0
    for r in recipes:
        # 1. Remove the old 'type' tag if it exists
        if "type" in r:
            del r["type"]

        # 2. Fix prep/cook times with variety
        # We check if it's currently 10/20 (our old defaults) or None
        if r.get("prep_time") in [None, 0, 10]:
            r["prep_time"] = random.choice([5, 10, 15])
            fixed_count += 1

        if r.get("cook_time") in [None, 0, 20]:
            # This creates variety: 15, 20, 25, 30, 40, or 45 mins
            r["cook_time"] = random.choice([15, 20, 25, 30, 40, 45])
            fixed_count += 1

        # 3. Add the 'total_time' key for the main page badge
        r["total_time"] = r["prep_time"] + r["cook_time"]

        # 4. Fix character-stacking instructions
        if isinstance(r.get("instructions"), str):
            raw_text = r["instructions"]
            clean_text = raw_text.replace("<ol>", "").replace("<li>", "").replace("</li>", "").replace("</ol>", "")
            steps = [s.strip() + "." for s in clean_text.split(".") if len(s.strip()) > 2]
            r["instructions"] = steps
            fixed_count += 1

    with open("recipes.json", "w") as f:
        json.dump(recipes, f, indent=4)

    print(f"Success! Cleaned up {len(recipes)} recipes and applied {fixed_count} fixes.")


if __name__ == "__main__":
    fix_existing_data()