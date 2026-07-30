from threading import Thread
import subprocess
import socket
import time
import os
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

ADB_PATH = "adb"
SCRCPY_SERVER_PATH = "scrcpy-server"
DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"
BASE_PORT = 5555  # base port for multiple devices
POWER_SAVE_START_ENV = "WEB_SCRCPY_POWER_SAVE_START"
POWER_SAVE_END_ENV = "WEB_SCRCPY_POWER_SAVE_END"
POWER_SAVE_TIMEZONE_ENV = "WEB_SCRCPY_POWER_SAVE_TIMEZONE"
VIDEO_DISABLED_OVERRIDE_ENV = "WEB_SCRCPY_VIDEO_DISABLED_OVERRIDE"
DEFAULT_POWER_SAVE_START = "22:00"
DEFAULT_POWER_SAVE_END = "07:00"
DEFAULT_POWER_SAVE_TIMEZONE = "America/Toronto"


def _parse_hhmm(value, default):
    try:
        hour, minute = value.split(":", 1)
        return dt_time(int(hour), int(minute))
    except (AttributeError, TypeError, ValueError):
        print(f"Invalid power-save time {value!r}; using {default}")
        hour, minute = default.split(":", 1)
        return dt_time(int(hour), int(minute))


def _format_hour(hour):
    return f"{hour:02d}:00"


def _time_to_hour(value, default):
    parsed = _parse_hhmm(value, default)
    return parsed.hour


def get_power_save_config():
    """Return the active power-save schedule as integer hours for UI/API use."""
    start_value = os.environ.get(POWER_SAVE_START_ENV, DEFAULT_POWER_SAVE_START)
    end_value = os.environ.get(POWER_SAVE_END_ENV, DEFAULT_POWER_SAVE_END)
    return {
        'start_hour': _time_to_hour(start_value, DEFAULT_POWER_SAVE_START),
        'end_hour': _time_to_hour(end_value, DEFAULT_POWER_SAVE_END),
    }


def set_power_save_config(start_hour, end_hour):
    """Set the power-save schedule using integer hours from 0 through 23."""
    start = int(start_hour)
    end = int(end_hour)
    if not 0 <= start <= 23 or not 0 <= end <= 23:
        raise ValueError('power-save hours must be between 0 and 23')
    os.environ[POWER_SAVE_START_ENV] = _format_hour(start)
    os.environ[POWER_SAVE_END_ENV] = _format_hour(end)
    return get_power_save_config()


def set_video_disabled_override(enabled):
    """Force video off regardless of the power-save schedule."""
    if isinstance(enabled, str):
        enabled = enabled.lower() in {'1', 'true', 'yes', 'on'}
    os.environ[VIDEO_DISABLED_OVERRIDE_ENV] = '1' if bool(enabled) else '0'


def is_video_disabled_override():
    """Return whether video is manually forced off."""
    return os.environ.get(VIDEO_DISABLED_OVERRIDE_ENV, '').lower() in {'1', 'true', 'yes', 'on'}


def get_power_save_timezone():
    """Return the timezone used for power-save schedule evaluation."""
    return os.environ.get(POWER_SAVE_TIMEZONE_ENV, DEFAULT_POWER_SAVE_TIMEZONE)


def get_power_save_now():
    """Return the current datetime in the configured power-save timezone."""
    return datetime.now(ZoneInfo(get_power_save_timezone()))


def is_power_save_window(now=None):
    """Return True during the configured no-playback power-save window."""
    current = (now or get_power_save_now()).time()
    current_hour = current.hour
    config = get_power_save_config()
    start_hour = config['start_hour']
    end_hour = config['end_hour']

    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour

    # Overnight windows are two explicit ranges: start_hour..24 and 0..end_hour.
    return start_hour <= current_hour < 24 or 0 <= current_hour < end_hour


def should_enable_video(now=None):
    """Return whether new or healthy sessions should run scrcpy video."""
    return not is_video_disabled_override() and not is_power_save_window(now)


