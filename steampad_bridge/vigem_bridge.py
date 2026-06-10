from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
from pathlib import Path

from .state import OutputMode, axis_to_s16, axis_to_u8, trigger_to_u8


XUSB_GAMEPAD_DPAD_UP = 0x0001
XUSB_GAMEPAD_DPAD_DOWN = 0x0002
XUSB_GAMEPAD_DPAD_LEFT = 0x0004
XUSB_GAMEPAD_DPAD_RIGHT = 0x0008
XUSB_GAMEPAD_START = 0x0010
XUSB_GAMEPAD_BACK = 0x0020
XUSB_GAMEPAD_LEFT_THUMB = 0x0040
XUSB_GAMEPAD_RIGHT_THUMB = 0x0080
XUSB_GAMEPAD_LEFT_SHOULDER = 0x0100
XUSB_GAMEPAD_RIGHT_SHOULDER = 0x0200
XUSB_GAMEPAD_A = 0x1000
XUSB_GAMEPAD_B = 0x2000
XUSB_GAMEPAD_X = 0x4000
XUSB_GAMEPAD_Y = 0x8000

DS4_BUTTON_THUMB_RIGHT = 1 << 15
DS4_BUTTON_THUMB_LEFT = 1 << 14
DS4_BUTTON_OPTIONS = 1 << 13
DS4_BUTTON_SHARE = 1 << 12
DS4_BUTTON_TRIGGER_RIGHT = 1 << 11
DS4_BUTTON_TRIGGER_LEFT = 1 << 10
DS4_BUTTON_SHOULDER_RIGHT = 1 << 9
DS4_BUTTON_SHOULDER_LEFT = 1 << 8
DS4_BUTTON_TRIANGLE = 1 << 7
DS4_BUTTON_CIRCLE = 1 << 6
DS4_BUTTON_CROSS = 1 << 5
DS4_BUTTON_SQUARE = 1 << 4
DS4_SPECIAL_BUTTON_PS = 1 << 0
DS4_BUTTON_DPAD_NONE = 0x8


class XUSB_REPORT(ctypes.Structure):
    _fields_ = [
        ("wButtons", wt.USHORT),
        ("bLeftTrigger", wt.BYTE),
        ("bRightTrigger", wt.BYTE),
        ("sThumbLX", wt.SHORT),
        ("sThumbLY", wt.SHORT),
        ("sThumbRX", wt.SHORT),
        ("sThumbRY", wt.SHORT),
    ]


class DS4_REPORT(ctypes.Structure):
    _fields_ = [
        ("bThumbLX", wt.BYTE),
        ("bThumbLY", wt.BYTE),
        ("bThumbRX", wt.BYTE),
        ("bThumbRY", wt.BYTE),
        ("wButtons", wt.USHORT),
        ("bSpecial", wt.BYTE),
        ("bTriggerL", wt.BYTE),
        ("bTriggerR", wt.BYTE),
    ]


class DS4_TOUCH(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("bPacketCounter", wt.BYTE),
        ("bIsUpTrackingNum1", wt.BYTE),
        ("bTouchData1", wt.BYTE * 3),
        ("bIsUpTrackingNum2", wt.BYTE),
        ("bTouchData2", wt.BYTE * 3),
    ]


class DS4_REPORT_EX_INNER(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("bThumbLX", wt.BYTE),
        ("bThumbLY", wt.BYTE),
        ("bThumbRX", wt.BYTE),
        ("bThumbRY", wt.BYTE),
        ("wButtons", wt.USHORT),
        ("bSpecial", wt.BYTE),
        ("bTriggerL", wt.BYTE),
        ("bTriggerR", wt.BYTE),
        ("wTimestamp", wt.USHORT),
        ("bBatteryLvl", wt.BYTE),
        ("wGyroX", wt.SHORT),
        ("wGyroY", wt.SHORT),
        ("wGyroZ", wt.SHORT),
        ("wAccelX", wt.SHORT),
        ("wAccelY", wt.SHORT),
        ("wAccelZ", wt.SHORT),
        ("_bUnknown1", wt.BYTE * 5),
        ("bBatteryLvlSpecial", wt.BYTE),
        ("_bUnknown2", wt.BYTE * 2),
        ("bTouchPacketsN", wt.BYTE),
        ("sCurrentTouch", DS4_TOUCH),
        ("sPreviousTouch", DS4_TOUCH * 2),
    ]


