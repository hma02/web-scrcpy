import queue

import app as app_module


class DummyScrcpy:
    def __init__(self):
        self.stop_calls = 0

    def scrcpy_stop(self):
        self.stop_calls += 1


def reset_state():
    app_module.client_queues.clear()
    app_module.device_video_queues.clear()
    app_module.device_contexts.clear()
    app_module.device_watchers.clear()
    app_module.device_control_owner.clear()
    app_module.device_bootstrap_chunks.clear()
    app_module.device_bootstrap_bytes.clear()
    app_module.device_locks.clear()


def test_bootstrap_is_replayed_to_late_joiner():
    reset_state()
    device = "d1"
    app_module.device_bootstrap_chunks[device] = [b"first", b"second"]
    app_module.device_bootstrap_bytes[device] = len(b"first") + len(b"second")

    q = queue.Queue()
    app_module.attach_client_to_device("c1", device, q)

    assert q.get_nowait() == b"first"
    assert q.get_nowait() == b"second"
    assert app_module.device_control_owner[device] == "c1"


def test_record_bootstrap_chunk_is_capped():
    reset_state()
    device = "d2"
    oversized = b"x" * (app_module.BOOTSTRAP_MAX_BYTES + 1024)
    app_module.record_bootstrap_chunk(device, oversized)

    assert app_module.device_bootstrap_bytes[device] == app_module.BOOTSTRAP_MAX_BYTES
    assert len(app_module.device_bootstrap_chunks[device][0]) == app_module.BOOTSTRAP_MAX_BYTES

    # Additional chunks should be ignored once cap is reached.
    app_module.record_bootstrap_chunk(device, b"more")
    assert app_module.device_bootstrap_bytes[device] == app_module.BOOTSTRAP_MAX_BYTES
    assert len(app_module.device_bootstrap_chunks[device]) == 1


def test_latest_joined_viewer_owns_control_and_falls_back_on_detach():
    reset_state()
    device = "d3"
    ctx = DummyScrcpy()
    app_module.device_contexts[device] = ctx
    app_module.device_bootstrap_chunks[device] = []
    app_module.device_bootstrap_bytes[device] = 0

    q1 = queue.Queue()
    q2 = queue.Queue()
    app_module.attach_client_to_device("c1", device, q1)
    app_module.attach_client_to_device("c2", device, q2)

    assert app_module.device_control_owner[device] == "c2"

    app_module.detach_client_and_update_owner("c2", device)
    assert app_module.device_control_owner[device] == "c1"
    assert device in app_module.device_contexts
    assert ctx.stop_calls == 0

    app_module.detach_client_and_update_owner("c1", device)
    assert device not in app_module.device_control_owner
    assert device not in app_module.device_watchers
    assert device not in app_module.device_contexts
    assert device not in app_module.device_bootstrap_chunks
    assert ctx.stop_calls == 1
