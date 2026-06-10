from __future__ import annotations

import threading
import time
from collections import deque

try:
    import hid
except ImportError:  # pragma: no cover - exercised on machines without hidapi
    hid = None

from .state import GamepadState, clamp


class SteamControllerDirect:
    """Direct HID reader for Valve Steam Controller devices."""

    VALVE_VID = 0x28DE
    SC2026_WIRED_PID = 0x1302
    SC2026_DONGLE_PID = 0x1304
    SUPPORTED_PIDS = {SC2026_WIRED_PID, SC2026_DONGLE_PID}
    VENDOR_USAGE_PAGE = 0xFF00
    REPORT_STATE = 0x42
    REPORT_EXTENDED_STATE = 0x45
    REPORT_PUCK_STATE = 0x47
    SERVICE_REPORTS = {0x7B}
    FEATURE_REPORT_CMD = 0x01
    FEATURE_REPORT_CMD_FALLBACK = 0x02
    CMD_CLEAR_DIGITAL_MAPPINGS = 0x81
    CMD_SET_DEFAULT_MAPPINGS = 0x85
    CMD_SET_SETTINGS = 0x87
    SETTING_RIGHT_TRACKPAD_MODE = 0x07
    SETTING_LEFT_TRACKPAD_MODE = 0x08
    TRACKPAD_NONE = 0x00

    BUTTON_BITS = (
        (2, 0x01),  # A
        (2, 0x02),  # B
        (2, 0x04),  # X
        (2, 0x08),  # Y
        (4, 0x08),  # LB
        (3, 0x02),  # RB
        (3, 0x40),  # View
        (2, 0x40),  # Menu
        (3, 0x80),  # LS click
        (2, 0x20),  # RS click
        (4, 0x01),  # Steam
        (4, 0x02),  # L4
        (2, 0x80),  # R4
        (4, 0x04),  # L5
        (3, 0x01),  # R5
        (3, 0x20),  # D-pad up
        (3, 0x04),  # D-pad down
        (3, 0x10),  # D-pad left
        (3, 0x08),  # D-pad right
    )

    def __init__(self, path):
        self.path = path
        self.device = None
        self.device_info = None
        self.state = GamepadState()
        self.samples = deque(maxlen=2048)
        self._running = False
        self._heartbeat = None

    @classmethod
    def available_devices(cls):
        if hid is None:
            return []
        devices = []
        for dev in cls.valve_devices():
            product_id = dev.get("product_id")
            product = (dev.get("product_string") or "").lower()
            usage_page = dev.get("usage_page")
            usage = dev.get("usage")
            is_known_pid = product_id in cls.SUPPORTED_PIDS
            is_steam_controller = "steam" in product and "controller" in product
            is_input_interface = usage_page == cls.VENDOR_USAGE_PAGE and usage == 1
            if (is_known_pid or is_steam_controller) and is_input_interface:
                devices.append(dev)
        devices.sort(key=cls._device_rank)
        return devices[:1]

    @classmethod
    def valve_devices(cls):
        if hid is None:
            return []
        return [dev for dev in hid.enumerate() if dev.get("vendor_id") == cls.VALVE_VID]

    @classmethod
    def _device_rank(cls, dev):
        product_id = dev.get("product_id")
        iface = dev.get("interface_number")
        return (
            0 if product_id == cls.SC2026_WIRED_PID else 1,
            0 if dev.get("usage_page") == cls.VENDOR_USAGE_PAGE else 1,
            0 if dev.get("usage") == 1 else 1,
            0 if product_id == cls.SC2026_DONGLE_PID and iface == 2 else 1,
            iface if isinstance(iface, int) and iface >= 0 else 99,
        )

    @classmethod
    def open_first(cls):
        devices = cls.available_devices()
        if not devices:
            return None
        controller = cls(devices[0]["path"])
        controller.device_info = devices[0]
        controller.open()
        return controller

    def open(self):
        if self.device:
            return
        if hid is None:
            raise RuntimeError("Python hidapi package is not installed")
        self.device = hid.device()
        self.device.open_path(self.path)
        try:
            self.device.set_nonblocking(True)
        except Exception:
            pass
        self.disable_lizard_mode()

    def close(self):
        self._running = False
        if self._heartbeat:
            self._heartbeat.join(timeout=0.25)
            self._heartbeat = None
        try:
            self._send_command(self.CMD_SET_DEFAULT_MAPPINGS)
        except Exception:
            pass
        try:
            if self.device:
                self.device.close()
        except Exception:
            pass
        self.device = None

    def disable_lizard_mode(self):
        if self._send_command(self.CMD_CLEAR_DIGITAL_MAPPINGS):
            payload = [
                self.SETTING_RIGHT_TRACKPAD_MODE, self.TRACKPAD_NONE, 0,
                self.SETTING_LEFT_TRACKPAD_MODE, self.TRACKPAD_NONE, 0,
            ]
            self._send_command(self.CMD_SET_SETTINGS, payload)
        if not self._running:
            self._running = True
            self._heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat.start()

    def _heartbeat_loop(self):
        while self._running:
            self._send_command(self.CMD_CLEAR_DIGITAL_MAPPINGS)
            time.sleep(0.8)

    def _send_command(self, command, payload=None):
        payload = payload or []
        for report_id in (self.FEATURE_REPORT_CMD, self.FEATURE_REPORT_CMD_FALLBACK):
            buf = [0] * 65
            buf[0] = report_id
            buf[1] = command
            buf[2] = len(payload)
            buf[3:3 + len(payload)] = payload
            try:
                if self.device and self.device.send_feature_report(buf) > 0:
                    return True
            except Exception:
                continue
        return False

    def update(self) -> bool:
        if not self.device:
            return False
        changed = False
        for _ in range(32):
            try:
                data = self.device.read(64, 0)
            except TypeError:
                data = self.device.read(64)
            except Exception:
                self.close()
                return False
            if not data:
                break
            if data[0] in self.SERVICE_REPORTS:
                continue
            if data[0] not in (self.REPORT_STATE, self.REPORT_EXTENDED_STATE, self.REPORT_PUCK_STATE):
                continue
            self._parse_state_report(data, time.perf_counter())
            changed = True
        return changed

    def _parse_state_report(self, data, sample_time):
        def s16(offset):
            if offset + 2 > len(data):
                return 0
            return int.from_bytes(bytes(data[offset:offset + 2]), "little", signed=True)

        def axis(offset, invert=False):
            value = s16(offset)
            if invert:
                value = -value
            return clamp(value / 32767.0, -1.0, 1.0)

        state = self.state
        state.buttons = [1 if data[offset] & mask else 0 for offset, mask in self.BUTTON_BITS if offset < len(data)]
        while len(state.buttons) < len(self.BUTTON_BITS):
            state.buttons.append(0)

        if len(data) >= 18:
            state.lx = axis(10)
            state.ly = axis(12)
            state.rx = axis(14)
            state.ry = axis(16)
            state.lt = clamp((s16(6) / 32767.0) * 2.0 - 1.0, -1.0, 1.0)
            state.rt = clamp((s16(8) / 32767.0) * 2.0 - 1.0, -1.0, 1.0)
            state.lt = clamp((state.lt + 1.0) * 0.5, 0.0, 1.0)
            state.rt = clamp((state.rt + 1.0) * 0.5, 0.0, 1.0)

        # hidapi includes the report ID at data[0]. The WebHID tester receives
        # payload bytes without it, so these offsets are WebHID offsets + 1.
        if data[0] in (self.REPORT_STATE, self.REPORT_EXTENDED_STATE, self.REPORT_PUCK_STATE) and len(data) >= 46:
            accel_x = s16(34)
            accel_y = s16(36)
            accel_z = s16(38)
            gyro_x = s16(40)
            gyro_y = s16(42)
            gyro_z = s16(44)

            # Convert Valve IMU into raw DS4 report units. SticTracerWeb reads
            # DS4 as: pitch=-gyroX, yaw=gyroY, roll=gyroZ. Valve/Triton maps as:
            # pitch=-gyroX, roll=-gyroY, yaw=gyroZ. Therefore the DS4 raw report
            # must be X=Valve X, Y=Valve Z, Z=-Valve Y.
            state.accel_x = accel_x // 2
            state.accel_y = accel_y // 2
            state.accel_z = -accel_z // 2
            state.gyro_x = gyro_x
            state.gyro_y = gyro_z
            state.gyro_z = -gyro_y
            state.has_imu = True
        else:
            state.has_imu = False

        state.updated_at = sample_time
        self.samples.append((state.lx, state.ly, state.rx, state.ry, sample_time))

    @property
    def label(self):
        if self.device_info and self.device_info.get("product_id") == self.SC2026_DONGLE_PID:
            return "Steam Controller (receiver)"
        return "Steam Controller (USB)"
