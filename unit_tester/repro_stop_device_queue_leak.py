#!/usr/bin/env python3
"""
Reproduce the original stop_device queue leak and compare with the fixed logic.

Run:
    python unit_tester/repro_stop_device_queue_leak.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stream_lifecycle import detach_client_from_device


class DummyScrcpy:
    def __init__(self):
        self.stop_calls = 0

    def scrcpy_stop(self):
        self.stop_calls += 1


def buggy_stop_device(client_sid, device_udid, client_queues, device_video_queues, device_contexts):
    """Original buggy ordering from app.py before the fix."""
    if client_sid in client_queues and device_udid in client_queues[client_sid]:
        del client_queues[client_sid][device_udid]

    if device_udid in device_video_queues:
        if device_udid in client_queues[client_sid]:
            try:
                device_video_queues[device_udid].remove(client_queues[client_sid][device_udid])
            except (ValueError, KeyError):
                pass

        if len(device_video_queues[device_udid]) == 0:
            if device_udid in device_contexts:
                device_contexts[device_udid].scrcpy_stop()
                del device_contexts[device_udid]
            del device_video_queues[device_udid]


def build_state():
    client_sid = "client-1"
    device_udid = "device-1"
    q = object()
    return (
        client_sid,
        device_udid,
        {client_sid: {device_udid: q}},
        {device_udid: [q]},
        {device_udid: DummyScrcpy()},
    )


def main():
    print("=== Scenario A: buggy stop_device logic ===")
    client_sid, device_udid, client_queues, device_video_queues, device_contexts = build_state()
    buggy_stop_device(client_sid, device_udid, client_queues, device_video_queues, device_contexts)
    print(f"device_video_queues still has device: {device_udid in device_video_queues}")
    print(f"remaining watcher count: {len(device_video_queues.get(device_udid, []))}")
    print(f"scrcpy context still exists: {device_udid in device_contexts}")
    print("")

    print("=== Scenario B: fixed detach_client_from_device logic ===")
    client_sid, device_udid, client_queues, device_video_queues, device_contexts = build_state()
    detach_client_from_device(
        client_sid,
        device_udid,
        client_queues,
        device_video_queues,
        device_contexts,
    )
    print(f"device_video_queues still has device: {device_udid in device_video_queues}")
    print(f"scrcpy context still exists: {device_udid in device_contexts}")
    print("Expected with fix: both should be False.")


if __name__ == "__main__":
    main()
