# ECE 441 Fall 2025

import time
import board
import adafruit_tca9548a
import adafruit_veml7700
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper

i2c = board.I2C()
mux = adafruit_tca9548a.TCA9548A(i2c)
light_sensor = adafruit_veml7700.VEML7700(mux[0])
motor_shield = MotorKit()

# test the I2C multiplexer
for channel in range(8):
    if mux[channel].try_lock():
        print("Channel {}:".format(channel), end="")
        addresses = mux[channel].scan()
        print([hex(address) for address in addresses if address != 0x70])
        print([type(address) for address in addresses])
        mux[channel].unlock()

# test the light sensor in MUX slot 0
for i in range(100):
    print("Light Reading:", light_sensor.lux)
    time.sleep(0.20)

# test the stepper motor
for i in range(100):
    motor_shield.stepper1.onestep()
    motor_shield.stepper2.onestep()
    time.sleep(0.01)
