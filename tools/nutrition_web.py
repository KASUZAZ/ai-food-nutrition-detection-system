"""Persistent website, password sessions and ESP32 bridge (standard library)."""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import math
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MYT = timezone(timedelta(hours=8))
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def now_iso():
    return datetime.now(MYT).isoformat(timespec="seconds")


def number(value, label, maximum=100000):
    if isinstance(value, bool):
        raise ValueError(f"{label} mesti nombor yang sah")
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} mesti nombor yang sah") from None
    if not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError(f"{label} mesti antara 0 dan {maximum}")
    return value


def text_field(value, label, limit=100):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f"{label} diperlukan (maksimum {limit} aksara)")
    value = value.strip()
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} mengandungi aksara tidak sah")
    return value


def food_values(data):
    name = text_field(data.get("food"), "Jenis makanan")
    rate = number(data.get("calories_per_100g"), "Kalori/100g", 10000) / 100
    note = data.get("note", "")
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError("Nota maksimum 500 aksara")
    return name, rate, note


def meal_values(data):
    name = text_field(data.get("food"), "Jenis makanan")
    weight = number(data.get("weight_g"), "Berat", 100000)
    if weight <= 0:
        raise ValueError("Berat mesti lebih daripada 0 g")
    calories = number(data.get("calories"), "Kalori", 1000000)
    try:
        eaten = datetime.fromisoformat(data["eaten_at"])
        if eaten.tzinfo is None:
            eaten = eaten.replace(tzinfo=MYT)
        eaten_at = eaten.astimezone(MYT).isoformat(timespec="seconds")
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("Tarikh dan waktu makan tidak sah") from None
    return name, weight, calories, eaten_at


def jpeg_bytes(raw):
    from PIL import Image, UnidentifiedImageError
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Gambar mesti antara 1 bait dan 2 MB")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 16000000:
                raise ValueError("Resolusi gambar terlalu besar")
            image.load()
            image.thumbnail((1600, 1600))
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=88)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Gambar tidak sah") from None


