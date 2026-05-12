# CraneCam — Operator Interface

Web-based operator interface for the 5G crane camera system. Runs on the NVIDIA Jetson Orin Nano and is accessible from any browser on the same network.

```
ZCM2133 camera (RTSP)
    └─ MediaMTX (Jetson) ──WebRTC──► operator.html
                                          │
                                    PTZ / camera API
                                          │
                                    server.py (Flask)
                                          │
                              ┌───────────┴───────────┐
                         Arduino Uno             ISAPI (HTTP)
                         (pan / tilt)             (zoom / image)
```

---

## Files

| File | Purpose |
|------|---------|
| `operator.html` | Single-page operator interface — WebRTC video, PTZ controls, camera image settings, event log |
| `server.py` | Flask server — serves `operator.html`, proxies PTZ commands to Arduino, proxies image settings to camera ISAPI |
| `mediamtx.yml` | MediaMTX configuration — accepts RTSP from camera, outputs WebRTC on port 8889 |

---

## Setup

### 1. Install Python dependencies

```bash
pip install flask requests pyserial --break-system-packages
```

### 2. Start MediaMTX

```bash
./mediamtx mediamtx.yml
```

MediaMTX listens on:
- **8554** — RTSP input (camera pushes here)
- **8889** — WebRTC output (WHEP, browser connects here)

### 3. Start the server

```bash
python3 server.py
```

The server starts on port 5000. Open `http://<jetson-ip>:5000` in a browser.

### 4. Connect

In the **CONN** tab, enter the Jetson's Tailscale IP and click **CONNECT**.

PTZ commands and camera settings are sent back to the same server — no separate address needed.

---

## PTZ API

The interface sends HTTP GET requests to the server:

```
GET /ptz?cmd=<command>&speed=<1-100>
GET /ptz/delta?pan=<degrees>&tilt=<degrees>
```

Pan/tilt commands: `pan_left`, `pan_right`, `tilt_up`, `tilt_down`, `preset_home`, `stop`
Zoom commands: `zoom_in`, `zoom_out`

Pan and tilt go to the Arduino over serial (`P<angle>` / `T<angle>`).
Zoom goes directly to the camera via ISAPI.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| Arrow keys / WASD | Pan / tilt |
| `+` / `-` | Zoom in / out |
| `Space` | Stop |
| `H` | Home preset |
| Scroll wheel on video | Zoom |
| Click on video | Aim to clicked point |

---

## Ports

| Port | Service |
|------|---------|
| 5000 | Flask server (operator interface + PTZ/camera API) |
| 8554 | RTSP input to MediaMTX |
| 8889 | WebRTC output from MediaMTX (WHEP) |
