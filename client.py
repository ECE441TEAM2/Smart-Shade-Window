# ECE 441 Fall 2025

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
import threading
import datetime

# set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# CircuitPython prep
i2c = board.I2C()
mux = adafruit_tca9548a.TCA9548A(i2c)
motor_shield = MotorKit()

# global variables
CHANNELS = 5 # do not change
SETTINGS_FILE = "shade_settings.json"
SCHEDULE_FILE = "shade_schedules.json"

sunlight_threshold = 2500 # any lux reading over this number is considered "sunlight"
sensor_array = [None] * CHANNELS # dummy sensor variables, the initial scan will propagate them
op_mode = "auto" # auto, manual, schedule, or setup
active_shade = "sunshade" # either "sunshade" or "blackout". stepper1 is the sunshade, stepper2 is the blackout
step = 0 # how many steps the motor has taken away from its resting position. 0 means the shade is all the way open.
sensor_steps = [0] * CHANNELS # the step positions corresponding to each sensor

running = True # main loop control variable, is set to False when the user presses Q
    # FYI: this should be done more gracefully in the future, since the user shouldn't really be turning the application off.
    # this mostly serves to save the settings before exiting
    # but it would be better to just periodically save the settings since in most cases, if the device shuts down,
    # it will be unexpected (power loss, crash, etc)

# for the schedule mode, keep track of when each scheduled movement was last executed, to not execute it multiple times
last_schedule_executions = {}

# Set up Flask, which manages the web app and its communications
app = Flask(__name__, static_folder="webapp")