class Store:
    def __init__(self, path, seed_csv):
        self.lock = threading.RLock()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS admin_credentials (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    salt BLOB NOT NULL, password_hash BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS foods (
                    id INTEGER PRIMARY KEY, food TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    calorie_per_gram REAL NOT NULL CHECK(calorie_per_gram >= 0),
                    note TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS meals (
                    id INTEGER PRIMARY KEY, food TEXT NOT NULL,
                    weight_g REAL NOT NULL CHECK(weight_g > 0),
                    calories REAL NOT NULL CHECK(calories >= 0), eaten_at TEXT NOT NULL,
                    image BLOB, source TEXT NOT NULL, event_key TEXT UNIQUE,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            """)
            if not self.db.execute("SELECT 1 FROM foods LIMIT 1").fetchone():
                with Path(seed_csv).open(encoding="utf-8-sig", newline="") as file:
                    self.db.executemany(
                        "INSERT INTO foods(food, calorie_per_gram, note) VALUES(?,?,?)",
                        [(r["food"], number(r["calorie_per_gram"], "Kalori/g", 100),
                          r.get("note", "")) for r in csv.DictReader(file)],
                    )

    def credentials(self):
        with self.lock:
            row = self.db.execute("SELECT salt,password_hash FROM admin_credentials WHERE id=1").fetchone()
            return tuple(row) if row else None

    def set_password(self, password):
        if not isinstance(password, str) or not 8 <= len(password) <= 1024:
            raise ValueError("Kata laluan mesti 8 hingga 1024 aksara")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
        with self.lock, self.db:
            self.db.execute("""INSERT INTO admin_credentials(id,salt,password_hash) VALUES(1,?,?)
                ON CONFLICT(id) DO UPDATE SET salt=excluded.salt,password_hash=excluded.password_hash""",
                (salt, digest))

    def foods(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM foods ORDER BY food")]

    def save_food(self, data, food_id=None):
        name, rate, note = food_values(data)
        with self.lock, self.db:
            if food_id is None:
                self.db.execute("INSERT INTO foods(food,calorie_per_gram,note) VALUES(?,?,?)", (name, rate, note))
            elif not self.db.execute("UPDATE foods SET food=?,calorie_per_gram=?,note=? WHERE id=?", (name, rate, note, food_id)).rowcount:
                raise LookupError("Makanan tidak ditemui")

    def meals(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("""
                SELECT id,food,weight_g,calories,eaten_at,source,created_at,updated_at,
                CASE WHEN image IS NULL THEN NULL ELSE '/api/meals/' || id || '/image' END AS image_url
                FROM meals ORDER BY eaten_at DESC,id DESC
            """)]

    def save_meal(self, data, meal_id=None, *, image=None, source="manual", event_key=None):
        name, weight, calories, eaten_at = meal_values(data)
        stamp = now_iso()
        with self.lock, self.db:
            if meal_id is None:
                cursor = self.db.execute("""INSERT INTO meals
                    (food,weight_g,calories,eaten_at,image,source,event_key,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING""",
                    (name, weight, calories, eaten_at, image, source, event_key, stamp, stamp))
                return cursor.lastrowid if cursor.rowcount else None
            cursor = self.db.execute("""UPDATE meals SET food=?,weight_g=?,calories=?,eaten_at=?,
                image=COALESCE(?,image),updated_at=? WHERE id=?""",
                (name, weight, calories, eaten_at, image, stamp, meal_id))
            if not cursor.rowcount:
                raise LookupError("Rekod tidak ditemui")
            return meal_id

    def meal_image(self, meal_id):
        with self.lock:
            row = self.db.execute("SELECT image FROM meals WHERE id=?", (meal_id,)).fetchone()
            return row[0] if row else None


class AppState:
    def __init__(self, classifier, store, password=None, scale_url=""):
        self.classifier = classifier
        self.store = store
        self.scale_url = scale_url.rstrip("/")
        self.lock = threading.RLock()
        self.catalog_lock = threading.Lock()
        self.auth_lock = threading.Lock()
        if password is not None:
            store.set_password(password)
        credentials = store.credentials()
        if credentials is None:
            raise ValueError("Tetapkan kata laluan pentadbir dahulu")
        self.salt, self.password_hash = credentials
        self.sessions = set()
        self.attempts = {}
        self.last_image = None
        self.last_result = None
        self.last_detection_at = None
        self.detection_measurement = None
        self.scale = None
        self.scale_seen = 0
        self.scale_error = "Penimbang belum disambungkan"
        self.stop = threading.Event()
        self.sync_catalog()

    def hash_password(self, password):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), self.salt, 200000)

    def sync_catalog(self):
        if self.classifier:
            self.classifier.replace_foods(self.store.foods())

    def login(self, password, client):
        with self.auth_lock:
            now = time.monotonic()
            self.attempts = {k: v for k, v in self.attempts.items() if now - v[1] < 60}
            count, _ = self.attempts.get(client, (0, now))
            if count >= 5:
                return None, 429
            if not hmac.compare_digest(self.hash_password(password), self.password_hash):
                self.attempts[client] = (count + 1, now)
                return None, 401
            self.attempts.pop(client, None)
            token = secrets.token_urlsafe(32)
            self.sessions.add(token)
            return token, 200

    def authenticated(self, token):
        with self.auth_lock:
            return token in self.sessions

    def logout(self, token):
        with self.auth_lock:
            self.sessions.discard(token)

    def device_request(self, path, method="GET"):
        if not self.scale_url:
            raise ValueError("Tetapkan --scale-url kepada IP ESP32 penimbang dahulu")
        req = Request(self.scale_url + path, data=b"" if method == "POST" else None, method=method)
        with urlopen(req, timeout=2) as response:
            return json.load(response)

    def snapshot(self):
        with self.lock:
            online = self.scale is not None and time.monotonic() - self.scale_seen < 4
            result = dict(self.last_result) if self.last_result else None
            return {"model_ready": self.classifier is not None,
                    "detected_at": self.last_detection_at, "result": result,
                    "scale": dict(self.scale) if self.scale else None,
                    "scale_online": online, "scale_error": self.scale_error,
                    "server_time": now_iso()}

    def detection(self, raw, result, measurement):
        with self.lock:
            self.last_image = raw
            self.last_result = dict(result)
            self.last_detection_at = now_iso()
            self.detection_measurement = measurement

    def accept_scale(self, data):
        weight = number(data.get("weight_g"), "Berat", 100000)
        with self.lock:
            self.scale = data
            self.scale_seen = time.monotonic()
            self.scale_error = None
            result = self.last_result
            # Both firmware IDs must match: a rejected/old photo or a different
            # placement must never acquire the current weight.
            if not (data.get("locked") is True and data.get("sensor_ready") is True
                    and weight > 0 and result and result["accepted"]
                    and data.get("detection_id") == result["detection_id"]
                    and data.get("measurement_id") == self.detection_measurement
                    and self.detection_measurement):
                return
            self.store.save_meal({"food": result["food"], "weight_g": weight,
                                  "calories": round(weight * result["calorie_per_gram"], 2),
                                  "eaten_at": now_iso()}, image=self.last_image,
                                 source="sensor", event_key=self.detection_measurement)

    def poll_scale(self):
        while not self.stop.is_set():
            try:
                self.accept_scale(self.device_request("/api/status"))
            except (OSError, URLError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                with self.lock:
                    self.scale_seen = 0
                    self.scale_error = str(exc)
            self.stop.wait(1)


class AiRequestHandler(BaseHTTPRequestHandler):
    server_version = "FoodNutritionWeb/2.0"

    @property
    def state(self):
        return self.server.app_state

    def send_bytes(self, status, body, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, status, payload, headers=None):
        self.send_bytes(status, json.dumps(payload, allow_nan=False, ensure_ascii=False).encode(), "application/json; charset=utf-8", headers)

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie["nutrition_session"].value if "nutrition_session" in cookie else ""
        except Exception:
            return ""

    def read_body(self, limit):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Content-Length tidak sah") from None
        if not 0 < length <= limit:
            raise ValueError("Saiz permintaan tidak sah / terlalu besar")
        self.connection.settimeout(15)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("Permintaan tidak lengkap")
        return raw

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("Content-Type mesti application/json")
        data = json.loads(self.read_body(3 * 1024 * 1024))
        if not isinstance(data, dict):
            raise ValueError("Objek JSON diperlukan")
        return data

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self.send_json(200, {"ok": True, "model_ready": self.state.classifier is not None})
        if path == "/api/session":
            return self.send_json(200, {"authenticated": self.state.authenticated(self.token())})
        if path in ("/api/latest", "/api/live"):
            return self.send_json(200, self.state.snapshot())
        if path == "/api/foods":
            return self.send_json(200, {"foods": self.state.store.foods()})
        if path == "/api/meals":
            return self.send_json(200, {"meals": self.state.store.meals()})
        if path == "/latest.jpg":
            with self.state.lock:
                raw = self.state.last_image
            if raw:
                return self.send_bytes(200, raw, "image/jpeg")
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "meals"] and parts[2].isdigit() and parts[3] == "image":
            raw = self.state.store.meal_image(int(parts[2]))
            if raw:
                return self.send_bytes(200, raw, "image/jpeg")
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                  "/styles.css": ("styles.css", "text/css; charset=utf-8")}
        if path in assets:
            name, mime = assets[path]
            return self.send_bytes(200, (ROOT / "web" / name).read_bytes(), mime,
                                   {"Content-Security-Policy": "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        self.send_json(404, {"error": "Tidak ditemui"})

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def mutate(self):
        # Browser writes require same-origin JSON; device JPEG uploads use /classify.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in ("http://" + host, "https://" + host):
            return self.send_json(403, {"error": "Origin tidak dibenarkan"})
        path = urlparse(self.path).path
        try:
            if path == "/classify" and self.command == "POST":
                return self.classify()
            if path == "/api/login" and self.command == "POST":
                password = self.read_json().get("password", "")
                if not isinstance(password, str) or len(password) > 1024:
                    raise ValueError("Kata laluan tidak sah")
                token, status = self.state.login(password, self.client_address[0])
                if not token:
                    return self.send_json(status, {"error": "Terlalu banyak percubaan. Tunggu 60 saat." if status == 429 else "Kata laluan salah"})
                secure = "; Secure" if getattr(self.state, "secure_cookies", False) else ""
                return self.send_json(200, {"ok": True}, {"Set-Cookie": f"nutrition_session={token}; HttpOnly; SameSite=Strict; Path=/{secure}"})
            if not self.state.authenticated(self.token()):
                return self.send_json(401, {"error": "Masukkan kata laluan pentadbir dahulu"})
            data = self.read_json()
            if path == "/api/logout" and self.command == "POST":
                self.state.logout(self.token())
                secure = "; Secure" if getattr(self.state, "secure_cookies", False) else ""
                return self.send_json(200, {"ok": True}, {"Set-Cookie": f"nutrition_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure}"})
            if path in ("/api/tare", "/api/capture") and self.command == "POST":
                return self.send_json(200, self.state.device_request(path, "POST"))
            parts = path.strip("/").split("/")
            ident = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else None
            create = self.command == "POST" and len(parts) == 2
            update = self.command == "PUT" and ident is not None
            if parts[:2] == ["api", "foods"] and (create or update):
                with self.state.catalog_lock:
                    self.state.store.save_food(data, ident)
                    self.state.sync_catalog()
                return self.send_json(201 if create else 200, {"ok": True})
            if parts[:2] == ["api", "meals"] and (create or update):
                image = None
                if data.get("image_base64"):
                    try:
                        image = jpeg_bytes(base64.b64decode(data["image_base64"], validate=True))
                    except (ValueError, TypeError):
                        raise ValueError("Gambar tidak sah atau melebihi 2 MB") from None
                meal_id = self.state.store.save_meal(data, ident, image=image)
                return self.send_json(201 if create else 200, {"ok": True, "id": meal_id})
            self.send_json(404, {"error": "Tidak ditemui"})
        except (ValueError, TypeError, UnicodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except LookupError as exc:
            self.send_json(404, {"error": str(exc)})
        except sqlite3.IntegrityError:
            self.send_json(409, {"error": "Nama makanan sudah digunakan atau data tidak sah"})
        except (OSError, URLError) as exc:
            self.send_json(503, {"error": f"Peranti tidak dapat dihubungi: {exc}"})

    def classify(self):
        if not self.state.classifier:
            return self.send_json(503, {"error": "Mod web sahaja; model AI belum dimuatkan"})
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "image/jpeg":
            return self.send_json(415, {"error": "Content-Type must be image/jpeg"})
        raw = jpeg_bytes(self.read_body(MAX_IMAGE_BYTES))
        from PIL import Image
        before = self.state.snapshot()
        scale = before["scale"] or {}
        measurement = scale.get("measurement_id") if before["scale_online"] and scale.get("weight_g", 0) > 0 else None
        started = time.perf_counter()
        result = self.state.classifier.classify(Image.open(io.BytesIO(raw)))
        result["inference_ms"] = round((time.perf_counter() - started) * 1000)
        result["detection_id"] = secrets.token_hex(12)
        self.state.detection(raw, result, measurement)
        self.send_json(200 if result["accepted"] else 422, result)

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} - {fmt % args}")
