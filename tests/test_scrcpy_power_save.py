from datetime import datetime

from scrcpy import Scrcpy, get_power_save_config, is_power_save_window, set_power_save_config


def test_power_save_window_wraps_midnight(monkeypatch):
    monkeypatch.delenv("WEB_SCRCPY_POWER_SAVE_START", raising=False)
    monkeypatch.delenv("WEB_SCRCPY_POWER_SAVE_END", raising=False)

    assert is_power_save_window(datetime(2026, 7, 30, 23, 0))
    assert is_power_save_window(datetime(2026, 7, 31, 5, 59))
    assert not is_power_save_window(datetime(2026, 7, 30, 6, 0))
    assert not is_power_save_window(datetime(2026, 7, 30, 22, 59))


def test_power_save_window_can_be_configured(monkeypatch):
    monkeypatch.setenv("WEB_SCRCPY_POWER_SAVE_START", "12:00")
    monkeypatch.setenv("WEB_SCRCPY_POWER_SAVE_END", "13:30")

    assert is_power_save_window(datetime(2026, 7, 30, 12, 0))
    assert is_power_save_window(datetime(2026, 7, 30, 13, 29))
    assert not is_power_save_window(datetime(2026, 7, 30, 13, 30))


def test_health_requires_expected_playback_mode(monkeypatch):
    ctx = Scrcpy(device_udid="d1")
    ctx.stop = False
    ctx.running = True
    ctx.video_enabled = False
    ctx.control_socket = object()
    ctx.control_thread = type("Thread", (), {"is_alive": lambda self: True})()
    ctx.android_thread = type("Thread", (), {"is_alive": lambda self: True})()
    monkeypatch.setattr("scrcpy.is_power_save_window", lambda: True)

    assert ctx.is_healthy()

    monkeypatch.setattr("scrcpy.is_power_save_window", lambda: False)

    assert not ctx.is_healthy()


def test_power_save_config_uses_integer_hours(monkeypatch):
    monkeypatch.delenv("WEB_SCRCPY_POWER_SAVE_START", raising=False)
    monkeypatch.delenv("WEB_SCRCPY_POWER_SAVE_END", raising=False)

    assert get_power_save_config() == {"start_hour": 23, "end_hour": 6}
    assert set_power_save_config(21, 5) == {"start_hour": 21, "end_hour": 5}
    assert is_power_save_window(datetime(2026, 7, 30, 21, 0))
    assert not is_power_save_window(datetime(2026, 7, 30, 20, 59))


def test_power_save_config_rejects_invalid_hours():
    try:
        set_power_save_config(24, 6)
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid hour to raise ValueError")
