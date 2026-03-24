from threading import Thread
import subprocess
import socket
import time

ADB_PATH = "adb"
SCRCPY_SERVER_PATH = "scrcpy-server"
DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"
BASE_PORT = 5555  # base port for multiple devices

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
        cmd = [
            ADB_PATH, "-s", device, "shell",
            f"CLASSPATH={DEVICE_SERVER_PATH} app_process / com.genymobile.scrcpy.Server 3.1 "
            f"tunnel_forward=true log_level=VERBOSE video_bit_rate=" + self.video_bit_rate + " max_fps=" + str(self.max_fps)
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
                    break
                self.video_callback(data)
            except Exception as e:
                print(f"Video recv error: {e}")
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
                    break
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Audio recv error: {e}")
                break
        print("Audio data reception stopped")

    def handle_control_conn(self):
        print("Control connection established (idle)...")
        try:
            # Try to read protocol version byte (non-blocking attempt)
            self.control_socket.settimeout(1.0)
            try:
                self.control_socket.recv(1)
            except socket.timeout:
                # No initial byte, that's okay - control socket might be send-only
                pass
            self.control_socket.settimeout(None)  # Reset to blocking
        except Exception as e:
            print(f"Error in control handshake: {e}")
        
        while not self.stop:
            try:
                # Set short timeout to allow checking self.stop regularly
                self.control_socket.settimeout(1.0)
                data = self.control_socket.recv(1024)
                if not data:
                    break
                if data:
                    self._process_device_message(data)
            except socket.timeout:
                # Timeout is normal, just loop again to check self.stop
                continue
            except Exception as e:
                print(f"Control recv error: {e}")
                break
        print("Control connection stopped")

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
            # video connection with retry
            self.video_socket = self._connect_with_retry("Video", max_retries=30, retry_delay=0.5)

            # audio connection with retry
            self.audio_socket = self._connect_with_retry("Audio", max_retries=30, retry_delay=0.5)

            # control connection with retry
            self.control_socket = self._connect_with_retry("Control", max_retries=30, retry_delay=0.5)

            self.video_thread = Thread(target=self.receive_video_data, daemon=True)
            self.audio_thread = Thread(target=self.receive_audio_data, daemon=True)
            self.control_thread = Thread(target=self.handle_control_conn, daemon=True)
            self.video_thread.start()
            self.audio_thread.start()
            self.control_thread.start()
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
        
        print("Scrcpy stopped")

    def scrcpy_send_control(self, data):
        self.control_socket.send(data)
