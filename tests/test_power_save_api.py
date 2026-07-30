import queue

import app as app_module


class DummyScrcpy:
    starts = []
    stops = 0

    def __init__(self, device_udid=None):
        self.device_udid = device_udid
        self.running = False

    def scrcpy_start(self, video_cb, bit_rate, max_fps, msg_cb, device_udid=None):
        self.running = True
        DummyScrcpy.starts.append(device_udid)

    def scrcpy_stop(self):
        self.running = False
        DummyScrcpy.stops += 1

    def is_healthy(self):
        return self.running


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


def test_power_save_api_updates_config_and_restarts_watched_context(monkeypatch):
    reset_state()
    DummyScrcpy.starts = []
    DummyScrcpy.stops = 0
    monkeypatch.setattr(app_module, "Scrcpy", DummyScrcpy)

    device = "device-1"
    old_ctx = DummyScrcpy(device_udid=device)
    old_ctx.running = True
    app_module.device_contexts[device] = old_ctx
    app_module.device_video_queues[device] = [queue.Queue()]

    client = app_module.app.test_client()
    response = client.post('/api/power_save', json={'start_hour': 22, 'end_hour': 7})

    assert response.status_code == 200
    assert response.get_json()['restarted_devices'] == [device]
    assert DummyScrcpy.stops == 1
    assert DummyScrcpy.starts == [device]
    assert app_module.device_contexts[device].running is True


def test_power_save_api_reports_video_enabled_status(monkeypatch):
    monkeypatch.setattr(app_module, 'is_power_save_window', lambda: True)

    client = app_module.app.test_client()
    response = client.get('/api/power_save')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['active'] is True
    assert payload['video_enabled'] is False


def test_power_save_api_rejects_invalid_hours():
    client = app_module.app.test_client()
    response = client.post('/api/power_save', json={'start_hour': 25, 'end_hour': 7})

    assert response.status_code == 400
