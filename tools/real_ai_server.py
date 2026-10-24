"""Food recognition and the unified, persistent nutrition website."""
from __future__ import annotations

import argparse
import getpass
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from nutrition_web import AppState, AiRequestHandler, ROOT, Store

DEFAULT_MODEL = "openai/clip-vit-base-patch32"


def food_prompt(food):
    prompt = f"a clear photo of {food['food']} food on a plate"
    note = food.get("note", "").strip()
    return f"{prompt}. {note}" if note else prompt


class FoodClassifier:
    def __init__(self, foods, model_id, confidence_threshold, margin_threshold):
        # Lazy imports keep manual website mode independent of PyTorch.
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.lock = threading.RLock()
        self.confidence_threshold = confidence_threshold
        self.margin_threshold = margin_threshold
        self.replace_foods(foods)
        print(f"Loading real AI model: {model_id}")
        print("First startup may take several minutes while the model downloads.")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = CLIPProcessor.from_pretrained(model_id)
        self.model = CLIPModel.from_pretrained(model_id).to(self.device)
        self.model.eval()
        print(f"AI ready with {len(foods)} candidate food classes on {self.device.type.upper()}.")

    def replace_foods(self, foods):
        if len(foods) < 2:
            raise ValueError("At least two food classes are required")
        with self.lock:
            self.foods = {food["food"]: dict(food) for food in foods}

    def classify(self, image):
        with self.lock, self.torch.inference_mode():
            labels = list(self.foods)
            prompts = [food_prompt(self.foods[label]) for label in labels]
            inputs = self.processor(text=prompts, images=image.convert("RGB"),
                                    return_tensors="pt", padding=True, truncation=True,
                                    max_length=self.model.config.text_config.max_position_embeddings)
            inputs = {name: value.to(self.device) for name, value in inputs.items()}
            logits = self.model(**inputs).logits_per_image[0]
            probabilities = logits.softmax(dim=0).cpu().tolist()
            ranked = sorted(zip(labels, probabilities), key=lambda item: item[1], reverse=True)
            label, confidence = ranked[0]
            margin = confidence - ranked[1][1]
            return {"accepted": confidence >= self.confidence_threshold and margin >= self.margin_threshold,
                    "food": label, "calorie_per_gram": self.foods[label]["calorie_per_gram"],
                    "confidence": round(confidence, 4), "margin": round(margin, 4),
                    "top_predictions": [{"food": name, "confidence": round(score, 4)} for name, score in ranked[:3]]}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--foods", type=Path, default=ROOT / "data" / "food_calories.csv")
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "nutrition.sqlite3")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--margin", type=float, default=0.08)
    parser.add_argument("--scale-url", default=os.environ.get("FOOD_SCALE_URL", ""),
                        help="ESP32 origin, e.g. http://192.168.1.50 (without /api/status)")
    parser.add_argument("--web-only", action="store_true", help="Manual website without loading AI")
    parser.add_argument("--cloud-config", type=Path, default=ROOT / "data" / "cloud-bridge.local.json")
    parser.add_argument("--no-cloud", action="store_true", help="Run the local website without cloud synchronization")
    return parser.parse_args()


def main():
    args = parse_args()
    if not 0 <= args.confidence <= 1 or not 0 <= args.margin <= 1:
        raise SystemExit("Confidence and margin must be between 0 and 1")
    if args.scale_url:
        from urllib.parse import urlparse
        parsed = urlparse(args.scale_url)
        if parsed.scheme != "http" or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
            raise SystemExit("--scale-url must be an HTTP origin, e.g. http://192.168.1.50")
    store = Store(args.database, args.foods)
    password = os.environ.get("FOOD_ADMIN_PASSWORD")
    if password is None and store.credentials() is None:
        password = getpass.getpass("Tetapkan kata laluan pentadbir website (minimum 8 aksara): ")
        if password != getpass.getpass("Ulang kata laluan: "):
            raise SystemExit("Kata laluan tidak sama")
    if password is not None and not 8 <= len(password) <= 1024:
        raise SystemExit("Kata laluan mesti 8 hingga 1024 aksara")
    classifier = None if args.web_only else FoodClassifier(store.foods(), args.model, args.confidence, args.margin)
    state = AppState(classifier, store, password, args.scale_url)
    server = ThreadingHTTPServer((args.host, args.port), AiRequestHandler)
    server.app_state = state
    poller = threading.Thread(target=state.poll_scale, daemon=True)
    bridge = None
    if not args.no_cloud and args.cloud_config.exists():
        from cloud_bridge import CloudBridge
        bridge = CloudBridge(state, args.cloud_config)
    if args.scale_url:
        poller.start()
    if bridge:
        bridge.thread.start()
    print(f"Website: http://127.0.0.1:{args.port}/", flush=True)
    print(f"Database: {args.database}", flush=True)
    print("Web sahaja: AI tidak dimuatkan." if args.web_only else "AI + website sedia.", flush=True)
    print("Tekan Ctrl+C untuk berhenti.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop.set()
        if poller.is_alive():
            poller.join(timeout=4)
        if bridge:
            bridge.thread.join(timeout=25)
        server.server_close()
        with store.lock:
            store.db.close()


if __name__ == "__main__":
    main()
