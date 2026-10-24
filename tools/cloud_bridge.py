"""Outbound laptop bridge. Retries saved meals and journals device commands."""
from __future__ import annotations

import base64
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class CloudBridge:
    def __init__(self, state, config_path):
        self.state = state
        self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.url = self.config["url"].rstrip("/")
        parsed = urlparse(self.url)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")):
            raise ValueError("Cloud bridge memerlukan URL HTTPS")
        if len(self.config.get("token", "")) < 32 or not self.config.get("device_id"):
            raise ValueError("Konfigurasi cloud bridge tidak lengkap")
        self.last_photo = None
        self.last_catalog = None
        self.last_error = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        store = self.state.store
        with store.lock, store.db:
            store.db.executescript("""
                CREATE TABLE IF NOT EXISTS cloud_sent (meal_id INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS cloud_commands (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, message TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0);
            """)
            # Never execute an uncertain command twice after a laptop restart.
            store.db.execute("UPDATE cloud_commands SET status='failed', message=? WHERE status='started'",
                             ("Laptop dimulakan semula; keputusan arahan sebelumnya tidak dapat disahkan.",))

    def request(self, path, payload):
        req = Request(self.url + path, data=json.dumps(payload, allow_nan=False).encode(),
                      headers={"Content-Type":"application/json", "Authorization":"Bearer " + self.config["token"]})
        with urlopen(req, timeout=20) as response:
            return json.load(response)

    def pending_results(self):
        store = self.state.store
        with store.lock:
            return [dict(row) for row in store.db.execute("""SELECT id,status,message FROM cloud_commands
                WHERE acknowledged=0 AND status IN ('succeeded','failed') LIMIT 20""")]

    def update_catalog(self, foods):
        if not isinstance(foods, list) or len(foods) < 2:
            raise ValueError("Pangkalan makanan cloud tidak lengkap")
        catalog = json.dumps(foods, sort_keys=True)
        if catalog == self.last_catalog:
            return
        store = self.state.store
        # Lock order matches the local website's catalog editor.
        with self.state.catalog_lock:
            with store.lock, store.db:
                store.db.execute("DELETE FROM foods")
                store.db.executemany("INSERT INTO foods(id,food,calorie_per_gram,note) VALUES(?,?,?,?)",
                                     [(f["id"],f["food"],f["calorie_per_gram"],f.get("note", "")) for f in foods])
            self.state.sync_catalog()
        self.last_catalog = catalog

    def run_command(self, command):
        ident, action = command["id"], command["action"]
        if action not in ("tare", "capture"):
            return
        store = self.state.store
        with store.lock, store.db:
            cursor = store.db.execute("INSERT OR IGNORE INTO cloud_commands(id,status,message) VALUES(?,'started','')", (ident,))
            if not cursor.rowcount:
                return
        status, message = "failed", "Arahan gagal"
        try:
            created = datetime.fromisoformat(command["created_at"].replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - created).total_seconds() > 90:
                raise ValueError("Arahan sudah luput")
            result = self.state.device_request("/api/" + action, "POST")
            status = "succeeded"
            message = "Tare selesai pada penimbang." if action == "tare" else "Kamera menerima permintaan gambar. Tunggu keputusan AI."
            if result.get("ok") is False:
                raise ValueError(result.get("error", "Peranti menolak arahan"))
        except (OSError, ValueError) as error:
            status = "failed"
            message = str(error)[:500] or "Peranti tidak dapat dihubungi"
        with store.lock, store.db:
            store.db.execute("UPDATE cloud_commands SET status=?,message=? WHERE id=?", (status,message,ident))

    def sync_once(self):
        with self.state.lock:
            live = self.state.snapshot()
            raw = self.state.last_image
        payload = {"live":live, "command_results":self.pending_results()}
        photo = (payload["live"].get("result") or {}).get("detection_id")
        if photo and photo != self.last_photo:
            if raw:
                payload["image_base64"] = base64.b64encode(raw).decode()
        reply = self.request("/api/device/sync", payload)
        if not reply.get("ok"):
            raise ValueError("Cloud menolak bacaan")
        self.last_photo = photo
        self.update_catalog(reply["foods"])
        store = self.state.store
        with store.lock, store.db:
            for ident in reply.get("acknowledged_commands", []):
                store.db.execute("UPDATE cloud_commands SET acknowledged=1 WHERE id=?", (ident,))
        for command in reply.get("commands", []):
            self.run_command(command)

        # Send at most one meal per heartbeat so photos do not delay live data
        # or exceed the function request-size limit. Local SQLite is the outbox.
        with store.lock:
            row = store.db.execute("""SELECT m.* FROM meals m LEFT JOIN cloud_sent s ON s.meal_id=m.id
                WHERE s.meal_id IS NULL ORDER BY m.id LIMIT 1""").fetchone()
        if row:
            meal = dict(row)
            image = meal.pop("image")
            meal["event_key"] = self.config["device_id"] + ":" + (meal["event_key"] or "meal:" + str(meal["id"]))
            if image:
                meal["image_base64"] = base64.b64encode(image).decode()
            if not self.request("/api/device/meal", meal).get("ok"):
                raise ValueError("Cloud belum mengakui rekod makanan")
            with store.lock, store.db:
                store.db.execute("INSERT OR IGNORE INTO cloud_sent(meal_id) VALUES(?)", (meal["id"],))

    def run(self):
        print("Cloud bridge started: " + self.url, flush=True)
        while not self.state.stop.is_set():
            try:
                self.sync_once()
                if self.last_error:
                    print("Cloud bridge reconnected.", flush=True)
                self.last_error = None
            except (OSError, ValueError, KeyError, TypeError) as error:
                # Do not log auth headers, tokens or request payloads.
                code = getattr(error, "code", None)
                label = f"HTTP {code}" if code else type(error).__name__
                if label != self.last_error:
                    print(f"Cloud bridge offline ({label}); retrying. Saved meals remain on laptop.", flush=True)
                self.last_error = label
            self.state.stop.wait(2)
