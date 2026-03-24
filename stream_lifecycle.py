"""Helpers for managing client/device stream lifecycle state."""


def stop_device_context(device_udid, device_contexts, device_video_queues, logger=print):
    """Stop and remove a device context when no clients are watching."""
    if device_udid in device_contexts:
        try:
            device_contexts[device_udid].scrcpy_stop()
        except Exception as exc:  # defensive cleanup
            logger(f'scrcpy_stop failed for {device_udid}: {exc}')
        del device_contexts[device_udid]

    if device_udid in device_video_queues:
        del device_video_queues[device_udid]


def detach_client_from_device(
    client_sid,
    device_udid,
    client_queues,
    device_video_queues,
    device_contexts,
    logger=print
):
    """
    Detach one client from one device.

    Correct ordering is critical:
    1) remove queue from device watcher list
    2) remove queue from client map
    3) stop device context only when watcher list is empty
    """
    client_map = client_queues.get(client_sid, {})
    queue_obj = client_map.get(device_udid)

    if device_udid in device_video_queues and queue_obj is not None:
        try:
            device_video_queues[device_udid].remove(queue_obj)
        except ValueError:
            # Already removed by another path (disconnect + stop race)
            pass

    if client_sid in client_queues and device_udid in client_queues[client_sid]:
        del client_queues[client_sid][device_udid]

    if device_udid in device_video_queues and len(device_video_queues[device_udid]) == 0:
        stop_device_context(device_udid, device_contexts, device_video_queues, logger=logger)
