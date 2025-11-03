from flask import Flask, request, jsonify, send_from_directory
import os
import json

app = Flask(__name__, static_folder="webapp", static_url_path="")

# Paths to your configuration files
SETTINGS_FILE = "shade_settings.json"
SCHEDULE_FILE = "shade_schedule.json"
MODE_FILE = "shade_mode.json"

# Default values
default_settings = {
    "sensor_steps": [],
    "mode": "auto"
}
default_schedules = []
current_settings = default_settings.copy()
current_schedules = default_schedules.copy()


# --- Utility functions ---

def load_json_file(path, default):
    """Load JSON from file or return default"""
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
    return default


def save_json_file(path, data):
    """Save JSON to file safely"""
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {path}: {e}")
        return False


# --- Autoload configuration on startup ---
@app.before_first_request
def autoload_config():
    global current_settings, current_schedules
    print("Autoloading configuration...")
    current_settings = load_json_file(SETTINGS_FILE, default_settings)
    current_schedules = load_json_file(SCHEDULE_FILE, default_schedules)
    print("Loaded settings:", current_settings)
    print("Loaded schedules:", current_schedules)


# --- Serve the web interface ---
@app.route("/")
def index():
    return send_from_directory("webapp", "index.html")


# --- API Endpoints ---

@app.route("/api/status", methods=["GET"])
def api_status():
    """Return current loaded configuration"""
    return jsonify({
        "settings": current_settings,
        "schedules": current_schedules
    })


@app.route("/api/save", methods=["POST"])
def api_save():
    """Save settings and schedules from frontend"""
    global current_settings, current_schedules

    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400

        current_settings = data.get("settings", default_settings)
        current_schedules = data.get("schedules", default_schedules)

        # Save to files
        save_json_file(SETTINGS_FILE, current_settings)
        save_json_file(SCHEDULE_FILE, current_schedules)

        print("Configuration saved.")
        return jsonify({"status": "ok"})
    except Exception as e:
        print("Error in /api/save:", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/mode", methods=["POST"])
def api_mode():
    """Update current operation mode"""
    global current_settings
    data = request.get_json()
    mode = data.get("mode", "auto")
    current_settings["mode"] = mode
    save_json_file(MODE_FILE, {"mode": mode})
    print(f"Mode set to: {mode}")
    return jsonify({"status": "ok", "mode": mode})


@app.route("/api/move", methods=["POST"])
def api_move():
    """Simulate a shade movement command"""
    data = request.get_json()
    direction = data.get("direction", "up")
    steps = data.get("steps", 10)
    print(f"[MOVE] Moving shade {direction} for {steps} steps")
    # Here you would send actual commands to your hardware (e.g., GPIO / Serial)
    return jsonify({"status": "ok", "direction": direction, "steps": steps})


@app.route("/api/swap", methods=["POST"])
def api_swap():
    """Simulate swapping shades (sunshade/blackout)"""
    print("[SWAP] Switching shade type")
    # Your hardware control logic would go here
    return jsonify({"status": "ok"})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset configuration back to defaults"""
    global current_settings, current_schedules
    current_settings = default_settings.copy()
    current_schedules = default_schedules.copy()
    save_json_file(SETTINGS_FILE, current_settings)
    save_json_file(SCHEDULE_FILE, current_schedules)
    print("Configuration reset to defaults.")
    return jsonify({"status": "ok", "message": "Reset complete"})


# --- Static file serving for frontend assets ---
@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory("webapp", path)


# --- Run the Flask app ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

