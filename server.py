# ECE 441 Fall 2025

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import threading
import logging
import os
from client import start_client, move_motor_to_step, swap_blind, automatic_mode, schedule_mode, save_settings
from client import op_mode, active_shade, step, running

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
web_confirm_event = threading.Event()

# set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

def wait_for_web_confirm():
    """Called by setup_mode to wait for user confirmation."""
    web_confirm_event.clear()
    web_confirm_event.wait()  # block until 'confirm' received

@app.route("/")
def serve_index():
    return send_from_directory('static', 'index.html')

@socketio.on("connect")
def on_connect():
    emit("status", {"connected": True})
    logging.info("Web client connected.")

@socketio.on("disconnect")
def on_disconnect():
    logging.info("Web client disconnected.")

@socketio.on("command")
def on_command():
    global op_mode, running, step

    data = request.get_json()
    command = data.get("command")
    logging.info(f"Received command: {command}")

    if command == "up":
        move_motor_to_step(step - 1)
    elif command == "down":
        move_motor_to_step(step + 1)
    elif command == "swap":
        swap_blind()
    elif command == "auto":
        op_mode = "auto"
    elif command == "manual":
        op_mode = "manual"
    elif command == "setup":
        op_mode = "setup"
    elif command == "schedule":
        op_mode = "schedule"
    elif command == "confirm":
        web_confirm_event.set()
    elif command == "quit":
        running = False
        emit("status", {"stopping": True})
    else:
        emit("status", {"error": f"Unknown command {command}"})

    emit("status", {"mode": op_mode, "shade": active_shade, "step": step}, broadcast=True)

@socketio.on("get_status")
def handle_status():
    emit("status", {"mode": op_mode, "shade": active_shade, "step": step})

if __name__ == "__main__":
    threading.Thread(target=start_client, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000)