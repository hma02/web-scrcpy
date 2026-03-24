#!/usr/bin/env python3
"""
Exercise disconnect-style cleanup across two devices.

Run:
    python unit_tester/repro_disconnect_multi_device_cleanup.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stream_lifecycle import detach_client_from_device


class DummyScrcpy:
    def __init__(self, name):
        self.name = name
        self.stop_calls = 0

    def scrcpy_stop(self):
        self.stop_calls += 1


def main():
    client_sid = "client-1"
    q1 = object()
    q2 = object()

    client_queues = {client_sid: {"device-A": q1, "device-B": q2}}
    device_video_queues = {"device-A": [q1], "device-B": [q2]}
    device_contexts = {"device-A": DummyScrcpy("A"), "device-B": DummyScrcpy("B")}

    print("Before cleanup:")
    print(" client_queues keys:", list(client_queues[client_sid].keys()))
    print(" device_video_queues keys:", list(device_video_queues.keys()))
    print(" device_contexts keys:", list(device_contexts.keys()))
    print("")

    for device_udid in list(client_queues[client_sid].keys()):
        detach_client_from_device(
            client_sid,
            device_udid,
            client_queues,
            device_video_queues,
            device_contexts,
        )
    del client_queues[client_sid]

    print("After cleanup:")
    print(" client_queues has client:", client_sid in client_queues)
    print(" device_video_queues empty:", len(device_video_queues) == 0)
    print(" device_contexts empty:", len(device_contexts) == 0)
    print("Expected with fix: False / True / True")


if __name__ == "__main__":
    main()