class DS4_REPORT_EX_UNION(ctypes.Union):
    _pack_ = 1
    _fields_ = [("Report", DS4_REPORT_EX_INNER), ("ReportBuffer", wt.BYTE * 63)]


def _load_dll():
    candidates = []
    here = Path(__file__).resolve().parent
    candidates.extend([
        here / "ViGEmClient.dll",
        here.parent / "ViGEmClient.dll",
        Path(os.getcwd()) / "ViGEmClient.dll",
    ])
    try:
        import vgamepad  # type: ignore
        vgamepad_dir = Path(vgamepad.__file__).resolve().parent
        candidates.append(vgamepad_dir / "win" / "vigem" / "client" / "x64" / "ViGEmClient.dll")
        candidates.append(vgamepad_dir / "win" / "x64" / "ViGEmClient.dll")
        candidates.append(vgamepad_dir / "ViGEmClient.dll")
    except Exception:
        pass
    for candidate in candidates:
        if candidate.exists():
            return ctypes.WinDLL(str(candidate))
    return ctypes.WinDLL("ViGEmClient.dll")


class ViGEmBridge:
    def __init__(self, mode: OutputMode):
        self.mode = mode
        self.dll = _load_dll()
        self.client = None
        self.target = None
        self._has_ds4_ex = hasattr(self.dll, "vigem_target_ds4_update_ex")
        self._configure_api()

    def _configure_api(self):
        self.dll.vigem_alloc.restype = ctypes.c_void_p
        self.dll.vigem_free.argtypes = [ctypes.c_void_p]
        self.dll.vigem_connect.argtypes = [ctypes.c_void_p]
        self.dll.vigem_connect.restype = ctypes.c_uint
        self.dll.vigem_disconnect.argtypes = [ctypes.c_void_p]
        self.dll.vigem_target_add.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.dll.vigem_target_add.restype = ctypes.c_uint
        self.dll.vigem_target_remove.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.dll.vigem_target_free.argtypes = [ctypes.c_void_p]

        self.dll.vigem_target_x360_alloc.restype = ctypes.c_void_p
        self.dll.vigem_target_ds4_alloc.restype = ctypes.c_void_p
        self.dll.vigem_target_x360_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, XUSB_REPORT]
        self.dll.vigem_target_x360_update.restype = ctypes.c_uint
        self.dll.vigem_target_ds4_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, DS4_REPORT]
        self.dll.vigem_target_ds4_update.restype = ctypes.c_uint
        if self._has_ds4_ex:
            self.dll.vigem_target_ds4_update_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, DS4_REPORT_EX_UNION]
            self.dll.vigem_target_ds4_update_ex.restype = ctypes.c_uint

    def connect(self):
        self.client = self.dll.vigem_alloc()
        if not self.client:
            raise RuntimeError("vigem_alloc failed")
        error = self.dll.vigem_connect(self.client)
        if error != 0x20000000:
            raise RuntimeError(f"vigem_connect failed: 0x{error:08X}")
        if self.mode == OutputMode.XBOX360:
            self.target = self.dll.vigem_target_x360_alloc()
        else:
            self.target = self.dll.vigem_target_ds4_alloc()
        if not self.target:
            raise RuntimeError("vigem target allocation failed")
        error = self.dll.vigem_target_add(self.client, self.target)
        if error != 0x20000000:
            raise RuntimeError(f"vigem_target_add failed: 0x{error:08X}")

    def close(self):
        if self.client and self.target:
            try:
                self.dll.vigem_target_remove(self.client, self.target)
            except Exception:
                pass
            try:
                self.dll.vigem_target_free(self.target)
            except Exception:
                pass
        if self.client:
            try:
                self.dll.vigem_disconnect(self.client)
            except Exception:
                pass
            try:
                self.dll.vigem_free(self.client)
            except Exception:
                pass
        self.client = None
        self.target = None

    @property
    def supports_ds4_imu(self) -> bool:
        return self.mode == OutputMode.DS4 and self._has_ds4_ex

    def update(self, state):
        if self.mode == OutputMode.XBOX360:
            self._update_x360(state)
        else:
            self._update_ds4(state)

    def _update_x360(self, state):
        buttons = 0
        mapping = [
            (0, XUSB_GAMEPAD_A), (1, XUSB_GAMEPAD_B), (2, XUSB_GAMEPAD_X), (3, XUSB_GAMEPAD_Y),
            (4, XUSB_GAMEPAD_LEFT_SHOULDER), (5, XUSB_GAMEPAD_RIGHT_SHOULDER),
            (6, XUSB_GAMEPAD_BACK), (7, XUSB_GAMEPAD_START),
            (8, XUSB_GAMEPAD_LEFT_THUMB), (9, XUSB_GAMEPAD_RIGHT_THUMB),
            (15, XUSB_GAMEPAD_DPAD_UP), (16, XUSB_GAMEPAD_DPAD_DOWN),
            (17, XUSB_GAMEPAD_DPAD_LEFT), (18, XUSB_GAMEPAD_DPAD_RIGHT),
        ]
        for index, flag in mapping:
            if index < len(state.buttons) and state.buttons[index]:
                buttons |= flag
        report = XUSB_REPORT(
            buttons,
            trigger_to_u8(state.lt),
            trigger_to_u8(state.rt),
            axis_to_s16(state.lx),
            axis_to_s16(state.ly),
            axis_to_s16(state.rx),
            axis_to_s16(state.ry),
        )
        self.dll.vigem_target_x360_update(self.client, self.target, report)

    def _update_ds4(self, state):
        w_buttons = self._ds4_buttons(state)
        base = DS4_REPORT(
            axis_to_u8(state.lx),
            axis_to_u8(state.ly, invert=True),
            axis_to_u8(state.rx),
            axis_to_u8(state.ry, invert=True),
            w_buttons,
            DS4_SPECIAL_BUTTON_PS if len(state.buttons) > 10 and state.buttons[10] else 0,
            trigger_to_u8(state.lt),
            trigger_to_u8(state.rt),
        )
        if self._has_ds4_ex:
            ex = DS4_REPORT_EX_UNION()
            ex.Report.bThumbLX = base.bThumbLX
            ex.Report.bThumbLY = base.bThumbLY
            ex.Report.bThumbRX = base.bThumbRX
            ex.Report.bThumbRY = base.bThumbRY
            ex.Report.wButtons = base.wButtons
            ex.Report.bSpecial = base.bSpecial
            ex.Report.bTriggerL = base.bTriggerL
            ex.Report.bTriggerR = base.bTriggerR
            ex.Report.bBatteryLvl = 0x0C
            ex.Report.bBatteryLvlSpecial = 0x10
            ex.Report.sCurrentTouch.bIsUpTrackingNum1 = 0x80
            ex.Report.sCurrentTouch.bIsUpTrackingNum2 = 0x80
            ex.Report.wGyroX = int(state.gyro_x)
            ex.Report.wGyroY = int(state.gyro_y)
            ex.Report.wGyroZ = int(state.gyro_z)
            ex.Report.wAccelX = int(state.accel_x)
            ex.Report.wAccelY = int(state.accel_y)
            ex.Report.wAccelZ = int(state.accel_z)
            self.dll.vigem_target_ds4_update_ex(self.client, self.target, ex)
        else:
            self.dll.vigem_target_ds4_update(self.client, self.target, base)

    def _ds4_buttons(self, state):
        buttons = self._ds4_dpad(state)
        mapping = [
            (0, DS4_BUTTON_CROSS), (1, DS4_BUTTON_CIRCLE), (2, DS4_BUTTON_SQUARE), (3, DS4_BUTTON_TRIANGLE),
            (4, DS4_BUTTON_SHOULDER_LEFT), (5, DS4_BUTTON_SHOULDER_RIGHT),
            (6, DS4_BUTTON_SHARE), (7, DS4_BUTTON_OPTIONS),
            (8, DS4_BUTTON_THUMB_LEFT), (9, DS4_BUTTON_THUMB_RIGHT),
        ]
        for index, flag in mapping:
            if index < len(state.buttons) and state.buttons[index]:
                buttons |= flag
        if state.lt > 0.1:
            buttons |= DS4_BUTTON_TRIGGER_LEFT
        if state.rt > 0.1:
            buttons |= DS4_BUTTON_TRIGGER_RIGHT
        return buttons

    @staticmethod
    def _ds4_dpad(state):
        x = state.dpad_x
        y = state.dpad_y
        if x == 0 and y > 0:
            return 0x0
        if x > 0 and y > 0:
            return 0x1
        if x > 0 and y == 0:
            return 0x2
        if x > 0 and y < 0:
            return 0x3
        if x == 0 and y < 0:
            return 0x4
        if x < 0 and y < 0:
            return 0x5
        if x < 0 and y == 0:
            return 0x6
        if x < 0 and y > 0:
            return 0x7
        return DS4_BUTTON_DPAD_NONE
