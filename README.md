# Crane Camera Simulation — Windows Setup

Simulates the full pipeline on a single Windows PC:

```
[FFmpeg test stream] → [MediaMTX] → [WebRTC] → [Operator HTML page]
                                         ↑
                              [PTZ mock server (Python)]
```

No hardware needed. Everything runs locally.

---

## 1. Install prerequisites (one-time)

### FFmpeg
Download the Windows build from https://www.gyan.dev/ffmpeg/builds/
Get the "release essentials" zip, extract it, and add the `bin\` folder to your PATH.

Or with winget:
```
winget install Gyan.FFmpeg
```

Verify:
```
ffmpeg -version
```

### MediaMTX
Download the Windows zip from:
https://github.com/bluenviron/mediamtx/releases/latest

Look for: `mediamtx_vX.X.X_windows_amd64.zip`

Extract it into this folder (next to this README). You should have:
```
sim\
  mediamtx.exe
  mediamtx.yml    ← our custom config (included)
  README.md
  start_sim.bat
  ptz_mock.py
  operator.html
```

Or with winget:
```
winget install bluenviron.mediamtx
```
(If installed via winget, mediamtx.exe will be in your PATH — the .bat script handles both cases.)

### Python (for the PTZ mock server)
Python 3.8 or newer. Download from https://www.python.org/downloads/
Make sure "Add Python to PATH" is checked during install.

Verify:
```
python --version
```

---

## 2. Start the simulation

Double-click `start_sim.bat` — it opens three terminal windows:

| Window | What it does |
|--------|--------------|
| MediaMTX | Receives RTSP from FFmpeg, serves WebRTC to browser |
| FFmpeg  | Generates a 1080p test pattern with live clock (fake camera) |
| PTZ Mock | Receives PTZ commands from the operator page, prints them |

Wait about 5 seconds for everything to start, then open the operator page:

```
operator.html   ← open this in Chrome or Edge (double-click or drag to browser)
```

---

## 3. What you should see

- Live video (colour test pattern with timestamp) playing in the browser
- PTZ control buttons on the right panel
- When you click a PTZ button, the PTZ Mock terminal prints the command
- Latency counter in the top bar (end-to-end, measured by timestamp difference)

---

## 4. Using a real video file instead of the test pattern

Edit `start_sim.bat` and find the FFmpeg line. Replace:

```
-f lavfi -i "testsrc2=size=1920x1080:rate=30,drawtext=..."
```

With:

```
-re -stream_loop -1 -i "C:\path\to\your\video.mp4"
```

---

## 5. Simulating bad 5G conditions

Download Clumsy (free Windows network emulator):
https://jagt.github.io/clumsy/

Run it and apply to loopback traffic:
- Lag: 80ms (simulates 5G round-trip)
- Drop: 1–2% (simulates mobile packet loss)
- Throttle: to simulate bandwidth limits

Watch whether the WebRTC stream in the browser degrades gracefully.

---

## 6. Testing across two PCs (simulates Jetson vs operator station)

Run MediaMTX + FFmpeg on PC A (the "Jetson").
Open operator.html on PC B, but change the server address in the page:

In operator.html, find:
```javascript
const MEDIAMTX_HOST = "localhost";
```
Change it to PC A's local IP address.

---

## Ports used

| Port  | Service                  |
|-------|--------------------------|
| 8554  | RTSP (FFmpeg → MediaMTX) |
| 8889  | WebRTC (MediaMTX → browser) |
| 5000  | PTZ mock HTTP server     |

Make sure Windows Firewall allows these if testing across two machines.
