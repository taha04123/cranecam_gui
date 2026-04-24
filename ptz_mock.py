"""
ptz_mock.py — Simulates the PTZ control endpoint on the Jetson.

When a command arrives, it:
  1. Prints it to the terminal (for debugging)
  2. Writes it to ptz_cmd.txt in the same folder

FFmpeg watches ptz_cmd.txt with the drawtext filter (textfile + reload=1)
and burns the current command directly into the encoded video frames.
This means the indicator is part of the stream, visible to any viewer.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import json
import os
import threading
from datetime import datetime

VALID_COMMANDS = {
    "pan_left", "pan_right",
    "tilt_up", "tilt_down",
    "zoom_in", "zoom_out",
    "stop",
    "preset_home",
}

# Maps command name to what gets burned into the video
CMD_DISPLAY = {
    "pan_left":    "<  PAN LEFT",
    "pan_right":   "PAN RIGHT  >",
    "tilt_up":     "^  TILT UP",
    "tilt_down":   "TILT DOWN  v",
    "zoom_in":     "[+]  ZOOM IN",
    "zoom_out":    "[-]  ZOOM OUT",
    "stop":        "[ STOP ]",
    "preset_home": "[*] HOME",
}

# Path to the text file FFmpeg is watching
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CMD_FILE   = os.path.join(SCRIPT_DIR, "ptz_cmd.txt")

# How long the command stays visible in the video (seconds)
DISPLAY_DURATION = 1.5

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# Timer handle — clears the text file after DISPLAY_DURATION
_clear_timer = None
_lock = threading.Lock()

def write_cmd(text):
    """Write text to the file FFmpeg is watching."""
    with open(CMD_FILE, "w", encoding="utf-8") as f:
        f.write(text)

def clear_cmd():
    """Clear the command file so nothing is shown."""
    write_cmd("")

def show_command(cmd):
    """Write command to file, then schedule a clear after DISPLAY_DURATION."""
    global _clear_timer
    with _lock:
        if _clear_timer:
            _clear_timer.cancel()
        write_cmd(CMD_DISPLAY.get(cmd, cmd.upper()))
        _clear_timer = threading.Timer(DISPLAY_DURATION, clear_cmd)
        _clear_timer.daemon = True
        _clear_timer.start()


class PTZHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/health":
            self._respond(200, {"status": "ok"})
            return

        if parsed.path == "/ptz":
            params = urllib.parse.parse_qs(parsed.query)
            cmd    = params.get("cmd",   ["unknown"])[0]
            speed  = params.get("speed", ["50"])[0]
            ts     = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            if cmd in VALID_COMMANDS:
                show_command(cmd)
                print(f"{GREEN}{BOLD}[{ts}] PTZ{RESET}  "
                      f"{CYAN}{cmd:<15}{RESET}  speed={speed}  "
                      f"→ written to ptz_cmd.txt")
                self._respond(200, {"status": "ok", "cmd": cmd, "speed": speed})
            else:
                print(f"{RED}[{ts}] UNKNOWN: {cmd}{RESET}")
                self._respond(400, {"status": "error", "msg": f"Unknown: {cmd}"})
            return

        self._respond(404, {"status": "error", "msg": "Not found"})

    def _respond(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    # Start with empty command file
    clear_cmd()
    print(f"\n{BOLD}PTZ Mock Server{RESET}")
    print(f"Commands are burned into the video stream via ptz_cmd.txt\n")
    print(f"Listening on  {CYAN}http://localhost:5000/ptz{RESET}")
    print(f"Command file  {CYAN}{CMD_FILE}{RESET}")
    print(f"Display time  {DISPLAY_DURATION}s per command\n")
    print(f"{YELLOW}Waiting for commands...{RESET}\n")
    print("-" * 55)

    try:
        HTTPServer(("0.0.0.0", 5000), PTZHandler).serve_forever()
    except KeyboardInterrupt:
        clear_cmd()
        print(f"\n{YELLOW}Stopped.{RESET}")
