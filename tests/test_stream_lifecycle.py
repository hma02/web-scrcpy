from stream_lifecycle import detach_client_from_device


class DummyScrcpy:
    def __init__(self):
        self.stop_calls = 0

    def scrcpy_stop(self):
        self.stop_calls += 1


def test_detach_removes_last_watcher_and_stops_device():
    client_sid = "c1"
    device_udid = "d1"
    q = object()
    client_queues = {client_sid: {device_udid: q}}
    device_video_queues = {device_udid: [q]}
    ctx = DummyScrcpy()
    device_contexts = {device_udid: ctx}

    detach_client_from_device(
        client_sid,
        device_udid,
        client_queues,
        device_video_queues,
        device_contexts,
    )

    assert device_udid not in device_video_queues
    assert device_udid not in device_contexts
    assert client_queues[client_sid] == {}
    assert ctx.stop_calls == 1


def test_detach_keeps_device_running_with_other_watchers():
    client_sid = "c1"
    device_udid = "d1"
    q1 = object()
    q2 = object()
    client_queues = {client_sid: {device_udid: q1}}
    device_video_queues = {device_udid: [q1, q2]}
    ctx = DummyScrcpy()
    device_contexts = {device_udid: ctx}

    detach_client_from_device(
        client_sid,
        device_udid,
        client_queues,
        device_video_queues,
        device_contexts,
    )

    assert device_udid in device_video_queues
    assert device_video_queues[device_udid] == [q2]
    assert device_udid in device_contexts
    assert ctx.stop_calls == 0
