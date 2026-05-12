"""
CraneCam server — Flask process running on the Jetson Orin Nano.

Serves operator.html and handles all camera and PTZ commands:
  - /        : serves the operator web interface
  - /ptz     : pan/tilt via Arduino serial, zoom via ISAPI
  - /ptz/delta: click-to-aim pan/tilt offset
  - /camera  : read and write all ISAPI image settings

Hardware:
    Jetson Orin Nano  192.168.2.1
    Camera            192.168.2.68  (Hikvision ISAPI, HTTP Digest auth)
    Arduino Uno       /dev/ttyACM0  (USB serial, 9600 baud)

Usage:
    pip install flask requests pyserial --break-system-packages
    python3 server.py
"""

import re
import time
import sys
from flask import Flask, request, jsonify, Response, send_from_directory
import requests
from requests.auth import HTTPDigestAuth
import serial

# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_IP   = '192.168.2.68'
CAMERA_USER = 'admin'
CAMERA_PASS = 'sebandtah2792'
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE   = 9600
FLASK_PORT  = 5000

# ISAPI endpoint URLs for the ZCM2133 camera
IMG_URL         = f'http://{CAMERA_IP}/ISAPI/Image/channels/1'
IMG_COLOR_URL   = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/color'
IMG_IRCUT_URL   = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/IrcutFilter'
IMG_DEHAZE_URL  = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/dehaze'
IMG_FLIP_URL    = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/ImageFlip'
IMG_FOCUS_URL   = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/focusConfiguration'
IMG_WB_URL      = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/WhiteBalance'
IMG_NOISE_URL   = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/noiseReduce'
IMG_WDR_URL     = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/WDR'
IMG_HLC_URL     = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/HLC'
IMG_RESTORE_URL = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/restore'
PTZ_URL         = f'http://{CAMERA_IP}/ISAPI/PTZCtrl/channels/1/absolute'

AUTH    = HTTPDigestAuth(CAMERA_USER, CAMERA_PASS)
HEADERS = {'Content-Type': 'application/xml'}

# Zoom state — tracked server-side because the camera has no GET for current zoom
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 1, 33, 1
current_zoom = 1

# Pan/tilt state — servo angles in degrees, 0–180, centre at 90
pan_angle  = 90
tilt_angle = 90

app = Flask(__name__)


# ── Startup init ──────────────────────────────────────────────────────────────

def init_camera():
    """Reset zoom to 1x and set 50 Hz power-line frequency on startup."""
    try:
        xml = ('<PTZData><AbsoluteHigh><elevation>0</elevation><azimuth>0</azimuth>'
               '<absoluteZoom>10</absoluteZoom></AbsoluteHigh></PTZData>')
        r = requests.put(PTZ_URL, auth=AUTH, data=xml, headers=HEADERS, timeout=5)
        print(f'[init] zoom reset to 1x → {r.status_code}')
    except Exception as e:
        print(f'[init] WARNING zoom reset failed: {e}')

    # 50 Hz is the EU/marine default; avoids fluorescent-light flicker artefacts
    try:
        current = requests.get(IMG_URL, auth=AUTH, timeout=5).text
        if '<powerLineFrequency>' in current or '<powerLineFrequency/>' in current:
            modified = re.sub(
                r'<powerLineFrequency(?:>[^<]*</powerLineFrequency>|\s*/>)',
                '<powerLineFrequency>50hz</powerLineFrequency>', current)
            modified = re.sub(r'<\?xml[^?]*\?>\s*', '', modified).strip()
            r = requests.put(IMG_URL, auth=AUTH, data=modified, headers=HEADERS, timeout=5)
            print(f'[init] powerLineFrequency=50hz → {r.status_code}')
    except Exception as e:
        print(f'[init] WARNING powerLineFrequency failed: {e}')


# ── Serial (Arduino servo controller) ────────────────────────────────────────

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print(f'[serial] connected on {SERIAL_PORT}')
except Exception as e:
    print(f'[serial] WARNING: {e}')
    ser = None


def send_serial(cmd):
    """Send a command string to the Arduino. Fails silently if not connected."""
    if ser and ser.is_open:
        ser.write((cmd + '\n').encode())
        ser.flush()
        print(f'[serial] {cmd}')
    else:
        print(f'[serial] (offline) would send: {cmd}')


# ── ISAPI helpers ─────────────────────────────────────────────────────────────

def cam_get(url):
    """GET an ISAPI endpoint and return the response body as text."""
    r = requests.get(url, auth=AUTH, timeout=5)
    print(f'[cam_get] {url} → {r.status_code}', file=sys.stderr)
    if r.status_code != 200:
        print(f'[cam_get] error body: {r.text}', file=sys.stderr)
    return r.text


