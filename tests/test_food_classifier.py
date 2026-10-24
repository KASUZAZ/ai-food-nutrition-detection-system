"""Check catalog prompts through the inference path without downloading models."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import sys
import threading
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from real_ai_server import FoodClassifier, food_prompt


class FoodClassifierTests(unittest.TestCase):
    def test_optional_notes_keep_the_food_name_and_strip_whitespace(self):
        self.assertEqual(food_prompt({"food": "Rice"}), "a clear photo of Rice food on a plate")
        self.assertEqual(food_prompt({"food": "Rice", "note": "  "}), food_prompt({"food": "Rice"}))
        self.assertEqual(food_prompt({"food": "Rice", "note": "  steamed white rice  "}),
                         "a clear photo of Rice food on a plate. steamed white rice")

    def test_inference_uses_updated_notes_and_limits_long_text_to_model_context(self):
        classifier = FoodClassifier.__new__(FoodClassifier)
        classifier.lock = threading.RLock()
        classifier.torch = SimpleNamespace(inference_mode=nullcontext)
        classifier.device = "cpu"
        classifier.confidence_threshold = .35
        classifier.margin_threshold = .08
        classifier.processor = Mock(return_value={})
        logits = Mock()
        logits.softmax.return_value.cpu.return_value.tolist.return_value = [.9, .1]
        classifier.model = Mock(return_value=SimpleNamespace(logits_per_image=[logits]))
        classifier.model.config = SimpleNamespace(text_config=SimpleNamespace(max_position_embeddings=77))
        foods = [{"food": "Nasi lemak", "calorie_per_gram": 2.2, "note": "Coconut rice with sambal"},
                 {"food": "Apple", "calorie_per_gram": .52, "note": "Fresh apple"}]
        classifier.replace_foods(foods)
        result = classifier.classify(Mock())
        self.assertTrue(result["accepted"])
        self.assertEqual(result["food"], "Nasi lemak")
        self.assertIn("Coconut rice with sambal", classifier.processor.call_args.kwargs["text"][0])
        foods[0]["note"] = "Steamed coconut rice " * 25
        foods[0]["calorie_per_gram"] = 2.5
        classifier.replace_foods(foods)
        result = classifier.classify(Mock())
        options = classifier.processor.call_args.kwargs
        self.assertIn(foods[0]["note"].strip(), options["text"][0])
        self.assertNotIn("sambal", options["text"][0])
        self.assertTrue(options["truncation"])
        self.assertEqual(options["max_length"], 77)
        self.assertEqual(result["calorie_per_gram"], 2.5)


if __name__ == "__main__":
    unittest.main()
