import app as app_module
from scrcpy import Scrcpy


class _FakeVideoSocket:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._timeout = None

    def settimeout(self, value):
        self._timeout = value

    def recv(self, _n):
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class DummyCtx:
    def __init__(self, running=True):
        self.running = running
        self.stop_calls = 0

    def scrcpy_stop(self):
        self.stop_calls += 1

    def scrcpy_send_control(self, _data):
        raise BrokenPipeError("[Errno 32] Broken pipe")


def _reset_state():
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


def test_repro_video_thread_exit_does_not_flip_running_false():
    """
    Reproduces the stale-running-state issue:
    receive_video_data() exits when socket closes, but Scrcpy.running remains True.
    """
    scpy = Scrcpy(device_udid="d1")
    scpy.running = True
    scpy.stop = False
    scpy.video_callback = lambda _data: None
    # first recv() is protocol-byte probe, second returns EOF and exits loop
    scpy.video_socket = _FakeVideoSocket([b"\x00", b""])

    scpy.receive_video_data()

    assert scpy.running is True


def test_repro_start_device_reuses_stale_running_context_without_restart(monkeypatch):
    """
    Reproduces app-level consequence:
    if an existing context says running=True, handle_start_device() does not restart.
    """
    _reset_state()
    device_udid = "192.168.1.111:5555"
    app_module.device_contexts[device_udid] = DummyCtx(running=True)

    constructor_calls = {"count": 0}

    class UnexpectedNewScrcpy:
        def __init__(self, *args, **kwargs):
            constructor_calls["count"] += 1
            raise AssertionError("A fresh Scrcpy should not be created in this repro")

    monkeypatch.setattr(app_module, "Scrcpy", UnexpectedNewScrcpy)

    client = app_module.socketio.test_client(app_module.app)
    try:
        client.emit("start_device", {"device_udid": device_udid})
    finally:
        client.disconnect()

    # Current behavior: no restart attempted when stale context still advertises running=True.
    assert constructor_calls["count"] == 0