def cam_put(url, xml):
    """PUT XML to an ISAPI endpoint. Strips the XML declaration before sending
    because the ZCM2133 firmware silently rejects PUT bodies that include it."""
    xml = re.sub(r'<\?xml[^?]*\?>\s*', '', xml).strip()
    print(f'[cam_put] {url}', file=sys.stderr)
    print(f'[cam_put] body: {xml}', file=sys.stderr)
    r = requests.put(url, auth=AUTH, data=xml, headers=HEADERS, timeout=5)
    ok = '<statusCode>1</statusCode>' in r.text
    print(f'[cam_put] response {r.status_code}: {r.text}', file=sys.stderr)
    return ok, r.text


def img_replace(xml_str, tag, new_val):
    """Replace a single leaf tag value in an XML string.
    Handles both <tag>value</tag> and self-closing <tag/> forms."""
    replacement = f'<{tag}>{new_val}</{tag}>'
    result = re.sub(
        rf'<{re.escape(tag)}>[^<]*</{re.escape(tag)}>',
        replacement, xml_str
    )
    if result != xml_str:
        return result
    return re.sub(rf'<{re.escape(tag)}\s*/>', replacement, xml_str)


def img_replace_in(xml_str, parent, tag, new_val):
    """Replace a leaf tag nested inside a specific parent element.
    Injects the tag if it is missing from the parent block."""
    replacement_tag = f'<{tag}>{new_val}</{tag}>'
    tag_pattern = re.compile(rf'<{re.escape(tag)}(?:\s*/>|>[^<]*</{re.escape(tag)}>)')

    def sub(m):
        block = m.group(0)
        if tag_pattern.search(block):
            return img_replace(block, tag, new_val)
        return block.replace(f'</{parent}>', f'{replacement_tag}</{parent}>')

    result = re.sub(
        rf'<{re.escape(parent)}[^>]*>.*?</{re.escape(parent)}>',
        sub, xml_str, flags=re.DOTALL
    )
    if result != xml_str:
        return result
    # Parent is self-closing — expand it and inject the child tag
    return re.sub(
        rf'<{re.escape(parent)}\s*/>',
        f'<{parent}>{replacement_tag}</{parent}>',
        xml_str
    )


# The ZCM2133 requires a full GET-modify-PUT cycle for most image settings:
# submitting only the changed field returns HTTP 400. These helpers fetch the
# current document, apply a transform function, and PUT the full result back.

def img_modify(fn):
    current = cam_get(IMG_URL)
    return cam_put(IMG_URL, fn(current))

def focus_modify(fn):
    current = cam_get(IMG_FOCUS_URL)
    return cam_put(IMG_FOCUS_URL, fn(current))

def ircut_modify(fn):
    current = cam_get(IMG_IRCUT_URL)
    if '<IrcutFilter' not in current:
        print(f'[ircut_modify] unexpected response: {current[:300]}', file=sys.stderr)
        return False, current
    modified = fn(current)
    print(f'[ircut_modify] PUT body: {modified}', file=sys.stderr)
    return cam_put(IMG_IRCUT_URL, modified)

def noise_modify(fn):
    current = cam_get(IMG_NOISE_URL)
    return cam_put(IMG_NOISE_URL, fn(current))

def wdr_modify(fn):
    current = cam_get(IMG_WDR_URL)
    return cam_put(IMG_WDR_URL, fn(current))

def hlc_modify(fn):
    current = cam_get(IMG_HLC_URL)
    return cam_put(IMG_HLC_URL, fn(current))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    res = send_from_directory('.', 'operator.html')
    res.headers['Cache-Control'] = 'no-store'
    return res


@app.route('/ptz')
def ptz():
    """Pan/tilt via Arduino serial; zoom via ISAPI PTZ absolute endpoint."""
    global pan_angle, tilt_angle
    cmd   = request.args.get('cmd', '')
    speed = int(request.args.get('speed', 50))
    inc   = 5

    if   cmd == 'pan_right':   pan_angle  = min(180, pan_angle  + inc); send_serial(f'P{pan_angle}')
    elif cmd == 'pan_left':    pan_angle  = max(0,   pan_angle  - inc); send_serial(f'P{pan_angle}')
    elif cmd == 'tilt_up':     tilt_angle = min(180, tilt_angle + inc); send_serial(f'T{tilt_angle}')
    elif cmd == 'tilt_down':   tilt_angle = max(0,   tilt_angle - inc); send_serial(f'T{tilt_angle}')
    elif cmd == 'preset_home': pan_angle = tilt_angle = 90; send_serial('P90'); send_serial('T90')
    elif cmd == 'zoom_in':     return _zoom('in')
    elif cmd == 'zoom_out':    return _zoom('out')
    elif cmd == 'stop':        pass
    else:                      return jsonify({'ok': False, 'error': f'Unknown: {cmd}'}), 400

    print(f'[ptz] {cmd} speed={speed} → pan={pan_angle} tilt={tilt_angle}')
    return jsonify({'ok': True, 'cmd': cmd, 'pan': pan_angle, 'tilt': tilt_angle})


