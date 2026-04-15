import app as app_module
from scrcpy import Scrcpy


class _EofSocket:
    def __init__(self):
        self.calls = 0

    def settimeout(self, _timeout):
        return None

    def recv(self, _size):
        self.calls += 1
        # First read (handshake attempt) returns nothing immediately,
        # which makes receive_video_data break out of its loop.
        return b""


class DummyScrcpy:
    starts = 0

    def __init__(self, device_udid=None):
        self.device_udid = device_udid
        self.running = False
        self.control_fail = False

    def scrcpy_start(self, video_cb, bit_rate, max_fps, msg_cb, device_udid=None):
        DummyScrcpy.starts += 1
        self.running = True

    def scrcpy_stop(self):
        self.running = False

    def scrcpy_send_control(self, _data):
        if self.control_fail:
            raise BrokenPipeError("simulated broken pipe")

    def is_healthy(self):
        return self.running and not self.control_fail


def reset_state():
    app_module.client_queues.clear()
    app_module.device_video_queues.clear()
    app_module.device_contexts.clear()
    app_module.device_watchers.clear()
    app_module.device_control_owner.clear()
    app_module.device_stream_target.clear()
    app_module.device_stream_buffers.clear()
    app_module.device_stream_headers.clear()
    app_module.device_recent_packets.clear()
    app_module.device_latest_sps_packet.clear()
    app_module.device_latest_pps_packet.clear()
    app_module.client_attention.clear()
    app_module.device_locks.clear()


def test_receive_video_data_eof_marks_running_false():
    """EOF should mark context unhealthy so reconnect can restart fresh."""
    s = Scrcpy(device_udid="d1")
    s.running = True
    s.stop = False
    s.video_socket = _EofSocket()
    s.video_callback = lambda _data: None

    s.receive_video_data()

    assert s.running is False


def test_start_device_restarts_context_after_control_broken_pipe(monkeypatch):
    """Control broken-pipe should force recovery and fresh start."""
    reset_state()
    DummyScrcpy.starts = 0
    monkeypatch.setattr(app_module, "Scrcpy", DummyScrcpy)

    flask_client = app_module.app.test_client()
    client = app_module.socketio.test_client(app_module.app, flask_test_client=flask_client)
    device_udid = "192.168.1.111:5555"

    client.emit("start_device", {"device_udid": device_udid})
    assert DummyScrcpy.starts == 1

    ctx = app_module.device_contexts[device_udid]
    ctx.control_fail = True

    # Simulate the server-side "Broken pipe" path seen in production logs.
    client.emit("control_data", {"device_udid": device_udid, "data": b"x"})

    # Recovery should restart immediately when control send fails.
    assert DummyScrcpy.starts == 2

    # A later start request should reuse healthy restarted context.
    client.emit("start_device", {"device_udid": device_udid})
    assert DummyScrcpy.starts == 2

    client.disconnect()
