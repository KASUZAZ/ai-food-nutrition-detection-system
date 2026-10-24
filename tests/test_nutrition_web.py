"""HTTP/database contract tests; sensor and classifier doubles stay in tests only."""
import base64
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from nutrition_web import AppState, AiRequestHandler, ROOT, Store
from cloud_bridge import CloudBridge
from real_ai_server import food_prompt
from PIL import Image


class ClassifierDouble:
    def replace_foods(self, foods):
        self.foods = foods

    def classify(self, image):
        return {"accepted": True, "food": "Rice", "calorie_per_gram": 1.3,
                "confidence": .9, "margin": .8, "top_predictions": []}


class WebsiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.store = Store(self.path, ROOT / "data/food_calories.csv")
        self.classifier = ClassifierDouble()
        self.state = AppState(self.classifier, self.store, "test-password")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), AiRequestHandler)
        self.server.app_state = self.state
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.cookie = ""
        image = io.BytesIO()
        Image.new("RGB", (20, 20), (50, 130, 70)).save(image, format="JPEG")
        self.image = image.getvalue()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.store.db.close()
        self.temp.cleanup()

    def request(self, path, method="GET", data=None, headers=None, raw=None):
        head = {"Cookie": self.cookie}
        if data is not None:
            head["Content-Type"] = "application/json"
            raw = json.dumps(data).encode()
        head.update(headers or {})
        req = Request(self.url + path, data=raw, method=method, headers=head)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            if "application/json" in response.headers.get("Content-Type", ""):
                body = json.loads(body)
            return response.status, body, response.headers

    def login(self):
        status, _, headers = self.request("/api/login", "POST", {"password": "test-password"})
        self.assertEqual(status, 200)
        self.assertNotIn("Max-Age", headers["Set-Cookie"])
        self.assertNotIn("Expires", headers["Set-Cookie"])
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]

    def meal(self, **values):
        return {"food": "Rice", "weight_g": 150, "calories": 195,
                "eaten_at": "2026-10-23T20:56:00+08:00", **values}

    def scale(self, **values):
        return {"food": "Rice", "weight_g": 150, "locked": True, "sensor_ready": True,
                "measurement_id": "boot-a-1", "detection_id": "photo-1", **values}

    def detection(self, **values):
        result = {"accepted": True, "food": "Rice", "calorie_per_gram": 1.3,
                  "confidence": .9, "detection_id": "photo-1", **values}
        self.state.detection(self.image, result, "boot-a-1")

    def test_anonymous_reads_but_cannot_write(self):
        for path in ("/", "/app.js", "/styles.css", "/api/live", "/api/meals", "/api/foods"):
            self.assertEqual(self.request(path)[0], 200, path)
        for path in ("/api/meals", "/api/foods", "/api/capture", "/api/tare"):
            self.assertEqual(self.request(path, "POST", {})[0], 401, path)
        self.assertEqual(self.request("/api/meals/1", "PUT", self.meal())[0], 401)

    def test_login_throttle_cookie_logout_and_no_timeout(self):
        for _ in range(5):
            self.assertEqual(self.request("/api/login", "POST", {"password":"wrong"})[0], 401)
        self.assertEqual(self.request("/api/login", "POST", {"password":"test-password"})[0], 429)
        self.state.attempts.clear()
        self.login()
        self.assertTrue(self.request("/api/session")[1]["authenticated"])
        self.assertEqual(self.request("/api/logout", "POST", {})[0], 200)
        self.assertFalse(self.request("/api/session")[1]["authenticated"])
        self.login()
        token = self.cookie.split("=", 1)[1]
        with patch("nutrition_web.time.monotonic", return_value=time.monotonic() + 7 * 86400):
            self.assertTrue(self.state.authenticated(token))
        self.assertEqual(self.request("/api/meals", "POST", self.meal())[0], 201)
        restarted = AppState(self.classifier, self.store)
        self.assertFalse(restarted.authenticated(token))

    def test_changed_password_persists_and_old_password_fails(self):
        self.store.set_password("replacement-password")
        second = Store(self.path, ROOT / "data/food_calories.csv")
        try:
            restarted = AppState(self.classifier, second)
            self.assertEqual(restarted.login("test-password", "test-client")[1], 401)
            self.assertEqual(restarted.login("replacement-password", "test-client")[1], 200)
            self.assertNotIn(b"replacement-password", self.path.read_bytes())
        finally:
            second.db.close()

    def test_manual_create_edit_and_image_survives_restart(self):
        self.login()
        meal = self.meal(image_base64=base64.b64encode(self.image).decode())
        status, result, _ = self.request("/api/meals", "POST", meal)
        self.assertEqual(status, 201)
        ident = result["id"]
        self.assertEqual(self.request(f"/api/meals/{ident}/image")[0], 200)
        self.assertEqual(self.request(f"/api/meals/{ident}", "PUT", self.meal(food="Egg", calories=232.5))[0], 200)
        self.assertIsNotNone(self.store.meal_image(ident))
        second = Store(self.path, ROOT / "data/food_calories.csv")
        try:
            self.assertEqual(second.meals()[0]["food"], "Egg")
            self.assertEqual(second.meals()[0]["calories"], 232.5)
            self.assertIsNotNone(second.meal_image(ident))
        finally:
            second.db.close()

    def test_catalog_live_update_and_duplicate(self):
        self.login()
        data = {"food":"Nasi lemak", "calories_per_100g": 220, "note":"Santan"}
        self.assertEqual(self.request("/api/foods", "POST", data)[0], 201)
        saved = next(f for f in self.classifier.foods if f["food"] == "Nasi lemak")
        self.assertAlmostEqual(saved["calorie_per_gram"], 2.2)
        self.assertIn("Santan", food_prompt(saved))
        self.assertEqual(self.request("/api/foods", "POST", data)[0], 409)
        data["calories_per_100g"] = 250
        data["note"] = "Coconut rice with sambal and peanuts"
        self.assertEqual(self.request(f"/api/foods/{saved['id']}", "PUT", data)[0], 200)
        updated = next(f for f in self.classifier.foods if f["id"] == saved["id"])
        self.assertEqual(updated["calorie_per_gram"], 2.5)
        self.assertIn(data["note"], food_prompt(updated))
        self.assertEqual(self.request("/api/foods/99999", "PUT", data)[0], 404)

    def test_cloud_catalog_notes_reach_ai_and_refresh_when_edited(self):
        bridge = self.make_bridge()
        foods = self.store.foods()
        foods[0]["note"] = "Fresh red apple with skin"
        bridge.update_catalog(foods)
        self.assertIn(foods[0]["note"], food_prompt(self.classifier.foods[0]))
        foods[0]["note"] = "Sliced green apple with skin"
        bridge.update_catalog(foods)
        self.assertIn(foods[0]["note"], food_prompt(self.classifier.foods[0]))
        self.assertNotIn("Fresh red", food_prompt(self.classifier.foods[0]))

    def test_sensor_saves_once_per_placement_across_restart(self):
        self.detection()
        for _ in range(3):
            self.state.accept_scale(self.scale())
        self.assertEqual(len(self.store.meals()), 1)
        self.assertEqual(self.store.meals()[0]["source"], "sensor")
        self.assertEqual(self.store.meals()[0]["calories"], 195)
        self.assertEqual(self.store.meal_image(1), self.image)
        second = AppState(self.classifier, self.store, "test-password")
        second.detection(self.image, self.state.last_result, "boot-a-1")
        second.accept_scale(self.scale())
        self.assertEqual(len(self.store.meals()), 1)
        second.detection(self.image, self.state.last_result, "boot-a-2")
        second.accept_scale(self.scale(measurement_id="boot-a-2"))
        self.assertEqual(len(self.store.meals()), 2)

    def test_sensor_rejects_old_photos_unstable_empty_and_unhealthy(self):
        self.detection()
        for changes in ({"detection_id":"old"}, {"measurement_id":"boot-a-2"},
                        {"locked":False}, {"weight_g":0}, {"sensor_ready":False}):
            self.state.accept_scale(self.scale(**changes))
        self.assertEqual(self.store.meals(), [])
        self.detection(accepted=False)
        self.state.accept_scale(self.scale())
        self.assertEqual(self.store.meals(), [])

    def test_classification_to_sensor_history_and_saved_photo(self):
        self.state.accept_scale(self.scale(detection_id=""))
        status, result, _ = self.request("/classify", "POST", raw=self.image, headers={"Content-Type":"image/jpeg"})
        self.assertEqual(status, 200)
        self.assertTrue(result["accepted"])
        self.state.accept_scale(self.scale(detection_id=result["detection_id"]))
        records = self.request("/api/meals")[1]["meals"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["calories"], 195)
        self.assertEqual(self.request(records[0]["image_url"])[0], 200)

    def test_validation_timezone_missing_record_and_origin(self):
        self.login()
        for changes in ({"weight_g":-1}, {"weight_g":0}, {"weight_g":True},
                        {"calories":float("nan")}, {"calories":float("inf")},
                        {"eaten_at":"invalid"}, {"food":""}, {"image_base64":"bad image"}):
            self.assertEqual(self.request("/api/meals", "POST", self.meal(**changes))[0], 400, changes)
        self.assertEqual(self.request("/api/meals/9999", "PUT", self.meal())[0], 404)
        self.assertEqual(self.request("/api/meals", "POST", self.meal(), {"Origin":"https://evil.example"})[0], 403)
        self.request("/api/meals", "POST", self.meal(eaten_at="2026-10-23T16:56:00Z"))
        self.assertEqual(self.store.meals()[0]["eaten_at"], "2026-10-24T00:56:00+08:00")

    def test_invalid_jpeg_web_only_and_offline(self):
        self.assertEqual(self.request("/classify", "POST", raw=b"invalid", headers={"Content-Type":"image/jpeg"})[0], 400)
        self.state.classifier = None
        self.assertEqual(self.request("/classify", "POST", raw=self.image, headers={"Content-Type":"image/jpeg"})[0], 503)
        self.assertFalse(self.request("/health")[1]["model_ready"])
        self.state.accept_scale(self.scale())
        self.state.scale_seen = time.monotonic() - 10
        self.assertFalse(self.request("/api/live")[1]["scale_online"])

    def test_scale_bridge_http_and_protected_controls(self):
        device_data = self.scale()
        calls = []

        class ScaleDouble(BaseHTTPRequestHandler):
            def do_GET(inner):
                raw = json.dumps(device_data).encode()
                inner.send_response(200)
                inner.send_header("Content-Length", str(len(raw)))
                inner.end_headers()
                inner.wfile.write(raw)

            def do_POST(inner):
                calls.append(inner.path)
                raw = b'{"ok":true,"message":"command queued"}'
                inner.send_response(202)
                inner.send_header("Content-Length", str(len(raw)))
                inner.end_headers()
                inner.wfile.write(raw)

            def log_message(inner, *_):
                pass

        device = ThreadingHTTPServer(("127.0.0.1", 0), ScaleDouble)
        thread = threading.Thread(target=device.serve_forever, daemon=True)
        thread.start()
        try:
            self.state.scale_url = f"http://127.0.0.1:{device.server_port}"
            self.detection()
            self.state.accept_scale(self.state.device_request("/api/status"))
            self.assertEqual(self.request("/api/live")[1]["scale"]["weight_g"], 150)
            self.assertEqual(len(self.request("/api/meals")[1]["meals"]), 1)
            self.assertEqual(self.request("/api/capture", "POST", {})[0], 401)
            self.assertEqual(calls, [])
            self.login()
            self.assertEqual(self.request("/api/capture", "POST", {})[0], 200)
            self.assertEqual(self.request("/api/tare", "POST", {})[0], 200)
            self.assertEqual(calls, ["/api/capture", "/api/tare"])
        finally:
            device.shutdown()
            thread.join()
            device.server_close()

    def make_bridge(self):
        config = Path(self.temp.name) / "bridge.json"
        config.write_text(json.dumps({"url":"https://example.test", "token":"x" * 48, "device_id":"test-device"}))
        return CloudBridge(self.state, config)

    def test_cloud_outbox_retries_and_does_not_repeat_uploaded_meals(self):
        bridge = self.make_bridge()
        self.store.save_meal(self.meal(), image=self.image, source="sensor", event_key="placement-1")
        calls = []
        fail_upload = True
        def cloud_request(path, payload):
            nonlocal fail_upload
            calls.append(path)
            if path.endswith("/sync"):
                return {"ok":True,"foods":self.store.foods(),"commands":[],"acknowledged_commands":[]}
            if fail_upload:
                fail_upload = False
                raise OSError("connection lost")
            self.assertEqual(payload["event_key"], "test-device:placement-1")
            return {"ok":True,"id":1}
        bridge.request = cloud_request
        with self.assertRaises(OSError):
            bridge.sync_once()
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM cloud_sent").fetchone()[0], 0)
        bridge.sync_once()
        bridge.sync_once()
        self.assertEqual(calls.count("/api/device/meal"), 2)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM cloud_sent").fetchone()[0], 1)

    def test_cloud_command_journal_prevents_repeated_tare(self):
        bridge = self.make_bridge()
        calls = []
        self.state.device_request = lambda path, method: calls.append(path) or {"ok":True}
        command = {"id":"test-command", "action":"tare", "created_at":self.meal()["eaten_at"]}
        from nutrition_web import now_iso
        command["created_at"] = now_iso()
        bridge.run_command(command)
        bridge.run_command(command)
        restarted = self.make_bridge()
        restarted.run_command(command)
        self.assertEqual(calls, ["/api/tare"])
        self.assertEqual(restarted.pending_results()[0]["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