@app.route('/ptz/delta')
def ptz_delta():
    """Apply a relative pan/tilt offset — used by the click-to-aim feature."""
    global pan_angle, tilt_angle
    try:
        pd = float(request.args.get('pan',  0))
        td = float(request.args.get('tilt', 0))
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid delta'}), 400
    if pd: pan_angle  = int(min(180, max(0, pan_angle  + pd))); send_serial(f'P{pan_angle}')
    if td: tilt_angle = int(min(180, max(0, tilt_angle + td))); send_serial(f'T{tilt_angle}')
    print(f'[ptz/delta] pan={pan_angle} tilt={tilt_angle}')
    return jsonify({'ok': True, 'pan': pan_angle, 'tilt': tilt_angle})


def _zoom(cmd):
    """Send an absolute zoom position to the camera via ISAPI.
    ISAPI absoluteZoom uses a scale of 10 per optical zoom step (1x = 10, 33x = 330)."""
    global current_zoom
    if   cmd == 'in':  current_zoom = min(ZOOM_MAX, current_zoom + ZOOM_STEP)
    elif cmd == 'out': current_zoom = max(ZOOM_MIN, current_zoom - ZOOM_STEP)
    abs_zoom = current_zoom * 10
    xml = (f'<PTZData><AbsoluteHigh><elevation>0</elevation><azimuth>0</azimuth>'
           f'<absoluteZoom>{abs_zoom}</absoluteZoom></AbsoluteHigh></PTZData>')
    ok, _ = cam_put(PTZ_URL, xml)
    print(f'[zoom] {cmd} → {current_zoom}x (absoluteZoom={abs_zoom})')
    return jsonify({'ok': ok, 'cmd': cmd, 'zoom': current_zoom})


