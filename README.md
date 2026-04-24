# Crane Camera — Operator Interface

Web-based operator GUI for viewing a live camera stream and sending PTZ commands.

```
[RTSP camera / source] → [MediaMTX] → [WebRTC] → [operator.html]
                                                         ↓
                                              [PTZ HTTP endpoint]
```

---

## Files

| File | Purpose |
|------|---------|
| `operator.html` | Operator GUI — WebRTC video, PTZ d-pad, zoom, presets, event log |
| `mediamtx.yml`  | MediaMTX config — low-latency WebRTC relay for an RTSP source |

---

## Prerequisites

### MediaMTX (WebRTC relay)

Required if your camera outputs RTSP and the browser needs WebRTC.

Download the Windows zip from:
https://github.com/bluenviron/mediamtx/releases/latest

Look for: `mediamtx_vX.X.X_windows_amd64.zip`

Extract `mediamtx.exe` into this folder (next to `mediamtx.yml`).

Or with winget:
```
winget install bluenviron.mediamtx
```

---

## Setup

### 1. Start MediaMTX

```
mediamtx mediamtx.yml
```

MediaMTX listens on:
- **8554** — RTSP input
- **8889** — WebRTC output (WHEP)

### 2. Push your RTSP stream into MediaMTX

Point your camera or FFmpeg at:
```
rtsp://localhost:8554/crane
```

Example with FFmpeg (test pattern):
```
ffmpeg -re -f lavfi -i testsrc2=size=1920x1080:rate=30 \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -b:v 4000k -g 30 -f rtsp -rtsp_transport tcp rtsp://localhost:8554/crane
```

### 3. Open the operator page

Open `operator.html` in Chrome or Edge (double-click or drag to browser).

In the **Connection** panel, set:
- **MediaMTX host** — IP of the machine running MediaMTX (default `192.168.1.147`)
- **Stream path** — RTSP path (default `crane`)
- **PTZ server host** — `host:port` of your PTZ HTTP endpoint (default `localhost:5000`)

Click **CONNECT**.

---

## PTZ API

The GUI sends HTTP GET requests to:
```
http://<PTZ_HOST>/ptz?cmd=<command>&speed=<1-100>
```

Commands: `pan_left`, `pan_right`, `tilt_up`, `tilt_down`, `zoom_in`, `zoom_out`, `stop`, `preset_home`

The PTZ endpoint must respond with HTTP 200 on success. Response body is ignored.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| Arrow keys / WASD | Pan / tilt |
| `+` / `-` | Zoom in / out |
| Space | Stop |
| `H` | Home preset |

---

## Two-machine setup (camera PC vs operator PC)

Run MediaMTX on the camera PC. Open `operator.html` on the operator PC and set **MediaMTX host** to the camera PC's IP address.

---

## Ports

| Port | Service |
|------|---------|
| 8554 | RTSP (camera → MediaMTX) |
| 8889 | WebRTC (MediaMTX → browser) |
| 5000 | PTZ HTTP endpoint (default, configurable in GUI) |
