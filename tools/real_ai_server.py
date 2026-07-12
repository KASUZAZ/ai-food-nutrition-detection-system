"""Real food image classification server for ESP32-CAM.

The first startup downloads the CLIP model. Later startups use the local cache.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import torch
from PIL import Image, UnidentifiedImageError
from transformers import CLIPModel, CLIPProcessor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOOD_CSV = PROJECT_ROOT / "data" / "food_calories.csv"
DEFAULT_MODEL = "openai/clip-vit-base-patch32"
MAX_IMAGE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FoodInfo:
    name: str
    calorie_per_gram: float
    note: str


class FoodClassifier:
    def __init__(
        self,
        foods: list[FoodInfo],
        model_id: str,
        confidence_threshold: float,
        margin_threshold: float,
    ) -> None:
        if len(foods) < 2:
            raise ValueError("food_calories.csv must contain at least two foods")

        self.foods = {food.name: food for food in foods}
        self.confidence_threshold = confidence_threshold
        self.margin_threshold = margin_threshold
        self.lock = threading.Lock()

        print(f"Loading real AI model: {model_id}")
        print("First startup may take several minutes while the model downloads.")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = CLIPProcessor.from_pretrained(model_id)
        self.model = CLIPModel.from_pretrained(model_id).to(self.device)
        self.model.eval()
        print(
            f"AI ready with {len(foods)} candidate food classes "
            f"on {self.device.type.upper()}."
        )

    def classify(self, image: Image.Image) -> dict[str, Any]:
        labels = list(self.foods)
        prompts = [f"a clear photo of {label} food on a plate" for label in labels]
        inputs = self.processor(
            text=prompts,
            images=image.convert("RGB"),
            return_tensors="pt",
            padding=True,
        )
        inputs = {name: value.to(self.device) for name, value in inputs.items()}

        with self.lock, torch.inference_mode():
            logits = self.model(**inputs).logits_per_image[0]
            probabilities = logits.softmax(dim=0).cpu()

        ranked = sorted(
            zip(labels, probabilities.tolist()),
            key=lambda item: item[1],
            reverse=True,
        )
        top_label, confidence = ranked[0]
        margin = confidence - ranked[1][1]
        accepted = (
            confidence >= self.confidence_threshold
            and margin >= self.margin_threshold
        )
        food = self.foods[top_label]

        return {
            "accepted": accepted,
            "food": food.name,
            "calorie_per_gram": food.calorie_per_gram,
            "confidence": round(confidence, 4),
            "margin": round(margin, 4),
            "top_predictions": [
                {"food": label, "confidence": round(score, 4)}
                for label, score in ranked[:3]
            ],
        }


class AppState:
    def __init__(self, classifier: FoodClassifier) -> None:
        self.classifier = classifier
        self.lock = threading.Lock()
        self.last_image: bytes | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_detection_at: str | None = None

    def update(self, image_bytes: bytes, result: dict[str, Any]) -> None:
        with self.lock:
            self.last_image = image_bytes
            self.last_result = result
            self.last_detection_at = time.strftime("%Y-%m-%d %H:%M:%S")


def load_foods(path: Path) -> list[FoodInfo]:
    foods: list[FoodInfo] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            name = (row.get("food") or "").strip()
            if not name:
                continue
            foods.append(
                FoodInfo(
                    name=name,
                    calorie_per_gram=float(row["calorie_per_gram"]),
                    note=(row.get("note") or "").strip(),
                )
            )
    return foods


class AiRequestHandler(BaseHTTPRequestHandler):
    server_version = "FoodNutritionAI/1.0"

    @property
    def state(self) -> AppState:
        return self.server.app_state  # type: ignore[attr-defined]

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "model_ready": True})
            return
        if path == "/latest.jpg":
            self.send_latest_image()
            return
        if path == "/api/latest":
            with self.state.lock:
                payload = {
                    "detected_at": self.state.last_detection_at,
                    "result": self.state.last_result,
                }
            self.send_json(HTTPStatus.OK, payload)
            return
        if path == "/":
            self.send_dashboard()
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/classify":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type != "image/jpeg":
            self.send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type must be image/jpeg"},
            )
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_IMAGE_BYTES:
            self.send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "JPEG must be between 1 byte and 2 MB"},
            )
            return

        image_bytes = self.rfile.read(length)
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
        except (UnidentifiedImageError, OSError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JPEG image"})
            return

        started = time.perf_counter()
        result = self.state.classifier.classify(image)
        result["inference_ms"] = round((time.perf_counter() - started) * 1000)
        self.state.update(image_bytes, result)

        print(
            f"Detection: {result['food']} "
            f"confidence={result['confidence']:.3f} accepted={result['accepted']}"
        )
        if not result["accepted"]:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "food confidence too low", **result},
            )
            return
        self.send_json(HTTPStatus.OK, result)

    def send_latest_image(self) -> None:
        with self.state.lock:
            image_bytes = self.state.last_image
        if image_bytes is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "no image received yet"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(image_bytes)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(image_bytes)

    def send_dashboard(self) -> None:
        with self.state.lock:
            result = self.state.last_result
            detected_at = self.state.last_detection_at

        food = html.escape(str(result["food"])) if result else "Waiting for camera"
        confidence = f"{float(result['confidence']) * 100:.1f}%" if result else "-"
        calorie_rate = (
            f"{float(result['calorie_per_gram']):.2f} kcal/g" if result else "-"
        )
        status = "Accepted" if result and result["accepted"] else "Waiting / rejected"
        image = (
            '<img src="/latest.jpg?t=' + str(int(time.time())) + '" alt="Latest food">'
            if result
            else '<div class="empty">No ESP32-CAM image received</div>'
        )
        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5"><title>Food Nutrition AI</title>
<style>
body{{margin:0;font:16px Arial,sans-serif;background:#f4f6f8;color:#182026}}main{{max-width:880px;margin:auto;padding:28px}}
header{{display:flex;justify-content:space-between;align-items:center;gap:16px;border-bottom:3px solid #15966f;padding-bottom:16px}}
h1{{font-size:25px;margin:0}}.live{{color:#087a5a;font-weight:700}}.grid{{display:grid;grid-template-columns:1.5fr 1fr;gap:20px;margin-top:22px}}
.panel{{background:white;border:1px solid #d9e0e5;border-radius:8px;padding:18px}}img,.empty{{width:100%;aspect-ratio:4/3;object-fit:cover;background:#e8ecef;display:grid;place-items:center}}
.metric{{border-bottom:1px solid #e4e8eb;padding:14px 0}}.label{{color:#62727d;font-size:13px}}.value{{font-size:23px;font-weight:700;margin-top:4px}}
@media(max-width:650px){{main{{padding:14px}}header{{display:block}}h1{{font-size:21px}}.live{{display:block;font-size:12px;margin-top:8px}}.grid{{grid-template-columns:1fr;gap:12px;margin-top:14px}}.panel{{padding:12px}}.value{{font-size:20px}}}}
</style></head><body><main><header><h1>AI Food Nutrition System</h1><span class="live">AI ONLINE</span></header>
<section class="grid"><div class="panel">{image}</div><div class="panel">
<div class="metric"><div class="label">Detected food</div><div class="value">{food}</div></div>
<div class="metric"><div class="label">AI confidence</div><div class="value">{confidence}</div></div>
<div class="metric"><div class="label">Energy rate</div><div class="value">{calorie_rate}</div></div>
<div class="metric"><div class="label">Decision</div><div class="value">{status}</div></div>
<div class="metric"><div class="label">Last detection</div><div>{html.escape(detected_at or '-')}</div></div>
</div></section></main></body></html>"""
        body = page.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real AI server for ESP32-CAM")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--foods", type=Path, default=DEFAULT_FOOD_CSV)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--margin", type=float, default=0.08)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    foods = load_foods(args.foods)
    classifier = FoodClassifier(
        foods,
        model_id=args.model,
        confidence_threshold=args.confidence,
        margin_threshold=args.margin,
    )
    server = ThreadingHTTPServer((args.host, args.port), AiRequestHandler)
    server.app_state = AppState(classifier)  # type: ignore[attr-defined]
    print(f"Server: http://{args.host}:{args.port}")
    print(f"Dashboard: http://127.0.0.1:{args.port}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAI server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