@app.route('/camera')
def camera():
    """Proxy for all ISAPI image settings. Accepts GET (read) and write commands."""
    cmd   = request.args.get('cmd',   '')
    value = request.args.get('value', '')
    level = request.args.get('level', '')

    # ── Read endpoints ────────────────────────────────────────────────────────
    if cmd == 'get_settings':
        return Response(cam_get(IMG_URL),        content_type='application/xml')
    elif cmd == 'get_focus':
        return Response(cam_get(IMG_FOCUS_URL),  content_type='application/xml')
    elif cmd == 'get_ircut':
        return Response(cam_get(IMG_IRCUT_URL),  content_type='application/xml')
    elif cmd == 'get_wb':
        return Response(cam_get(IMG_WB_URL),     content_type='application/xml')
    elif cmd == 'get_hlc':
        return Response(cam_get(IMG_HLC_URL),    content_type='application/xml')
    elif cmd == 'get_dehaze':
        return Response(cam_get(IMG_DEHAZE_URL), content_type='application/xml')
    elif cmd == 'get_flip':
        return Response(cam_get(IMG_FLIP_URL),   content_type='application/xml')
    elif cmd == 'get_noise':
        return Response(cam_get(IMG_NOISE_URL),  content_type='application/xml')
    elif cmd == 'get_wdr':
        return Response(cam_get(IMG_WDR_URL),    content_type='application/xml')

    # ── Image adjustment ──────────────────────────────────────────────────────
    elif cmd == 'brightness':
        ok, r = cam_put(IMG_COLOR_URL, img_replace(cam_get(IMG_COLOR_URL), 'brightnessLevel', value))
    elif cmd == 'contrast':
        ok, r = cam_put(IMG_COLOR_URL, img_replace(cam_get(IMG_COLOR_URL), 'contrastLevel', value))
    elif cmd == 'saturation':
        ok, r = cam_put(IMG_COLOR_URL, img_replace(cam_get(IMG_COLOR_URL), 'saturationLevel', value))
    elif cmd == 'sharpness':
        ok, r = img_modify(lambda x: img_replace(x, 'SharpnessLevel', value))

    # ── Focus ─────────────────────────────────────────────────────────────────
    elif cmd == 'focus':
        ok, r = focus_modify(lambda x: img_replace(x, 'focusStyle', value))
    elif cmd == 'focus_min_dist':
        ok, r = focus_modify(lambda x: img_replace(x, 'focusLimited', value))
    elif cmd == 'focus_trigger':
        # Trigger one-shot autofocus: switch to SEMIAUTOMATIC, then back to AUTO
        focus_modify(lambda x: img_replace(x, 'focusStyle', 'SEMIAUTOMATIC'))
        time.sleep(0.3)
        ok, r = focus_modify(lambda x: img_replace(x, 'focusStyle', 'AUTO'))

    # ── White balance ─────────────────────────────────────────────────────────
    elif cmd == 'wb':
        ok, r = cam_put(IMG_WB_URL, img_replace(cam_get(IMG_WB_URL), 'WhiteBalanceStyle', value))

    # ── Dynamic range (HLC + WDR — BLC removed: ISAPI write has no effect on this firmware)
    elif cmd == 'hlc':
        ok, r = hlc_modify(lambda x: img_replace(x, 'enabled', value))
    elif cmd == 'hlc_level':
        ok, r = hlc_modify(lambda x: img_replace(x, 'HLCLevel', value))
    elif cmd == 'super_wdr':
        # mode values: open | close | auto
        ok, r = wdr_modify(lambda x: img_replace(x, 'mode', value))
    elif cmd == 'wdr_level':
        ok, r = wdr_modify(lambda x: img_replace(x, 'WDRLevel', value))

    # ── Image enhancement ─────────────────────────────────────────────────────
    elif cmd == 'noise_mode':
        # mode: close | general | advanced
        ok, r = noise_modify(lambda x: img_replace(x, 'mode', value))
    elif cmd == 'noise':
        ok, r = noise_modify(lambda x: img_replace_in(x, 'GeneralMode', 'generalLevel', value))
    elif cmd == 'noise_spatial':
        ok, r = noise_modify(lambda x: img_replace_in(x, 'AdvancedMode', 'FrameNoiseReduceLevel', value))
    elif cmd == 'noise_temporal':
        ok, r = noise_modify(lambda x: img_replace_in(x, 'AdvancedMode', 'InterFrameNoiseReduceLevel', value))
    elif cmd == 'dehaze':
        lvl = level or '80'
        def _fn(x): return img_replace_in(img_replace_in(x, 'Dehaze', 'DehazeMode', value), 'Dehaze', 'DehazeLevel', lvl)
        ok, r = cam_put(IMG_DEHAZE_URL, _fn(cam_get(IMG_DEHAZE_URL)))
    elif cmd == 'dehaze_level':
        ok, r = cam_put(IMG_DEHAZE_URL, img_replace_in(cam_get(IMG_DEHAZE_URL), 'Dehaze', 'DehazeLevel', value))

    # ── Day/night switch ──────────────────────────────────────────────────────
    elif cmd == 'daynight':
        # IrcutFilterType: day (colour) | night (B/W) | auto
        ok, r = ircut_modify(lambda x: img_replace(x, 'IrcutFilterType', value))

    # ── Mirror/flip ───────────────────────────────────────────────────────────
    elif cmd == 'flip':
        # ImageFlipStyle values: LEFTRIGHT | UPDOWN | CENTER
        current = cam_get(IMG_FLIP_URL)
        if value == 'OFF':
            modified = img_replace(current, 'enabled', 'false')
            modified = re.sub(r'<ImageFlipStyle>[^<]*</ImageFlipStyle>', '', modified)
            modified = re.sub(r'<ImageFlipStyle\s*/>', '', modified)
        else:
            modified = img_replace(current, 'enabled', 'true')
            if '<ImageFlipStyle>' in modified or '<ImageFlipStyle/>' in modified:
                modified = img_replace(modified, 'ImageFlipStyle', value)
            else:
                modified = modified.replace('</ImageFlip>',
                    f'<ImageFlipStyle>{value}</ImageFlipStyle></ImageFlip>')
        ok, r = cam_put(IMG_FLIP_URL, modified)

    # ── Factory reset ─────────────────────────────────────────────────────────
    elif cmd == 'reset':
        r = requests.put(IMG_RESTORE_URL, auth=AUTH, headers=HEADERS, timeout=5)
        ok = r.status_code == 200
        print(f'[reset] restore → {r.status_code}', file=sys.stderr)
        return jsonify({'ok': ok, 'cmd': cmd})

    else:
        return jsonify({'ok': False, 'error': f'Unknown cmd: {cmd}'}), 400

    print(f'[camera] {cmd}={value}/{level} ok={ok}')
    return jsonify({'ok': ok, 'cmd': cmd, 'camResponse': r})


if __name__ == '__main__':
    print(f'[server] CraneCam starting on port {FLASK_PORT}')
    print(f'[server] Open: http://192.168.2.1:{FLASK_PORT}')
    init_camera()
    app.run(host='0.0.0.0', port=FLASK_PORT, threaded=True)
