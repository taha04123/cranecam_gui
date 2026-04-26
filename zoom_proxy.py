from flask import Flask, request, jsonify, Response
import subprocess
import sys
import re

CAMERA_IP   = '192.168.2.68'
CAMERA_USER = 'admin'
CAMERA_PASS = 'sebandtah2792'
ZOOM_URL    = f'http://{CAMERA_IP}/ISAPI/PTZCtrl/channels/1/absolute'
IMG_URL     = f'http://{CAMERA_IP}/ISAPI/Image/channels/1/'
VID_URL     = f'http://{CAMERA_IP}/ISAPI/Video/inputs/channels/1/'

app = Flask(__name__)

current_zoom = 10
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 10, 1000, 50


def cam_get(url):
    """GET from camera, return response text."""
    r = subprocess.run(
        ['curl', '--digest', '-s', '--connect-timeout', '3', '--max-time', '5',
         '-u', f'{CAMERA_USER}:{CAMERA_PASS}', url],
        capture_output=True, text=True)
    return r.stdout


def cam_put(url, xml):
    """PUT xml to camera URL, log full response, return (ok, response_text)."""
    r = subprocess.run(
        ['curl', '--digest', '-s', '--connect-timeout', '3', '--max-time', '5',
         '-u', f'{CAMERA_USER}:{CAMERA_PASS}',
         '-X', 'PUT', url, '-H', 'Content-Type: application/xml', '-d', xml],
        capture_output=True, text=True)
    ok = 'OK' in r.stdout or 'ok' in r.stdout
    print(f'[cam_put] url={url}', file=sys.stderr)
    print(f'[cam_put] xml={xml}', file=sys.stderr)
    print(f'[cam_put] response={r.stdout!r}', file=sys.stderr)
    return ok, r.stdout


def img_put(inner_xml):
    """PUT image channel settings (focus, flip, ircut, WDR, BLC, NR, sharpness, WB)."""
    xml = (f'<ImageChannel version="2.0" xmlns="http://www.std-cgi.com/ver20/XMLSchema">'
           f'<id>1</id>{inner_xml}</ImageChannel>')
    ok, resp = cam_put(IMG_URL, xml)
    return ok, resp


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    return r


@app.route('/zoom')
def zoom():
    global current_zoom
    cmd = request.args.get('cmd', '')
    if cmd == 'in':
        current_zoom = min(ZOOM_MAX, current_zoom + ZOOM_STEP)
        xml = (f'<PTZData><AbsoluteHigh><elevation>0</elevation><azimuth>0</azimuth>'
               f'<absoluteZoom>{current_zoom}</absoluteZoom></AbsoluteHigh></PTZData>')
        ok, _ = cam_put(ZOOM_URL, xml)
    elif cmd == 'out':
        current_zoom = max(ZOOM_MIN, current_zoom - ZOOM_STEP)
        xml = (f'<PTZData><AbsoluteHigh><elevation>0</elevation><azimuth>0</azimuth>'
               f'<absoluteZoom>{current_zoom}</absoluteZoom></AbsoluteHigh></PTZData>')
        ok, _ = cam_put(ZOOM_URL, xml)
    elif cmd == 'stop':
        ok = True
    else:
        return jsonify({'ok': False, 'error': 'Unknown cmd'}), 400
    print(f'[zoom] {cmd} -> {current_zoom}')
    return jsonify({'ok': ok, 'cmd': cmd, 'zoom': current_zoom})


@app.route('/camera')
def camera():
    cmd   = request.args.get('cmd',   '')
    value = request.args.get('value', '')
    level = request.args.get('level', '')

    if cmd == 'get_settings':
        img_xml = re.sub(r'<\?xml[^>]*\?>', '', cam_get(IMG_URL)).strip()
        vid_xml = re.sub(r'<\?xml[^>]*\?>', '', cam_get(VID_URL)).strip()
        combined = f'<?xml version="1.0" encoding="UTF-8"?><CombinedSettings>{img_xml}{vid_xml}</CombinedSettings>'
        return Response(combined, content_type='application/xml')

    elif cmd == 'brightness':
        ok, resp = img_put(f'<Color><brightnessLevel>{value}</brightnessLevel></Color>')
    elif cmd == 'contrast':
        ok, resp = img_put(f'<Color><contrastLevel>{value}</contrastLevel></Color>')
    elif cmd == 'saturation':
        ok, resp = img_put(f'<Color><saturationLevel>{value}</saturationLevel></Color>')
    elif cmd == 'sharpness':
        ok, resp = img_put(f'<Sharpness><SharpnessLevel>{value}</SharpnessLevel></Sharpness>')
    elif cmd == 'noise':
        ok, resp = img_put(
            f'<NoiseReduce><mode>general</mode>'
            f'<GeneralMode><generalLevel>{value}</generalLevel></GeneralMode></NoiseReduce>')
    elif cmd == 'daynight':
        ok, resp = img_put(f'<IrcutFilter><IrcutFilterType>{value}</IrcutFilterType></IrcutFilter>')
    elif cmd == 'wdr':
        lvl = level or '5'
        ok, resp = img_put(f'<WDR><mode>{value}</mode><WDRLevel>{lvl}</WDRLevel></WDR>')
    elif cmd == 'dehaze':
        lvl = level or '80'
        ok, resp = img_put(f'<Dehaze><DehazeMode>{value}</DehazeMode><DehazeLevel>{lvl}</DehazeLevel></Dehaze>')
    elif cmd == 'blc':
        ok, resp = img_put(f'<BLC><enabled>{value}</enabled></BLC>')
    elif cmd == 'wb':
        ok, resp = img_put(f'<WhiteBalance><WhiteBalanceStyle>{value}</WhiteBalanceStyle></WhiteBalance>')
    elif cmd == 'flip':
        if value == 'none':
            ok, resp = img_put('<ImageFlip><enabled>false</enabled></ImageFlip>')
        else:
            ok, resp = img_put(
                f'<ImageFlip><enabled>true</enabled><ImageFlipStyle>{value}</ImageFlipStyle></ImageFlip>')
    elif cmd == 'focus':
        ok, resp = img_put(f'<FocusConfiguration><focusStyle>{value}</focusStyle></FocusConfiguration>')
    elif cmd == 'focus_limit':
        ok, resp = img_put(f'<FocusConfiguration><focusLimited>{value}</focusLimited></FocusConfiguration>')
    elif cmd == 'focus_trigger':
        img_put('<FocusConfiguration><focusStyle>SEMIAUTOMATIC</focusStyle></FocusConfiguration>')
        import time; time.sleep(0.3)
        ok, resp = img_put('<FocusConfiguration><focusStyle>AUTO</focusStyle></FocusConfiguration>')

    # ── Debug: return raw camera response ──────────────────────────
    elif cmd == 'debug_get_vid':
        return Response(cam_get(VID_URL), content_type='application/xml')

    else:
        return jsonify({'ok': False, 'error': f'Unknown cmd: {cmd}'}), 400

    print(f'[camera] {cmd}={value}/{level} ok={ok}')
    return jsonify({'ok': ok, 'cmd': cmd, 'camResponse': resp})


if __name__ == '__main__':
    print('[zoom_proxy] Starting on port 5001')
    app.run(host='0.0.0.0', port=5001, threaded=True)
