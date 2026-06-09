# http://localhost:5050
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
FOODS_PATH = DATA_DIR / "foods.json"
FLOORPLAN_PATH = BASE_DIR / "floorplan" / "floorplan.json"

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

app = Flask(__name__)


DEFAULT_FOODS: dict[str, Any] = {
    "items": []
}


def ensure_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)

    if not FOODS_PATH.exists():
        save_json(FOODS_PATH, DEFAULT_FOODS)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    shutil.move(tmp_path, path)


def clean_room_id(value: str) -> str:
    return value.strip().upper()


def room_shelf_exists(room_id: str, shelf_id: int) -> bool:
    floorplan = load_json(FLOORPLAN_PATH, {"rooms": []})

    for room in floorplan.get("rooms", []):
        if room.get("id") != room_id:
            continue

        for shelf in room.get("shelves", []):
            if shelf.get("id") == shelf_id and isinstance(shelf.get("point"), list):
                return True

    return False


def validate_food_payload(data: Any) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "Food item must be a JSON object."

    name = data.get("name")
    room = data.get("room")
    shelf = data.get("shelf")

    if not isinstance(name, str) or not name.strip():
        return False, "Missing food name."

    if not isinstance(room, str) or not re.fullmatch(r"[A-Z0-9]{3}", room.strip().upper()):
        return False, "Room must be a 3-character code."

    if not isinstance(shelf, int) or shelf < 1:
        return False, "Shelf must be a positive integer."

    image = data.get("image")
    if image is not None and not isinstance(image, str):
        return False, "Image path must be a string or null."

    notes = data.get("notes")
    if notes is not None and not isinstance(notes, str):
        return False, "Notes must be a string or null."

    return True, "OK"


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/floorplan/floorplan.json")
def serve_floorplan_static_path():
    return send_from_directory(BASE_DIR / "floorplan", "floorplan.json")


@app.get("/data/foods.json")
def serve_foods_static_path():
    return send_from_directory(DATA_DIR, "foods.json")


@app.get("/data/images/<path:filename>")
def serve_image_static_path(filename: str):
    return send_from_directory(IMAGES_DIR, filename)


@app.get("/api/floorplan")
def api_floorplan():
    floorplan = load_json(
        FLOORPLAN_PATH,
        {
            "config": {
                "width": 10000,
                "height": 10000,
                "grid": 50
            },
            "rooms": []
        }
    )

    return jsonify(floorplan)


@app.get("/api/foods")
def api_get_foods():
    return jsonify(load_json(FOODS_PATH, DEFAULT_FOODS))


@app.post("/api/foods")
def api_add_food():
    data = request.get_json(silent=True)

    valid, message = validate_food_payload(data)
    if not valid:
        return jsonify({"ok": False, "error": message}), 400

    room = clean_room_id(data["room"])
    shelf = int(data["shelf"])

    if not room_shelf_exists(room, shelf):
        return jsonify({
            "ok": False,
            "error": f"Location {room}-{shelf} does not exist in floorplan.json."
        }), 400

    foods = load_json(FOODS_PATH, DEFAULT_FOODS)

    item = {
        "id": uuid.uuid4().hex,
        "name": data["name"].strip(),
        "room": room,
        "shelf": shelf,
        "image": data.get("image") or None,
        "notes": data.get("notes") or ""
    }

    foods.setdefault("items", []).append(item)
    save_json(FOODS_PATH, foods)

    return jsonify({"ok": True, "item": item})


@app.put("/api/foods/<item_id>")
def api_update_food(item_id: str):
    data = request.get_json(silent=True)

    valid, message = validate_food_payload(data)
    if not valid:
        return jsonify({"ok": False, "error": message}), 400

    room = clean_room_id(data["room"])
    shelf = int(data["shelf"])

    if not room_shelf_exists(room, shelf):
        return jsonify({
            "ok": False,
            "error": f"Location {room}-{shelf} does not exist in floorplan.json."
        }), 400

    foods = load_json(FOODS_PATH, DEFAULT_FOODS)

    for item in foods.setdefault("items", []):
        if item.get("id") == item_id:
            item["name"] = data["name"].strip()
            item["room"] = room
            item["shelf"] = shelf
            item["image"] = data.get("image") or None
            item["notes"] = data.get("notes") or ""

            save_json(FOODS_PATH, foods)

            return jsonify({"ok": True, "item": item})

    return jsonify({"ok": False, "error": "Food item not found."}), 404


@app.delete("/api/foods/<item_id>")
def api_delete_food(item_id: str):
    foods = load_json(FOODS_PATH, DEFAULT_FOODS)
    items = foods.setdefault("items", [])

    new_items = [item for item in items if item.get("id") != item_id]

    if len(new_items) == len(items):
        return jsonify({"ok": False, "error": "Food item not found."}), 404

    foods["items"] = new_items
    save_json(FOODS_PATH, foods)

    return jsonify({"ok": True})


@app.post("/api/images")
def api_upload_image():
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "No image file uploaded."}), 400

    file = request.files["image"]

    if not file.filename:
        return jsonify({"ok": False, "error": "Empty filename."}), 400

    original_name = secure_filename(file.filename)
    ext = Path(original_name).suffix.lower()

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "ok": False,
            "error": f"Unsupported image type: {ext}"
        }), 400

    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = IMAGES_DIR / filename

    file.save(save_path)

    return jsonify({
        "ok": True,
        "path": f"data/images/{filename}"
    })


if __name__ == "__main__":
    ensure_files()
    app.run(host="0.0.0.0", port=5050, debug=True)