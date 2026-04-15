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
    app_module.device_stream_target.clear()
    app_module.device_stream_buffers.clear()
    app_module.device_stream_headers.clear()
    app_module.device_recent_packets.clear()
    app_module.device_latest_sps_packet.clear()
    app_module.device_latest_pps_packet.clear()
    app_module.client_attention.clear()
    app_module.device_locks.clear()


def test_bootstrap_is_replayed_to_late_joiner():
    reset_state()
    device = "d1"
    app_module.device_stream_headers[device] = b"h" * app_module.STREAM_HEADER_BYTES
    app_module.device_latest_sps_packet[device] = b"sps"
    app_module.device_latest_pps_packet[device] = b"pps"
    app_module.device_recent_packets[device] = app_module.deque([b"p1", b"p2"], maxlen=10)

    q = queue.Queue()
    app_module.attach_client_to_device("c1", device, q)

    assert q.get_nowait() == b"h" * app_module.STREAM_HEADER_BYTES
    assert q.get_nowait() == b"sps"
    assert q.get_nowait() == b"pps"
    assert q.get_nowait() == b"p1"
    assert q.get_nowait() == b"p2"
    assert app_module.device_control_owner[device] == "c1"
    assert app_module.device_stream_target[device] == "c1"


def test_process_stream_chunk_emits_aligned_chunks():
    reset_state()
    device = "d2"
    header = b"h" * app_module.STREAM_HEADER_BYTES
    payload = b"\x00\x00\x00\x01\x65\x01\x02"
    packet = b"\x00" * 8 + len(payload).to_bytes(4, "big", signed=True) + payload

    chunks = app_module._process_stream_chunk_locked(device, header + packet)
    assert chunks[0] == header
    assert chunks[1] == packet


def test_latest_joined_viewer_owns_control_and_falls_back_on_detach():
    reset_state()
    device = "d3"
    ctx = DummyScrcpy()
    app_module.device_contexts[device] = ctx
    app_module.device_stream_headers[device] = b"h" * app_module.STREAM_HEADER_BYTES

    q1 = queue.Queue()
    q2 = queue.Queue()
    app_module.attach_client_to_device("c1", device, q1)
    app_module.attach_client_to_device("c2", device, q2)

    assert app_module.device_control_owner[device] == "c2"
    assert app_module.device_stream_target[device] == "c2"

    app_module.detach_client_and_update_owner("c2", device)
    assert app_module.device_control_owner[device] == "c1"
    assert app_module.device_stream_target[device] == "c1"
    assert device in app_module.device_contexts
    assert ctx.stop_calls == 0

    app_module.detach_client_and_update_owner("c1", device)
    assert device not in app_module.device_control_owner
    assert device not in app_module.device_stream_target
    assert device not in app_module.device_watchers
    assert device not in app_module.device_contexts
    assert device not in app_module.device_stream_headers
    assert ctx.stop_calls == 1


def test_attention_switches_live_stream_target():
    reset_state()
    device = "d4"
    app_module.device_stream_headers[device] = b"h" * app_module.STREAM_HEADER_BYTES

    q1 = queue.Queue()
    q2 = queue.Queue()
    app_module.attach_client_to_device("ubuntu", device, q1)
    app_module.attach_client_to_device("iphone", device, q2)
    assert app_module.device_stream_target[device] == "iphone"

    # Latest joined loses attention; previous attentive watcher regains stream+control.
    app_module.client_attention["iphone"] = False
    app_module.recompute_stream_target_and_owner_locked(device)
    assert app_module.device_stream_target[device] == "ubuntu"
    assert app_module.device_control_owner[device] == "ubuntu"
