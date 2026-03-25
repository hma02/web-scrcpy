from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, send
from scrcpy import Scrcpy
from stream_lifecycle import detach_client_from_device
import argparse
import queue
# Force inclusion of simple_websocket for threading async_mode in bundled binary
import simple_websocket  # noqa: F401

# Multi-device support: maps device_udid -> scrcpy instance
device_contexts = {}

# Maps client_sid -> dict of {device_udid -> queue}
client_queues = {}

# Maps device_udid -> list of queues for that device (for multi-client support)
device_video_queues = {}

video_bit_rate = "256000"
max_fps = 10

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# In a bundled binary we likely don't have eventlet/gevent installed; force threading.
socketio = SocketIO(app, async_mode="threading")

@app.route('/')
def index():
    return render_template('device-selector.html')

@app.route('/stream-single')
def stream_single():
    return render_template('stream-single.html')

@app.route('/stream-dual')
def stream_dual():
    return render_template('stream-multi.html')

@app.route('/stream-multi')
def stream_multi():
    return render_template('stream-multi.html')

@app.route('/api/devices')
def get_devices():
    """Return list of connected devices"""
    try:
        scpy_temp = Scrcpy()
        devices = scpy_temp.list_devices()
        return jsonify(devices)
    except Exception as e:
        print(f"Error getting devices: {e}")
        return jsonify([]), 500

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
    if device_udid in device_video_queues:
        for q in device_video_queues[device_udid]:
            try:
                q.put(data, block=False)
            except queue.Full:
                pass  # Skip if queue is full

def send_device_message(device_udid, message):
    """Send control channel device messages (e.g. clipboard) to all viewers of a device."""
    for client_sid, queues_by_device in client_queues.items():
        if device_udid in queues_by_device:
            socketio.emit('device_message', {
                'device_udid': device_udid,
                'message': message
            }, to=client_sid)

@socketio.on('connect')
def handle_connect():
    client_sid = request.sid
    print(f'Client {client_sid} connected')
    # Initialize per-client queue dict
    client_queues[client_sid] = {}

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    """Cleanup when client disconnects."""
    client_sid = request.sid
    print(f'Client {client_sid} disconnected: {reason}')
    
    # Remove client from all device queues
    if client_sid in client_queues:
        for device_udid in list(client_queues[client_sid].keys()):
            detach_client_from_device(
                client_sid,
                device_udid,
                client_queues,
                device_video_queues,
                device_contexts
            )
        del client_queues[client_sid]
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
        # Create scrcpy instance for this device if not already exists
        # OR if existing instance is not running (was stopped)
        if device_udid not in device_contexts or not device_contexts[device_udid].running:
            # Clean up old instance if it exists
            if device_udid in device_contexts:
                try:
                    device_contexts[device_udid].scrcpy_stop()
                except:
                    pass
                del device_contexts[device_udid]
            
            # Create fresh instance
            scpy_ctx = Scrcpy(device_udid=device_udid)
            scpy_ctx.scrcpy_start(
                lambda data: send_video_data(device_udid, data),
                video_bit_rate,
                max_fps,
                lambda message: send_device_message(device_udid, message),
                device_udid=device_udid
            )
            device_contexts[device_udid] = scpy_ctx
            device_video_queues[device_udid] = []
        
        # Create queue for this client-device pair
        q = queue.Queue()
        client_queues[client_sid][device_udid] = q
        device_video_queues[device_udid].append(q)
        
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
    
    detach_client_from_device(
        client_sid,
        device_udid,
        client_queues,
        device_video_queues,
        device_contexts
    )

@socketio.on('control_data')
def handle_control_data(data):
    """Route control data to the correct device"""
    device_udid = data.get('device_udid')
    control_data = data.get('data')
    
    if device_udid in device_contexts:
        try:
            device_contexts[device_udid].scrcpy_send_control(control_data)
        except Exception as e:
            print(f"Error sending control data to {device_udid}: {e}")
    else:
        print(f"Device {device_udid} not found in contexts")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web server for scrcpy')
    parser.add_argument('--video_bit_rate', default="512000", help='scrcpy video bit rate')
    parser.add_argument('--max_fps', type=int, default=10, help='scrcpy max FPS')
    parser.add_argument('--port', type=int, default=5011, help='port to bind the web server to')
    args = parser.parse_args()
    video_bit_rate = args.video_bit_rate
    max_fps = args.max_fps
    socketio.run(app, host='0.0.0.0', port=args.port)
