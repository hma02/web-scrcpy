from flask import Flask, render_template, request, jsonify, redirect
from flask_socketio import SocketIO, emit, send
from scrcpy import (
    Scrcpy,
    get_power_save_config,
    get_power_save_now,
    get_power_save_timezone,
    get_video_enabled_override,
    get_effective_stream_settings,
    is_power_save_window,
    is_video_disabled_override,
    set_power_save_config,
    set_video_enabled_override,
    set_video_disabled_override,
)
from stream_lifecycle import detach_client_from_device
import argparse
import queue
import time
import threading
from urllib.parse import quote
from collections import deque
from pathlib import Path
# Force inclusion of simple_websocket for threading async_mode in bundled binary
import simple_websocket  # noqa: F401

# Multi-device support: maps device_udid -> scrcpy instance
device_contexts = {}

# Maps client_sid -> dict of {device_udid -> queue}
client_queues = {}

# Maps device_udid -> list of queues for that device (for multi-client support)
device_video_queues = {}

# Maps device_udid -> list of watcher client_sids in join order
device_watchers = {}

# Maps device_udid -> client_sid that currently owns control (latest watcher)
device_control_owner = {}

# Maps device_udid -> client_sid that currently receives live video.
device_stream_target = {}

# Per-device lock to avoid start/stop races across concurrent clients.
device_locks = {}

# Global lock for shared state maps.
state_lock = threading.RLock()

# Per-device stream parsing/cache state to support late joiners at packet boundaries.
STREAM_HEADER_BYTES = 76  # 64-byte device name + 12-byte initial video size block
REPLAY_RECENT_PACKET_COUNT = 40
RECENT_PACKET_HISTORY = 240
MAX_PACKET_SIZE = 2 * 1024 * 1024
device_stream_buffers = {}
device_stream_headers = {}
device_recent_packets = {}
device_latest_sps_packet = {}
device_latest_pps_packet = {}
client_attention = {}

video_bit_rate = "800000"
max_fps = 30
memorized_pin = ""
UNLOCK_PIN_FILE = Path("tmp.txt")
server_start_time = time.time()
device_first_seen = {}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# In a bundled binary we likely don't have eventlet/gevent installed; force threading.
socketio = SocketIO(app, async_mode="threading")


def get_device_lock(device_udid):
    with state_lock:
        lock = device_locks.get(device_udid)
        if lock is None:
            lock = threading.Lock()
            device_locks[device_udid] = lock
        return lock