class Scrcpy:
    def __init__(self, device_udid=None):
        self.video_socket = None
        self.audio_socket = None
        self.control_socket = None

        self.android_thread = None
        self.video_thread = None
        self.audio_thread = None
        self.control_thread = None
        self.android_process = None

        self.devices = []          # list of devices
        self.device_ports = {}     # map device -> local port
        self.next_port = BASE_PORT
        self.device_udid = device_udid  # device to use
        self.selected_device = None     # selected device details
        self.device_port = None         # port for this device
        self.stop = False
        self.running = False  # Flag to track if this instance is actively streaming
        self.device_message_callback = None
        self.control_recv_buffer = bytearray()
        self.health_thread = None
        self._first_video_chunk_logged = False
        self.video_enabled = True

    def list_devices(self):
        """Populate self.devices and assign unique local ports per device."""
        result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
        self.devices = [line.split()[0] for line in result.stdout.splitlines() if "\tdevice" in line]
        self.device_ports = {device: self.next_port + i for i, device in enumerate(self.devices)}
        
        # If device_udid specified, select that device
        if self.device_udid:
            if self.device_udid in self.devices:
                self.selected_device = self.device_udid
                self.device_port = self.device_ports[self.device_udid]
                print(f"Selected device: {self.device_udid}, port: {self.device_port}")
            else:
                print(f"Error: Device {self.device_udid} not found in connected devices")
                print(f"Available devices: {self.devices}")
                return []
        else:
            # If no device specified, use first device
            if self.devices:
                self.selected_device = self.devices[0]
                self.device_port = self.device_ports[self.selected_device]
                print(f"No device specified, using first device: {self.selected_device}, port: {self.device_port}")
        
        return self.devices

    def push_server_to_device(self):
        print("Pushing scrcpy-server.jar to device...")
        if not self.devices:
            self.list_devices()
        
        if not self.selected_device:
            print("No device selected")
            return False

        device = self.selected_device
        print(f"Pushing to {device}")
        cmd = [ADB_PATH, "-s", device, "push", SCRCPY_SERVER_PATH, DEVICE_SERVER_PATH]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"[{device}] Error pushing server")
            print("Command:", " ".join(cmd))
            print("Return code:", result.returncode)
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
        else:
            print(f"[{device}] Push succeeded")
            return True

    def setup_adb_forward(self):
        if not self.devices:
            self.list_devices()

        if not self.selected_device:
            print("No device selected")
            return

        device = self.selected_device
        local_port = self.device_port
        print(f"Setting up ADB forward for {device}: tcp:{local_port} -> localabstract:scrcpy")
        subprocess.run(
            [ADB_PATH, "-s", device, "forward", f"tcp:{local_port}", "localabstract:scrcpy"],
            check=True
        )

    def start_server(self):
        if not self.devices:
            self.list_devices()

        if not self.selected_device:
            print("No device selected")
            return

        device = self.selected_device
        print(f"Starting scrcpy server on {device}...")
        server_options = [
            "tunnel_forward=true",
            "log_level=VERBOSE",
            "audio=false",
            f"video={str(self.video_enabled).lower()}",
            "control=true",
            "turn_screen_off=true",
        ]
        if self.video_enabled:
            server_options.extend([
                f"video_bit_rate={self.video_bit_rate}",
                f"max_fps={self.max_fps}",
            ])

        cmd = [
            ADB_PATH, "-s", device, "shell",
            f"CLASSPATH={DEVICE_SERVER_PATH} app_process / com.genymobile.scrcpy.Server 3.1 "
            + " ".join(server_options)
        ]
        self.android_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        while not self.stop:
            stderr_line = self.android_process.stderr.readline().decode().strip()
            if not stderr_line:
                break
            if stderr_line:
                print(f"[{device}] Server error: {stderr_line}")

        self.android_process.wait()
        print(f"[{device}] Server stopped")

    def receive_video_data(self):
        print("Receiving video data (H.264)...")
        try:
            # Try to read protocol version byte (non-blocking attempt)
            self.video_socket.settimeout(1.0)
            try:
                self.video_socket.recv(1)
            except socket.timeout:
                # No initial byte, that's okay - continue anyway
                pass
            self.video_socket.settimeout(None)  # Reset to blocking
        except Exception as e:
            print(f"Error in video handshake: {e}")
        
        while not self.stop:
            try:
                data = self.video_socket.recv(20480)
                if not data:
                    if not self.stop:
                        self.running = False
                    break
                if not self._first_video_chunk_logged:
                    self._first_video_chunk_logged = True
                    head = data[:24]
                    head_hex = " ".join(f"{b:02x}" for b in head)
                    head_ascii = "".join(chr(b) if 32 <= b <= 126 else "." for b in head)
                    print(f"[{self.selected_device}] First video chunk head hex: {head_hex}")
                    print(f"[{self.selected_device}] First video chunk head ascii: {head_ascii}")
                    if b"OpusHead" in data[:128]:
                        print(f"[{self.selected_device}] WARNING: video socket appears to carry Opus audio bytes")
                self.video_callback(data)
            except Exception as e:
                print(f"Video recv error: {e}")
                if not self.stop:
                    self.running = False
                break
        print("Video data reception stopped")

    def receive_audio_data(self):
        print("Receiving audio data...")
        try:
            self.audio_socket.settimeout(1.0)
            try:
                self.audio_socket.recv(1)
            except socket.timeout:
                pass
            self.audio_socket.settimeout(None)
        except Exception as e:
            print(f"Error in audio handshake: {e}")
        
        while not self.stop:
            try:
                self.audio_socket.settimeout(1.0)
                data = self.audio_socket.recv(1024)
                if not data:
                    if not self.stop:
                        self.running = False
                    break
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Audio recv error: {e}")
                if not self.stop:
                    self.running = False
                break
        print("Audio data reception stopped")

    def handle_control_conn(self):
        print("Control connection established (idle)...")
        
        while not self.stop:
            try:
                # Set short timeout to allow checking self.stop regularly
                self.control_socket.settimeout(1.0)
                data = self.control_socket.recv(1024)
                if not data:
                    if not self.stop:
                        self.running = False
                    break
                if data:
                    self._process_device_message(data)
            except socket.timeout:
                # Timeout is normal, just loop again to check self.stop
                continue
            except Exception as e:
                print(f"Control recv error: {e}")
                if not self.stop:
                    self.running = False
                break
        print("Control connection stopped")

    def _health_watchdog(self):
        """Periodically downgrade running flag when stream threads/sockets are unhealthy."""
        while not self.stop:
            if self.running and not self.is_healthy():
                print(f"[{self.selected_device}] Health watchdog marked session unhealthy")
                self.running = False
            time.sleep(1.0)

    def _process_device_message(self, data):
        self.control_recv_buffer.extend(data)
        magic = b"scrcpy_message"
        magic_len = len(magic)

        while True:
            idx = self.control_recv_buffer.find(magic)
            if idx < 0:
                # Keep tail in case part of magic arrives split across packets
                if len(self.control_recv_buffer) > magic_len:
                    del self.control_recv_buffer[:-magic_len]
                return
            if idx > 0:
                del self.control_recv_buffer[:idx]
            if len(self.control_recv_buffer) < magic_len + 1:
                return

            msg_type = self.control_recv_buffer[magic_len]
            if msg_type == 0:  # clipboard
                if len(self.control_recv_buffer) < magic_len + 5:
                    return
                text_len = int.from_bytes(
                    self.control_recv_buffer[magic_len + 1:magic_len + 5],
                    byteorder='big',
                    signed=True
                )
                total_len = magic_len + 1 + 4 + max(0, text_len)
                if len(self.control_recv_buffer) < total_len:
                    return
                text_start = magic_len + 5
                text_end = text_start + max(0, text_len)
                text = bytes(self.control_recv_buffer[text_start:text_end]).decode('utf-8', errors='replace')
                if self.device_message_callback:
                    self.device_message_callback({'type': 'clipboard', 'text': text})
                del self.control_recv_buffer[:total_len]
            elif msg_type == 101:  # file push response
                total_len = magic_len + 1 + 2 + 1
                if len(self.control_recv_buffer) < total_len:
                    return
                del self.control_recv_buffer[:total_len]
            else:
                # Unknown payload; discard this magic marker and continue.
                del self.control_recv_buffer[:magic_len + 1]

    def _connect_with_retry(self, socket_type, max_retries=30, retry_delay=0.5):
        """Connect to localhost:device_port with retry logic that verifies connection is alive."""
        sock = None
        
        for attempt in range(max_retries):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.connect(('localhost', self.device_port))
                
                # Verify connection is alive by trying non-blocking recv
                # If we get 0 bytes, socket was closed by peer (scrcpy not ready)
                sock.setblocking(False)
                try:
                    data = sock.recv(1)
                    if len(data) == 0:
                        # Connection closed by peer - scrcpy server not ready yet
                        sock.close()
                        if attempt < max_retries - 1:
                            wait_time = min(retry_delay * (1.5 ** attempt), 5.0)
                            time.sleep(wait_time)
                        continue
                except BlockingIOError:
                    # No data yet (EAGAIN) - this is normal, socket is alive
                    pass
                
                sock.setblocking(True)
                print(f"{socket_type} connection established after {attempt} attempts")
                return sock
                
            except (ConnectionRefusedError, OSError) as e:
                if sock:
                    try:
                        sock.close()
                    except:
                        pass
                    sock = None
                if attempt < max_retries - 1:
                    wait_time = min(retry_delay * (1.5 ** attempt), 5.0)
                    time.sleep(wait_time)
                else:
                    raise Exception(f"{socket_type} connection failed after {max_retries} attempts")
        
        raise Exception(f"{socket_type} connection failed")

    def scrcpy_start(self, video_callback, video_bit_rate, max_fps, device_message_callback=None, device_udid=None):
        if device_udid:
            self.device_udid = device_udid
            
        self.video_bit_rate = video_bit_rate
        self.max_fps = max_fps
        self.video_callback = video_callback
        self.device_message_callback = device_message_callback
        self.control_recv_buffer = bytearray()
        self._first_video_chunk_logged = False
        self.video_enabled = should_enable_video()
        self.stop = False

        result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
        if "device" not in result.stdout:
            print("No device found. Please connect your Android device via USB.")
            return
        print(result.stdout)

        # List devices and select the specified one
        self.list_devices()
        
        if not self.selected_device:
            print("Failed to select device")
            return

        if not self.push_server_to_device():
            print("Failed to push server files to device.")
            return

        self.setup_adb_forward()
        self.android_thread = Thread(target=self.start_server, daemon=True)
        self.android_thread.start()
        
        # CRITICAL: Wait for server to initialize on device
        print("Waiting 3s for server to initialize...")
        time.sleep(3)

        try:
            if self.video_enabled:
                # video connection with retry
                self.video_socket = self._connect_with_retry("Video", max_retries=30, retry_delay=0.5)
            else:
                print(f"[{self.selected_device}] Power-save window active: starting scrcpy with no playback and screen off")

            # control connection with retry
            self.control_socket = self._connect_with_retry("Control", max_retries=30, retry_delay=0.5)

            if self.video_enabled:
                self.video_thread = Thread(target=self.receive_video_data, daemon=True)
                self.video_thread.start()
            else:
                self.video_thread = None
            self.control_thread = Thread(target=self.handle_control_conn, daemon=True)
            self.control_thread.start()
            self.health_thread = Thread(target=self._health_watchdog, daemon=True)
            self.health_thread.start()
            print("Background tasks started")
            self.running = True  # Mark instance as successfully running
        except Exception as e:
            print(f"Failed to connect: {e}")
            self.scrcpy_stop()
            raise

    def scrcpy_stop(self):
        print("Stopping Scrcpy")
        self.stop = True
        self.running = False  # Mark as no longer running
        
        # Close sockets first (will cause receive threads to exit)
        try:
            if self.control_socket:
                try:
                    self.control_socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self.control_socket.close()
                self.control_socket = None
        except Exception as e:
            print(f"Control socket shutdown error: {e}")
        
        try:
            if self.audio_socket:
                try:
                    self.audio_socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self.audio_socket.close()
                self.audio_socket = None
        except Exception as e:
            print(f"Audio socket shutdown error: {e}")
        
        try:
            if self.video_socket:
                try:
                    self.video_socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self.video_socket.close()
                self.video_socket = None
        except Exception as e:
            print(f"Video socket shutdown error: {e}")

        # Wait for threads to exit
        try:
            if self.video_thread and self.video_thread.is_alive():
                self.video_thread.join(timeout=2)
        except Exception as e:
            print(f"Video thread join error: {e}")
        
        try:
            if self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=2)
        except Exception as e:
            print(f"Audio thread join error: {e}")
        
        try:
            if self.control_thread and self.control_thread.is_alive():
                self.control_thread.join(timeout=2)
        except Exception as e:
            print(f"Control thread join error: {e}")
        
        try:
            if self.android_process:
                self.android_process.terminate()
                self.android_process.wait(timeout=2)
        except Exception as e:
            print(f"Android process terminate error: {e}")
        
        try:
            if self.android_thread and self.android_thread.is_alive():
                self.android_thread.join(timeout=2)
        except Exception as e:
            print(f"Android thread join error: {e}")

        try:
            if self.health_thread and self.health_thread.is_alive():
                self.health_thread.join(timeout=2)
        except Exception as e:
            print(f"Health thread join error: {e}")
        
        print("Scrcpy stopped")

    def scrcpy_send_control(self, data):
        try:
            self.control_socket.send(data)
        except Exception:
            self.running = False
            raise

    def is_healthy(self):
        if self.stop or not self.running:
            return False
        if self.video_enabled != should_enable_video():
            return False
        if self.control_socket is None:
            return False
        if self.video_enabled:
            if self.video_socket is None:
                return False
            if self.video_thread is None or not self.video_thread.is_alive():
                return False
        if self.control_thread is None or not self.control_thread.is_alive():
            return False
        if self.android_thread is None or not self.android_thread.is_alive():
            return False
        return True
