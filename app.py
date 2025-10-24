# Basic Python Backend to save JSON request
from flask import Flask, request, jsonify
import json, os

app = Flask(__name__)

@app.route("/save-config", methods=["POST"])
def save_config():
    data = request.get_json()
    os.makedirs("config", exist_ok=True)
    with open("config/setup.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Config saved:", data)
    return jsonify({"status": "saved"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