def is_ctx_healthy(ctx):
    """Best-effort context health check with backward compatibility."""
    if ctx is None:
        return False
    checker = getattr(ctx, "is_healthy", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception as exc:
            print(f"Context health check failed: {exc}")
            return False
    return bool(getattr(ctx, "running", False))


def restart_device_context_locked(device_udid, force_start=False):
    """
    Restart one device context under per-device lock when watchers are present.
    Caller must already hold the per-device lock.
    """
    existing_ctx = device_contexts.get(device_udid)
    if existing_ctx is not None:
        try:
            existing_ctx.scrcpy_stop()
        except Exception as exc:
            print(f"scrcpy_stop failed during restart for {device_udid}: {exc}")
        with state_lock:
            device_contexts.pop(device_udid, None)

    with state_lock:
        watcher_count = len(device_video_queues.get(device_udid, []))
        if watcher_count <= 0 and not force_start:
            clear_stream_cache_locked(device_udid)
            return False

    scpy_ctx = Scrcpy(device_udid=device_udid)
    scpy_ctx.scrcpy_start(
        lambda data: send_video_data(device_udid, data),
        video_bit_rate,
        max_fps,
        lambda message: send_device_message(device_udid, message),
        device_udid=device_udid
    )
    with state_lock:
        device_contexts[device_udid] = scpy_ctx
        device_video_queues.setdefault(device_udid, [])
        device_watchers.setdefault(device_udid, [])
        clear_stream_cache_locked(device_udid)
    return True


def recover_unhealthy_device_context(device_udid, reason):
    """If context is unhealthy, stop it and restart fresh when viewers still exist."""
    lock = get_device_lock(device_udid)
    with lock:
        with state_lock:
            ctx = device_contexts.get(device_udid)
            healthy = is_ctx_healthy(ctx)
        if healthy:
            return False

        print(f"Recovering device {device_udid} due to unhealthy context: {reason}")
        try:
            return restart_device_context_locked(device_udid)
        except Exception as exc:
            print(f"Failed recovering {device_udid}: {exc}")
            with state_lock:
                bad_ctx = device_contexts.get(device_udid)
            if bad_ctx is not None:
                try:
                    bad_ctx.scrcpy_stop()
                except Exception:
                    pass
                with state_lock:
                    device_contexts.pop(device_udid, None)
            return False


def attach_client_to_device(client_sid, device_udid, queue_obj):
    with state_lock:
        client_queues.setdefault(client_sid, {})[device_udid] = queue_obj
        device_video_queues.setdefault(device_udid, []).append(queue_obj)
        watchers = device_watchers.setdefault(device_udid, [])
        if client_sid in watchers:
            watchers.remove(client_sid)
        watchers.append(client_sid)
        # New connections are treated as visible/active unless stated otherwise.
        client_attention.setdefault(client_sid, True)
        recompute_stream_target_and_owner_locked(device_udid)
        bootstrap_chunks = build_replay_chunks_locked(device_udid)

    # Replay bootstrap stream bytes to late joiners (name/size/SPS/PPS headers etc.).
    for chunk in bootstrap_chunks:
        try:
            queue_obj.put(chunk, block=False)
        except queue.Full:
            break


def detach_client_and_update_owner(client_sid, device_udid):
    with state_lock:
        detach_client_from_device(
            client_sid,
            device_udid,
            client_queues,
            device_video_queues,
            device_contexts
        )

        watchers = device_watchers.get(device_udid, [])
        while client_sid in watchers:
            watchers.remove(client_sid)
        if watchers:
            device_control_owner[device_udid] = watchers[-1]
            device_watchers[device_udid] = watchers
        else:
            device_watchers.pop(device_udid, None)
            device_control_owner.pop(device_udid, None)
            device_stream_target.pop(device_udid, None)
            clear_stream_cache_locked(device_udid)
        recompute_stream_target_and_owner_locked(device_udid)


def clear_stream_cache_locked(device_udid):
    device_stream_buffers.pop(device_udid, None)
    device_stream_headers.pop(device_udid, None)
    device_recent_packets.pop(device_udid, None)
    device_latest_sps_packet.pop(device_udid, None)
    device_latest_pps_packet.pop(device_udid, None)


def _extract_nalu_type(packet_bytes):
    if len(packet_bytes) < 17:
        return None
    if packet_bytes[12:16] == b"\x00\x00\x00\x01":
        return packet_bytes[16] & 0x1F
    return None


def _process_stream_chunk_locked(device_udid, data):
    """
    Convert raw recv() chunks into protocol-aligned chunks:
    - first emits stream header block (76 bytes)
    - then emits complete packet blocks (12-byte packet header + payload)
    """
    if not data:
        return []

    out_chunks = []
    buffer = device_stream_buffers.setdefault(device_udid, bytearray())
    buffer.extend(data)

    if device_udid not in device_stream_headers:
        if len(buffer) < STREAM_HEADER_BYTES:
            return []
        header = bytes(buffer[:STREAM_HEADER_BYTES])
        del buffer[:STREAM_HEADER_BYTES]
        device_stream_headers[device_udid] = header
        out_chunks.append(header)

    recent = device_recent_packets.setdefault(device_udid, deque(maxlen=RECENT_PACKET_HISTORY))
    while len(buffer) >= 12:
        packet_size = int.from_bytes(buffer[8:12], byteorder='big', signed=True)
        if packet_size <= 0 or packet_size > MAX_PACKET_SIZE:
            # Desync safety: shift one byte and keep scanning.
            del buffer[0]
            continue
        full_size = 12 + packet_size
        if len(buffer) < full_size:
            break
        packet = bytes(buffer[:full_size])
        del buffer[:full_size]

        nalu_type = _extract_nalu_type(packet)
        if nalu_type == 7:
            device_latest_sps_packet[device_udid] = packet
        elif nalu_type == 8:
            device_latest_pps_packet[device_udid] = packet

        recent.append(packet)
        out_chunks.append(packet)

    return out_chunks


def build_replay_chunks_locked(device_udid):
    header = device_stream_headers.get(device_udid)
    if not header:
        return []

    replay = [header]
    sps = device_latest_sps_packet.get(device_udid)
    pps = device_latest_pps_packet.get(device_udid)
    if sps:
        replay.append(sps)
    if pps:
        replay.append(pps)
    recent = list(device_recent_packets.get(device_udid, []))
    if recent:
        replay.extend(recent[-REPLAY_RECENT_PACKET_COUNT:])
    return replay


def recompute_stream_target_and_owner_locked(device_udid):
    """
    Choose who should receive live frames and control for a device.
    Priority:
    1) latest joined watcher that is currently visible/attentive
    2) latest joined watcher regardless of visibility (fallback)
    """
    watchers = device_watchers.get(device_udid, [])
    if not watchers:
        device_stream_target.pop(device_udid, None)
        device_control_owner.pop(device_udid, None)
        return None

    target = None
    for sid in reversed(watchers):
        if client_attention.get(sid, True):
            target = sid
            break
    if target is None:
        target = watchers[-1]

    device_stream_target[device_udid] = target
    device_control_owner[device_udid] = target
    return target

@app.route('/')
def index():
    return render_template('device-selector.html')

@app.route('/stream-single')
def stream_single():
    device_udid = request.args.get('device')
    if not device_udid:
        return redirect('/')
    return redirect(f"/stream-multi?device1={quote(device_udid)}")

@app.route('/stream-dual')
def stream_dual():
    return render_template('stream-multi.html')

@app.route('/stream-multi')
def stream_multi():
    return render_template('stream-multi.html')

@app.route('/api/devices')
def get_devices():
    """Return list of connected devices"""
    global device_first_seen
    try:
        scpy_temp = Scrcpy()
        devices = scpy_temp.list_devices()
        now = time.time()
        payload = []
        for raw_device in devices:
            udid = raw_device if isinstance(raw_device, str) else raw_device.get('udid')
            if not udid:
                continue
            if udid not in device_first_seen:
                device_first_seen[udid] = now
            alive_for_seconds = max(0.0, now - device_first_seen[udid])
            payload.append({
                'udid': udid,
                'alive_for_seconds': alive_for_seconds,
                'server_uptime_seconds': max(0.0, now - server_start_time)
            })
        return jsonify(payload)
    except Exception as e:
        print(f"Error getting devices: {e}")
        return jsonify([]), 500

@app.route('/api/pin', methods=['GET', 'POST'])
def pin_memory():
    """In-memory PIN storage (lives only while server process is running)."""
    global memorized_pin
    if request.method == 'GET':
        return jsonify({'pin': memorized_pin})

    payload = request.get_json(silent=True) or {}
    pin = payload.get('pin', '')
    if not isinstance(pin, str):
        return jsonify({'error': 'pin must be a string'}), 400
    # PIN is expected as digits; keep only digits to avoid accidental extra chars.
    memorized_pin = ''.join(ch for ch in pin if ch.isdigit())
    return jsonify({'pin': memorized_pin})


@app.route('/api/unlock_pin')
def get_unlock_pin():
    """Read the unlock PIN from local tmp.txt in the server working directory."""
    try:
        pin = UNLOCK_PIN_FILE.read_text(encoding='utf-8').strip()
        method = 'tmp.txt file'
        path = str(UNLOCK_PIN_FILE.resolve())
    except FileNotFoundError:
        pin = '123456'
        method = 'default password'
        path = str(UNLOCK_PIN_FILE.resolve())
    # PIN entry is sent as text input; keep only digits to avoid accidental whitespace/comments.
    return jsonify({
        'pin': ''.join(ch for ch in pin if ch.isdigit()),
        'method': method,
        'path': path,
    })


def get_power_save_status():
    """Return power-save config plus whether new sessions should enable video."""
    now = get_power_save_now()
    active = is_power_save_window(now)
    override = is_video_disabled_override()
    video_enabled_override = get_video_enabled_override()
    video_enabled, effective_bit_rate, effective_max_fps, power_save_video_settings = get_effective_stream_settings(
        video_bit_rate,
        max_fps,
        now,
    )
    return {
        **get_power_save_config(),
        'active': active,
        'timezone': get_power_save_timezone(),
        'current_hour': now.hour,
        'current_time': now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        'video_disabled_override': override,
        'video_enabled_override': video_enabled_override,
        'video_override_mode': 'auto' if video_enabled_override is None else ('on' if video_enabled_override else 'off'),
        'power_save_video_settings': power_save_video_settings,
        'effective_video_bit_rate': effective_bit_rate,
        'effective_max_fps': effective_max_fps,
        'video_enabled': video_enabled,
    }


@app.route('/api/stream_config')
def get_stream_config():
    """Expose active stream configuration for client-side diagnostics."""
    return jsonify({
        'video_bit_rate': str(video_bit_rate),
        'max_fps': int(max_fps),
        'power_save': get_power_save_status(),
    })


@app.route('/api/power_save', methods=['GET', 'POST'])
def power_save_config():
    """Read or update the power-save hour window and restart active devices."""
    if request.method == 'GET':
        return jsonify(get_power_save_status())

    payload = request.get_json(silent=True) or {}
    try:
        if 'start_hour' in payload or 'end_hour' in payload:
            set_power_save_config(payload.get('start_hour'), payload.get('end_hour'))
        if 'video_enabled_override' in payload:
            set_video_enabled_override(payload.get('video_enabled_override'))
        elif 'video_disabled_override' in payload:
            set_video_disabled_override(payload.get('video_disabled_override'))
    except (TypeError, ValueError):
        return jsonify({'error': 'start_hour and end_hour must be integers from 0 to 23'}), 400

    restarted = []
    with state_lock:
        device_ids = list(device_contexts.keys())
    for device_udid in device_ids:
        lock = get_device_lock(device_udid)
        with lock:
            if restart_device_context_locked(device_udid):
                restarted.append(device_udid)

    return jsonify({**get_power_save_status(), 'restarted_devices': restarted})

def video_send_task(client_sid, device_udid):
    """Send video data for a specific device to a specific client"""
    while client_sid in client_queues and device_udid in client_queues[client_sid]:
        try:
            queue_obj = client_queues[client_sid][device_udid]
            message = queue_obj.get(timeout=0.01)
            socketio.emit('video_data', {
                'device_udid': device_udid,
                'data': message
            }, to=client_sid)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error sending data: {e}")
        finally:
            socketio.sleep(0.001)
    print(f"video_send_task stopped for device {device_udid}")

def send_video_data(device_udid, data):
    """Queue video data for all clients watching this device"""
    with state_lock:
        chunks = _process_stream_chunk_locked(device_udid, data)
        target_sid = device_stream_target.get(device_udid)
        target_queue = None
        if target_sid is not None:
            target_queue = client_queues.get(target_sid, {}).get(device_udid)
    if not chunks:
        return
    if target_queue is None:
        return
    for chunk in chunks:
        try:
            target_queue.put(chunk, block=False)
        except queue.Full:
            pass  # Skip if queue is full

def send_device_message(device_udid, message):
    """Send control channel device messages (e.g. clipboard) to all viewers of a device."""
    with state_lock:
        recipients = [
            client_sid for client_sid, queues_by_device in client_queues.items()
            if device_udid in queues_by_device
        ]
    for client_sid in recipients:
        socketio.emit('device_message', {
            'device_udid': device_udid,
            'message': message
        }, to=client_sid)


def device_context_health_task():
    """Periodic health monitor for running scrcpy contexts."""
    while True:
        with state_lock:
            device_ids = list(device_contexts.keys())
        for device_udid in device_ids:
            with state_lock:
                ctx = device_contexts.get(device_udid)
            if ctx is None:
                continue
            if not is_ctx_healthy(ctx):
                recover_unhealthy_device_context(device_udid, "periodic health check")
        socketio.sleep(1.0)

@socketio.on('connect')
def handle_connect():
    client_sid = request.sid
    print(f'Client {client_sid} connected')
    # Initialize per-client queue dict
    with state_lock:
        client_queues[client_sid] = {}
        client_attention[client_sid] = True

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    """Cleanup when client disconnects."""
    client_sid = request.sid
    print(f'Client {client_sid} disconnected: {reason}')
    
    # Remove client from all device queues
    with state_lock:
        device_ids = list(client_queues.get(client_sid, {}).keys())
    for device_udid in device_ids:
        lock = get_device_lock(device_udid)
        with lock:
            detach_client_and_update_owner(client_sid, device_udid)
    with state_lock:
        client_queues.pop(client_sid, None)
        client_attention.pop(client_sid, None)
    print('Client cleanup done')

@socketio.on('start_device')
def handle_start_device(data):
    """Start streaming from a specific device"""
    client_sid = request.sid
    device_udid = data.get('device_udid')
    
    print(f"Client {client_sid} requesting device {device_udid}")
    
    if not device_udid:
        emit('error', 'device_udid required')
        return
    
    try:
        lock = get_device_lock(device_udid)
        with lock:
            existing_ctx = device_contexts.get(device_udid)
            needs_start = existing_ctx is None or not is_ctx_healthy(existing_ctx)
            if needs_start:
                restart_device_context_locked(device_udid, force_start=True)

            # Create queue for this client-device pair
            q = queue.Queue()
            attach_client_to_device(client_sid, device_udid, q)

            # Start video send task
            socketio.start_background_task(video_send_task, client_sid, device_udid)
        
        emit('device_started', {'device_udid': device_udid})
        print(f"Device {device_udid} started for client {client_sid}")
        
    except Exception as e:
        print(f"Error starting device {device_udid}: {e}")
        emit('error', f"Failed to start device: {str(e)}")

@socketio.on('stop_device')
def handle_stop_device(data):
    """Stop streaming a specific device"""
    client_sid = request.sid
    device_udid = data.get('device_udid')
    
    print(f"Client {client_sid} stopping device {device_udid}")
    if not device_udid:
        return
    
    lock = get_device_lock(device_udid)
    with lock:
        detach_client_and_update_owner(client_sid, device_udid)

@socketio.on('control_data')
def handle_control_data(data):
    """Route control data to the correct device"""
    device_udid = data.get('device_udid')
    control_data = data.get('data')
    
    with state_lock:
        owner_sid = device_control_owner.get(device_udid)
        ctx = device_contexts.get(device_udid)

    # Latest joined viewer exclusively owns controls for this device.
    if owner_sid is not None and owner_sid != request.sid:
        return

    if ctx is not None:
        try:
            ctx.scrcpy_send_control(control_data)
        except Exception as e:
            print(f"Error sending control data to {device_udid}: {e}")
            recover_unhealthy_device_context(device_udid, "control send failure")
    else:
        print(f"Device {device_udid} not found in contexts")


@socketio.on('viewer_attention')
def handle_viewer_attention(data):
    """
    Update viewer visibility/attention state.
    Used to hand live stream/control back to an earlier viewer when the latest
    joined viewer goes to background.
    """
    client_sid = request.sid
    visible = bool((data or {}).get('visible', True))
    with state_lock:
        client_attention[client_sid] = visible
        watched_devices = list(client_queues.get(client_sid, {}).keys())

    for device_udid in watched_devices:
        lock = get_device_lock(device_udid)
        with lock:
            with state_lock:
                recompute_stream_target_and_owner_locked(device_udid)


socketio.start_background_task(device_context_health_task)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web server for scrcpy')
    parser.add_argument('--video_bit_rate', default="800000", help='scrcpy video bit rate')
    parser.add_argument('--max_fps', type=int, default=30, help='scrcpy max FPS')
    parser.add_argument('--port', type=int, default=5011, help='port to bind the web server to')
    args = parser.parse_args()
    video_bit_rate = args.video_bit_rate
    max_fps = args.max_fps
    socketio.run(app, host='0.0.0.0', port=args.port)
