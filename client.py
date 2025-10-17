# ECE 441 Fall 2025

import time
import board
import adafruit_tca9548a
import adafruit_veml7700
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import logging

# set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# CircuitPython prep
i2c = board.I2C()
mux = adafruit_tca9548a.TCA9548A(i2c)
motor_shield = MotorKit()

# global variables
channels = 5
sunlight_threshold = 2500 # any lux reading over this number is considered "sunlight"
sensor_array = [None] * 5 # dummy sensor variables, the initial scan will propagate them
op_mode = "auto" # auto, manual, or setup
active_shade = "sunshade" # either "sunshade" or "blackout". stepper1 is the sunshade, stepper2 is the blackout
step = 0 # how many steps the motor has taken away from its resting position. 0 means the shade is all the way open.

# read the previously saved setup settings from file, filling in global variables as necessary.
# also check how many sensors are currently being used, if it doesn't match the
# previous settings, force the user to run setup again
def read_settings():
    # NOT YET IMPLEMENTED
    pass

# propagate sensor array
def scan_mux():
    for channel in range(channels):
        logging.info(f"scan_mux: attempting to access channel {channel}")
        if mux[channel].try_lock():
            addresses = mux[channel].scan()
            mux[channel].unlock()
            if ("0x10" in addresses):
                logging.info(f"scan_mux: Light sensor was detected on channel {channel}")
                # replace None in the sensor_array with a proper sensor object
                sensor_array[channel] = adafruit_veml7700.VEML7700(mux[channel])
            else:
                logging.info(f"scan_mux: No light sensor detected on channel {channel}")

# returns an array of the current lux readings from all sensors
def read_sensors():
    out = [None] * 5
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
    var1 = new_step - step
    logging.info(f"move_motor_to_step: Moving from step {step} to {new_step} (delta {var1})")
    # if positive, move up
    if var1 > 0:
        for i in range(var1):
            if active_shade == "sunshade":
                motor_shield.stepper1.onestep(direction=stepper.FORWARD, style=stepper.SINGLE)
            else:
                motor_shield.stepper2.onestep(direction=stepper.FORWARD, style=stepper.SINGLE)
            step -= 1
            time.sleep(0.01)
    # if negative, move down
    elif var1 < 0:
        for i in range(-var1):
            if active_shade == "sunshade":
                motor_shield.stepper1.onestep(direction=stepper.BACKWARD, style=stepper.SINGLE)
            else:
                motor_shield.stepper2.onestep(direction=stepper.BACKWARD, style=stepper.SINGLE)
            step += 1
            time.sleep(0.01)

if __name__ == "__main__":
    scan_mux()
    move_motor_to_step(360)
    move_motor_to_step(0)
    while True:
        _ = read_sensors()