def save_settings():
    """Saves the active setup settings to a file, to be loaded on next startup."""
    sensor_mask = sensor_mask_helper()
    settings = {
        "sensor_mask": sensor_mask,
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
    """Loads settings from SETTINGS_FILE.
    If the file does not exist, or if the quantity or wiring of the sensors does not match previously configured settings, forces setup to run."""
    global step, active_shade, op_mode, sensor_steps

    if not os.path.exists(SETTINGS_FILE):
        logging.info("Settings file not found. Launching setup.")
        op_mode = "setup"
        setup_mode()
        return
    try:
        with open(SETTINGS_FILE, "r") as file:
            settings = json.load(file)
        logging.info("Settings loaded successfully!")
        sensor_steps = settings["sensor_steps"]
        op_mode = settings["op_mode"]
        active_shade = settings["active_shade"]
        step = settings["step"]
        # if there is a sensor mismatch, force setup to run
        if sum(1 for s in settings["sensor_mask"] if s is not None) != sum(1 for s in sensor_array if s is not None):
            logging.warning("Sensor mismatch detected. Launching setup.")
            setup_mode()
        return

    except Exception as e:
        logging.error(f"Failed to load settings: {e}")

def sensor_mask_helper():
    """Returns an array which replaces every sensor instance in the array with just a 1, which can be saved to JSON."""
    return [None if x is None else 1 for x in sensor_array]

def scan_mux():
    """Scans each channel of the multiplexer for connected VEML7700 sensors.
    Updates the global sensor_array with instances of detected sensors."""
    count = 0
    for channel in range(CHANNELS):
        logging.debug(f"scan_mux: attempting to access channel {channel}")
        if mux[channel].try_lock():
            addresses = mux[channel].scan()
            mux[channel].unlock()
            if (16 in addresses): # VEML7700 has I2C address 0x10 (16 dec)
                logging.debug(f"scan_mux: Light sensor was detected on channel {channel}")
                # replace None in the sensor_array with a proper sensor object
                sensor_array[channel] = adafruit_veml7700.VEML7700(mux[channel])
                count += 1
            else:
                logging.debug(f"scan_mux: No light sensor detected on channel {channel}")
    logging.info(f"scan_mux: {count} sensors were detected!")
    return

def read_sensors():
    """Returns an array of the current lux readings from all sensors."""
    out = [None] * CHANNELS
    for i, sensor in enumerate(sensor_array):
        if sensor is None:
            continue
        try:
            out[i] = sensor.lux
        except Exception as e:
            logging.error(f"read_sensors: Error reading sensor {i}: {e}")
            out[i] = None
    logging.debug(f"read_sensors: Lux levels were retrieved: {out}")
    return out

def move_motor_to_step(new_step, safety=True):
    """Moves the active shade's motor to the specified step position.
    If safety is True, the motor will not move beyond the limits of the shade (0 <= step <= sensor_steps[0])"""
    if safety == True:
        if new_step < 0 or new_step > sensor_steps[0]:
            logging.warning(f"move_motor_to_step: Attempted to move to invalid step {new_step} while safety was active. Movement aborted.")
            return
    global step
    delta = new_step - step
    logging.debug(f"move_motor_to_step: Moving from step {step} to {new_step} (delta {delta})")
    # if positive, move down
    if delta > 0:
        for i in range(delta):
            if active_shade == "sunshade":
                motor_shield.stepper1.onestep(direction=stepper.BACKWARD, style=stepper.SINGLE)
            else:
                motor_shield.stepper2.onestep(direction=stepper.BACKWARD, style=stepper.SINGLE)
            step += 1
            time.sleep(0.01)
    # if negative, move up
    elif delta < 0:
        for i in range(-delta):
            if active_shade == "sunshade":
                motor_shield.stepper1.onestep(direction=stepper.FORWARD, style=stepper.SINGLE)
            else:
                motor_shield.stepper2.onestep(direction=stepper.FORWARD, style=stepper.SINGLE)
            step -= 1
            time.sleep(0.01)
    return

def swap_blind():
    """Switches the currently active blind to the the other blind.
    The original blind is moved back to its starting point (step 0) and the new blind moves to the same step position as the original blind."""
    global active_shade
    global step

    # make a copy of the current step since it will be overwritten by move_motor_to_step
    saved_step = step
    logging.debug(f"swap_blind: Swapping from {active_shade} blind.")
    # Move current blind back to 0
    move_motor_to_step(0)
    # Swap active blind
    if active_shade == "sunshade":
        active_shade = "blackout"
    else:
        active_shade = "sunshade"
    # Move new blind to the previous step position
    move_motor_to_step(saved_step)
    logging.debug(f"swap_blind: Now using {active_shade} blind.")
    return

def swap_blind_dumb():
    """Switches the currently active blind to the the other blind.
    Neither blind is moved in the process."""
    global active_shade

    logging.debug(f"swap_blind_dumb: Swapping from {active_shade} blind.")
    # Swap active blind
    if active_shade == "sunshade":
        active_shade = "blackout"
    else:
        active_shade = "sunshade"
    logging.debug(f"swap_blind_dumb: Now using {active_shade} blind.")
    return

def setup_mode():
    """Uses the web app to set up variables used by the other modes."""
    # NOT YET IMPLEMENTED
    pass

def automatic_mode():
    """Iterates through each sensor's readings from top to bottom.
    For the first one that it finds is too bright, the blind is moved to match that sensor's height."""
    for i, lux in enumerate(read_sensors()):
        if lux is None:
            continue
        if lux > sunlight_threshold:
            logging.debug(f"automatic_mode: Sensor {i} detected sunlight ({lux} lux). Adjusting shade.")
            move_motor_to_step(sensor_steps[i])
            return

def schedule_mode():
    """Checks SCHEDULE_FILE and moves the blind to certain positions in accordance with scheduled events."""
    global active_shade, step, sensor_steps

    # parse the current time
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")

    # load the schedule file
    try:
        with open(SCHEDULE_FILE, "r") as file:
            schedules = json.load(file)
    except FileNotFoundError:
        logging.info("schedule_mode: No schedule file found. Skipping schedule mode.")
        return
    except json.JSONDecodeError as e:
        logging.error(f"schedule_mode: Failed to parse schedule file: {e}")
        return
    logging.debug("schedule_mode: Schedule file loaded successfully.")

    # iterate through the schedule list to access each scheduled action
    for entry in schedules:
        scheduled_time = entry["time"]
        scheduled_shade = entry["motor"]
        scheduled_level = entry["level"]

        # format a schedule ID for tracking last execution
        schedule_id = f"{scheduled_time}_{scheduled_shade}_{scheduled_level}"
        logging.debug(f"schedule_mode: Now checking schedule entry: {schedule_id}")
        logging.debug(f"schedule_mode: Current time is {current_time}, scheduled time is {scheduled_time}")

        # skip if this schedule has already been executed today
        last_run_date = last_schedule_executions.get(schedule_id)
        if last_run_date == now.strftime("%Y-%m-%d"):
            continue

        if scheduled_time == current_time:
            logging.info(f"schedule_mode: Executing scheduled move at {scheduled_time}: {scheduled_shade} to Level {scheduled_level}")

            # Convert level to int safely
            try:
                int_level = int(scheduled_level)
            except ValueError:
                logging.error(f"Invalid level in schedule: {scheduled_level}")
                continue

            # Switch blinds if needed
            if active_shade != scheduled_shade:
                swap_blind()

            # If level is 5, move to step 0 (fully open)
            if int_level == 5:
                move_motor_to_step(0)
            # Else, move to the corresponding sensor step
            elif 0 <= int_level < len(sensor_steps):
                move_motor_to_step(sensor_steps[int_level])
            else:
                logging.warning(f"schedule_mode: Invalid level {int_level}, skipping.")

            # Mark this schedule as executed today
            last_schedule_executions[schedule_id] = now.strftime("%Y-%m-%d")

@app.route("/")
def serve_index():
    """Serve the HTML webapp."""
    return send_from_directory("webapp", "index.html")

@app.route("/api/move", methods=["POST"])
def api_move():
    """Service webapp request to move the blind up/down."""
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
    """Service webapp request to change operation mode (auto/manual/schedule/setup)."""
    global op_mode
    op_mode = request.json.get("mode", "auto")
    logging.info(f"Mode switched to {op_mode}")
    return jsonify({"status": "ok", "mode": op_mode})

@app.route("/api/swap", methods=["POST"])
def api_swap():
    """Service webapp request to swap between blackout and sunshade blinds."""
    swap_blind()
    return jsonify({"status": "ok", "active_shade": active_shade})

@app.route("/api/swap_dumb", methods=["POST"])
def api_swap():
    """Service webapp request to swap between blackout and sunshade blinds without moving the motors."""
    swap_blind_dumb()
    return jsonify({"status": "ok", "active_shade": active_shade})

@app.route("/api/sensors", methods=["GET"])
def api_sensors():
    """Service webapp request to return current sensor readings."""
    return jsonify({"readings": read_sensors()})

@app.route("/api/save", methods=["POST"])
def api_save():
    """Service webapp request to save configuration files."""
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
    """Service webapp request to return current app status."""
    return jsonify({
        "mode": op_mode,
        "active_shade": active_shade,
        "step": step
    })

def control_loop():
    """Main control loop which runs the blind operation according to the selected mode."""
    global running
    while running:
        logging.debug(f"main: Blind is currently operating in {op_mode} mode")
        match op_mode:
            case "setup":
                setup_mode()
            case "auto":
                automatic_mode()
            case "schedule":
                schedule_mode()
        time.sleep(1)
        save_settings()
    logging.info("Goodbye!")
    
if __name__ == "__main__":
    # propagate sensor array
    scan_mux()
    # load settings from file, entering setup if necessary
    load_settings()
    # Start the main control loop in its own thread
    threading.Thread(target=control_loop, daemon=True).start()
    # start web app
    app.run(host="0.0.0.0", port=5000, debug=False)
