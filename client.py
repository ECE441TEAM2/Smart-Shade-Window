# ECE 441 Fall 2025

import board
import adafruit_tca9548a

i2c = board.I2C()
mux = adafruit_tca9548a.TCA9548A(i2c)

# this is just a testing thing for now
# if this doesnt work then something is fucked
for channel in range(8):
    if mux[channel].try_lock():
        print("Channel {}:".format(channel), end="")
        addresses = mux[channel].scan()
        print([hex(address) for address in addresses if address != 0x70])
        mux[channel].unlock()