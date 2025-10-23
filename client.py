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

# we may not need this stuff after adding the web app communication
import keyboard
import threading

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

# Save the active setup settings to a file, to be loaded on next startup.
def save_settings():
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

# load the previously saved setup settings from file, filling in global variables as necessary.
# also check how many sensors are currently being used, if it doesn't match the
# previous settings, force the user to run setup again
def load_settings():
    global step
    global active_shade
    global op_mode
    global sensor_steps

    if not os.path.exists(SETTINGS_FILE):
        logging.info("Settings file not found. Launching setup.")
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

# returns an array which replaces every sensor instance in the array with just a 1, which is actually saveable to json
def sensor_mask_helper():
    return [None if x is None else 1 for x in sensor_array]

# propagate sensor array
def scan_mux():
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

# returns an array of the current lux readings from all sensors
def read_sensors():
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

# given a new step value, move the motor to that step
def move_motor_to_step(new_step):
    global step
    var1 = new_step - step
    logging.info(f"move_motor_to_step: Moving from step {step} to {new_step} (delta {var1})")
    # if positive, move down
    if var1 > 0:
        for i in range(var1):
            if active_shade == "sunshade":
                motor_shield.stepper1.onestep(direction=stepper.BACKWARD, style=stepper.SINGLE)
            else:
                motor_shield.stepper2.onestep(direction=stepper.BACKWARD, style=stepper.SINGLE)
            step += 1
            time.sleep(0.01)
    # if negative, move up
    elif var1 < 0:
        for i in range(-var1):
            if active_shade == "sunshade":
                motor_shield.stepper1.onestep(direction=stepper.FORWARD, style=stepper.SINGLE)
            else:
                motor_shield.stepper2.onestep(direction=stepper.FORWARD, style=stepper.SINGLE)
            step -= 1
            time.sleep(0.01)
    return

# Switches the currently active blind to the the other blind.
# The original blind is moved back to its starting point (0) and the new blind moves
# to the same step position as the original blind.
def swap_blind():
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

# Uses the web app to set up variables used by the other modes.
def setup_mode():
    # NOT YET IMPLEMENTED
    pass

# Iterates through each sensor's readings from top to bottom.
# For the first one that it finds is too bright, the blind is moved to match that sensor's height.
def automatic_mode():
    for i, lux in enumerate(read_sensors()):
        if lux is None:
            continue
        if lux > sunlight_threshold:
            logging.debug(f"automatic_mode: Sensor {i} detected sunlight ({lux} lux). Adjusting shade.")
            move_motor_to_step(sensor_steps[i])
            return

# Allows the user to use up/down buttons to move the blind manually.
def manual_mode():
    # NOT YET IMPLEMENTED
    pass

# Follows the schedule imported during setup/created by the web app.
def schedule_mode():
    # NOT YET IMPLEMENTED
    pass

# A separate thread to listen to keypresses for manual control.
# In the future, this can be replaced with web app communication.
# Keypress controls: A for automatic mode, M for manual mode, S for setup mode, C for scheduler mode, B for blind swap
# In manual mode, press up and down arrows to move the blind
# Q to quit the application
def keypress_listener():
    global op_mode
    global active_shade

    while running:
        if keyboard.is_pressed('a'): # switch to automatic mode
            op_mode = "auto"
        elif keyboard.is_pressed('m'): # switch to manual mode
            op_mode = "manual"
        elif keyboard.is_pressed('s'): # switch to setup mode
            op_mode = "setup"
        elif keyboard.is_pressed('c'): # switch to schedule mode
            op_mode = "schedule"
        elif keyboard.is_pressed('b'): # swap blinds
            swap_blind()
        elif keyboard.is_pressed('q'): # quit
            running = False

        # manual mode controls
        if op_mode == "manual":
            if keyboard.is_pressed('up'):
                move_motor_to_step(step - 1)
            elif keyboard.is_pressed('down'):
                move_motor_to_step(step + 1)

        time.sleep(0.1)

if __name__ == "__main__":
    # first check how many sensors there are and propagate the sensor array
    scan_mux()
    # then attempt to load settings from file (if file doesnt exist or sensor quantity mismatch, this also runs setup)
    load_settings()

    # create a separate thread to listen for keypresses (means they aren't affected by waits)
    # In the future, can replace this with web app communication.
    listener = threading.Thread(target=keypress_listener, daemon=True).start()

    while running:
        logging.debug("main: Blind is currently operating in {op_mode} mode")
        match op_mode:
            case "setup":
                setup_mode()
            case "automatic":
                automatic_mode()
            case "schedule":
                schedule_mode()
            # manual mode is completely handled within the keypress listener
        time.sleep(1)

    # shutdown sequence
    # save the blind settings
    save_settings()