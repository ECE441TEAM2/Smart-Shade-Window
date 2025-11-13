# Intro
This repository consists of all the block diagrams and code used for the project on ECE 441.

## Smart-Shade Window Overview
- Features logic for two smart shade windows named the sunshade and the blackout shade.
- Controls NEMA-17 Stepper Motors from Adafruit.
- Reads VEML7700 Light Sensors from Adafruit (upto 5).
- Self-hosted via flask-api at port 5000.
- Use of Tailscale to provide remote access and private network port forwarding.
- Deployed on any device with GPIO pins and I2C bus.

## Installation
Prerequesites:
- Raspberry Pi or compatible device with GPIO and I2C support.
- Storage enough to occupy the Python's CircuitPython and Flask API library alongside Python.
- Tailscale setup with both your compatible hosting device and client device (PC/Phone).

Clone the repository into a desired folder via 
```git clone https://github.com/ECE441TEAM2/Smart-Shade-Window```

For a single instance, run python3 client.py on the root of the repository.

To keep it persistant on boot, either initialize a start script with init.d or use systemd.

Access the hosted webserver via <machine-tailscale-ip>:5000.

You may also use tailscale serve, or a reverse proxy service such as ngnix or caddy to
provision a certificate and authenticate the IP as a URL with https support.

## Licensing
All code in this repository is under the Unlicense License unless wherever an explicit licensing is included.