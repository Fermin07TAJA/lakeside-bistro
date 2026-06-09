# http://localhost:5051

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
FLOORPLAN_PATH = BASE_DIR / "floorplan.json"
EDITOR_HTML = BASE_DIR / "editor.html"

app = Flask(__name__)


DEFAULT_FLOORPLAN: dict[str, Any] = {
    "config": {
        "width": 10000,
        "height": 10000,
        "grid": 50
    },
    "rooms": []
}


def load_floorplan() -> dict[str, Any]:
    if not FLOORPLAN_PATH.exists():
        save_floorplan(DEFAULT_FLOORPLAN)
        return DEFAULT_FLOORPLAN

    with FLOORPLAN_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_floorplan(data: dict[str, Any]) -> None:
    with FLOORPLAN_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def validate_floorplan(data: Any) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "Floorplan must be a JSON object."

    if "config" not in data or not isinstance(data["config"], dict):
        return False, "Missing config object."

    config = data["config"]

    for key in ("width", "height", "grid"):
        if key not in config:
            return False, f"Missing config.{key}."

        if not isinstance(config[key], int | float):
            return False, f"config.{key} must be numeric."

        if config[key] <= 0:
            return False, f"config.{key} must be positive."

    if "rooms" not in data or not isinstance(data["rooms"], list):
        return False, "Missing rooms array."

    seen_room_ids: set[str] = set()

    for room_index, room in enumerate(data["rooms"]):
        if not isinstance(room, dict):
            return False, f"Room {room_index} must be an object."

        room_id = room.get("id")
        if not isinstance(room_id, str) or len(room_id.strip()) != 3:
            return False, f"Room {room_index} must have a 3-letter id."

        room_id = room_id.strip().upper()

        if room_id in seen_room_ids:
            return False, f"Duplicate room id: {room_id}."

        seen_room_ids.add(room_id)

        if not isinstance(room.get("name"), str):
            return False, f"Room {room_id} must have a name."

        polygon = room.get("polygon")
        if not isinstance(polygon, list) or len(polygon) < 4:
            return False, f"Room {room_id} must have at least 4 polygon vertices."

        for point in polygon:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not all(isinstance(v, int | float) for v in point)
            ):
                return False, f"Room {room_id} has an invalid polygon point."

        shelves = room.get("shelves", [])
        if not isinstance(shelves, list):
            return False, f"Room {room_id} shelves must be an array."

        seen_shelf_ids: set[int] = set()

        for shelf in shelves:
            if not isinstance(shelf, dict):
                return False, f"Room {room_id} has an invalid shelf."

            shelf_id = shelf.get("id")
            if not isinstance(shelf_id, int):
                return False, f"Room {room_id} has a shelf with non-integer id."

            if shelf_id in seen_shelf_ids:
                return False, f"Room {room_id} has duplicate shelf id {shelf_id}."

            seen_shelf_ids.add(shelf_id)

            point = shelf.get("point")
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not all(isinstance(v, int | float) for v in point)
            ):
                return False, f"Room {room_id} shelf {shelf_id} has invalid point."

    return True, "OK"


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "editor.html")


@app.get("/api/floorplan")
def api_get_floorplan():
    return jsonify(load_floorplan())


@app.post("/api/floorplan")
def api_save_floorplan():
    data = request.get_json(silent=True)

    valid, message = validate_floorplan(data)

    if not valid:
        return jsonify({"ok": False, "error": message}), 400

    for room in data["rooms"]:
        room["id"] = room["id"].strip().upper()

    save_floorplan(data)

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051, debug=True)