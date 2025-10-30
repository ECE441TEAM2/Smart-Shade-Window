# ECE 441 Fall 2025 — Integrated Web API version

import time
import board
import adafruit_tca9548a
import adafruit_veml7700
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import logging
import json
import os
from flask import Flask, jsonify, request, send_from_directory
from threading import Thread

# ----------------------------
# Logging Setup
# ----------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# ----------------------------
# Hardware Setup
# ----------------------------
i2c = board.I2C()
mux = adafruit_tca9548a.TCA9548A(i2c)
motor_shield = MotorKit()

CHANNELS = 5
SETTINGS_FILE = "shade_settings.json"
SCHEDULE_FILE = "shade_schedules.json"

sunlight_threshold = 2500
sensor_array = [None] * CHANNELS
op_mode = "auto"
active_shade = "sunshade"
step = 0
sensor_steps = [0] * CHANNELS
running = True

# ----------------------------
# Flask Setup
# ----------------------------
app = Flask(__name__, static_folder="webapp")

# ----------------------------
# Utility & Helper Functions
# ----------------------------
def sensor_mask_helper():
    return [None if x is None else 1 for x in sensor_array]

def save_settings():
    settings = {
        "sensor_mask": sensor_mask_helper(),
        "op_mode": op_mode,
        "active_shade": active_shade,
        "step": step,
        "sensor_steps": sensor_steps
    }
    try:
        with open(SETTINGS_FILE, "w") as file:
            json.dump(settings, file, indent=4)
        logging.info("Settings saved!")
    except Exception as e:
        logging.error(f"Failed to save settings: {e}")

def load_settings():
    global step, active_shade, op_mode, sensor_steps
    if not os.path.exists(SETTINGS_FILE):
        logging.info("Settings file not found. Launching setup.")
        return
    try:
        with open(SETTINGS_FILE, "r") as file:
            settings = json.load(file)
        logging.info("Settings loaded successfully!")
        sensor_steps = settings.get("sensor_steps", [0]*CHANNELS)
        op_mode = settings.get("op_mode", "auto")
        active_shade = settings.get("active_shade", "sunshade")
        step = settings.get("step", 0)
    except Exception as e:
        logging.error(f"Failed to load settings: {e}")

def scan_mux():
    count = 0
    for channel in range(CHANNELS):
        if mux[channel].try_lock():
            addresses = mux[channel].scan()
            mux[channel].unlock()
            if 16 in addresses:
                sensor_array[channel] = adafruit_veml7700.VEML7700(mux[channel])
                count += 1
    logging.info(f"Detected {count} light sensors.")

def read_sensors():
    out = [None] * CHANNELS
    for i, sensor in enumerate(sensor_array):
        if sensor is None:
            continue
        try:
            out[i] = sensor.lux
        except Exception as e:
            logging.error(f"Sensor {i} read failed: {e}")
            out[i] = None
    return out

def move_motor_to_step(new_step):
    global step
    delta = new_step - step
    logging.info(f"Moving motor: {active_shade} from {step} to {new_step} (Δ={delta})")

    motor = motor_shield.stepper1 if active_shade == "sunshade" else motor_shield.stepper2
    direction = stepper.BACKWARD if delta > 0 else stepper.FORWARD

    for _ in range(abs(delta)):
        motor.onestep(direction=direction, style=stepper.SINGLE)
        step += 1 if delta > 0 else -1
        time.sleep(0.01)

def swap_blind():
    global active_shade, step
    prev = step
    move_motor_to_step(0)
    active_shade = "blackout" if active_shade == "sunshade" else "sunshade"
    move_motor_to_step(prev)
    logging.info(f"Switched to {active_shade}")

def automatic_mode():
    readings = read_sensors()
    for i, lux in enumerate(readings):
        if lux and lux > sunlight_threshold:
            logging.info(f"Sensor {i} triggered ({lux} lux). Moving to step {sensor_steps[i]}")
            move_motor_to_step(sensor_steps[i])
            break

# ----------------------------
# Flask API Endpoints
# ----------------------------

@app.route("/")
def serve_index():
    """Serve the HTML webapp."""
    return send_from_directory("webapp", "index.html")

@app.route("/api/move", methods=["POST"])
def api_move():
    """Move blinds up or down."""
    data = request.json
    direction = data.get("direction")
    steps = int(data.get("steps", 10))
    if direction == "up":
        move_motor_to_step(step - steps)
    elif direction == "down":
        move_motor_to_step(step + steps)
    return jsonify({"status": "ok", "current_step": step})

@app.route("/api/mode", methods=["POST"])
def api_mode():
    """Change operation mode (auto/manual/schedule/setup)."""
    global op_mode
    op_mode = request.json.get("mode", "auto")
    logging.info(f"Mode switched to {op_mode}")
    return jsonify({"status": "ok", "mode": op_mode})

@app.route("/api/swap", methods=["POST"])
def api_swap():
    """Swap between blackout and sunshade blinds."""
    swap_blind()
    return jsonify({"status": "ok", "active_shade": active_shade})

@app.route("/api/sensors", methods=["GET"])
def api_sensors():
    """Return current sensor readings."""
    return jsonify({"readings": read_sensors()})

@app.route("/api/save", methods=["POST"])
def api_save():
    """Save configuration files from the webapp."""
    data = request.json
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data.get("settings"), f, indent=4)
        with open(SCHEDULE_FILE, "w") as f:
            json.dump(data.get("schedules"), f, indent=4)
        logging.info("Config and schedules saved from webapp.")
        return jsonify({"status": "ok"})
    except Exception as e:
        logging.error(f"Save failed: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/status", methods=["GET"])
def api_status():
    """Return current app status."""
    return jsonify({
        "mode": op_mode,
        "active_shade": active_shade,
        "step": step
    })

# ----------------------------
# Background Control Thread
# ----------------------------
def control_loop():
    global running
    while running:
        if op_mode == "auto":
            automatic_mode()
        elif op_mode == "schedule":
            # Future: implement schedule logic here
            pass
        time.sleep(1)

# ----------------------------
# Main Entry Point
# ----------------------------
if __name__ == "__main__":
    scan_mux()
    load_settings()

    Thread(target=control_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)

