"""Download and validate the food classification model during first-time setup."""

from real_ai_server import DEFAULT_FOOD_CSV, DEFAULT_MODEL, FoodClassifier, load_foods


def main() -> None:
    foods = load_foods(DEFAULT_FOOD_CSV)
    FoodClassifier(
        foods,
        model_id=DEFAULT_MODEL,
        confidence_threshold=0.35,
        margin_threshold=0.08,
    )
    print("AI model cache is ready.")


if __name__ == "__main__":
    main()
