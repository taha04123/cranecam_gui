"""
PTZ server for cranecam_gui operator interface.
Listens on port 5000 and translates HTTP PTZ commands to Arduino serial commands.

Usage:
    pip install flask pyserial
    python ptz_server.py

Arduino serial protocol:
    P<angle>\n  — set pan servo  (pin 5) to angle (0–180)
    T<angle>\n  — set tilt servo (pin 6) to angle (0–180)
"""

import time
import json
import serial
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify, Response

SERIAL_PORT  = "COM3"
BAUD_RATE    = 9600
FLASK_PORT   = 5000
ZOOM_PROXY   = "http://100.83.7.52:5001/zoom"  # Jetson zoom proxy

app = Flask(__name__)

# Open serial connection to Arduino
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Wait for Arduino to reset after serial connect
    print(f"[ptz_server] Connected to Arduino on {SERIAL_PORT}")
except serial.SerialException as e:
    print(f"[ptz_server] WARNING: Could not open {SERIAL_PORT}: {e}")
    ser = None

# Current servo positions (degrees)
pan_angle  = 90
tilt_angle = 90


def send_zoom(cmd: str):
    """Forward zoom command to the Jetson zoom proxy."""
    try:
        url = f"{ZOOM_PROXY}?cmd={cmd}"
        urllib.request.urlopen(url, timeout=2)
        print(f"[zoom] {cmd}")
    except Exception as e:
        print(f"[zoom] error: {e}")


def send_serial(cmd: str):
    """Send a command string to the Arduino over serial."""
    if ser and ser.is_open:
        ser.write((cmd + "\n").encode())
        ser.flush()
        print(f"[serial] {cmd}")
    else:
        print(f"[serial] (no connection) would send: {cmd}")


@app.after_request
def add_cors(response):
    """Allow cross-origin requests from operator.html (file:// or any origin)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response


@app.route("/ptz")
def ptz():
    global pan_angle, tilt_angle

    cmd   = request.args.get("cmd", "")
    speed = int(request.args.get("speed", 50))

    # Map speed (1–100) to angle increment (1–10 degrees)
    increment = max(1, speed // 10)

    if cmd == "pan_right":
        pan_angle = min(180, pan_angle + increment)
        send_serial(f"P{pan_angle}")

    elif cmd == "pan_left":
        pan_angle = max(0, pan_angle - increment)
        send_serial(f"P{pan_angle}")

    elif cmd == "tilt_up":
        tilt_angle = min(180, tilt_angle + increment)
        send_serial(f"T{tilt_angle}")

    elif cmd == "tilt_down":
        tilt_angle = max(0, tilt_angle - increment)
        send_serial(f"T{tilt_angle}")

    elif cmd == "stop":
        send_zoom("stop")  # Stop zoom motor too

    elif cmd == "preset_home":
        pan_angle  = 90
        tilt_angle = 90
        send_serial("P90")
        send_serial("T90")

    elif cmd == "zoom_in":
        send_zoom("in")

    elif cmd == "zoom_out":
        send_zoom("out")

    else:
        return jsonify({"ok": False, "error": f"Unknown command: {cmd}"}), 400

    print(f"[ptz] cmd={cmd} speed={speed} → pan={pan_angle} tilt={tilt_angle}")
    return jsonify({"ok": True, "cmd": cmd, "pan": pan_angle, "tilt": tilt_angle})


@app.route("/ptz/delta")
def ptz_delta():
    global pan_angle, tilt_angle

    try:
        pan_delta  = float(request.args.get("pan",  0))
        tilt_delta = float(request.args.get("tilt", 0))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid delta values"}), 400

    if pan_delta != 0:
        pan_angle = int(min(180, max(0, pan_angle + pan_delta)))
        send_serial(f"P{pan_angle}")

    if tilt_delta != 0:
        tilt_angle = int(min(180, max(0, tilt_angle + tilt_delta)))
        send_serial(f"T{tilt_angle}")

    print(f"[ptz/delta] pan_delta={pan_delta:+.0f} tilt_delta={tilt_delta:+.0f} → pan={pan_angle} tilt={tilt_angle}")
    return jsonify({"ok": True, "pan": pan_angle, "tilt": tilt_angle})


@app.route("/camera")
def camera():
    cmd   = request.args.get("cmd",   "")
    value = request.args.get("value", "")
    level = request.args.get("level", "")

    try:
        params = urllib.parse.urlencode({"cmd": cmd, "value": value, "level": level})
        url = f"http://100.83.7.52:5001/camera?{params}"
        with urllib.request.urlopen(url, timeout=4) as resp:
            body        = resp.read()
            content_type = resp.headers.get("Content-Type", "application/json")
        return Response(body, content_type=content_type)
    except Exception as e:
        print(f"[camera] error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    print(f"[ptz_server] Starting on http://localhost:{FLASK_PORT}")
    app.run(host="0.0.0.0", port=FLASK_PORT)
