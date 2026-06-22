from __future__ import annotations

import ctypes
import threading
import time
from collections import deque

try:
    import sdl2
except ImportError:
    sdl2 = None

from .state import GamepadState, clamp


_sdl_initialized = False
_sdl_init_lock = threading.Lock()


def init_sdl():
    global _sdl_initialized
    if sdl2 is None:
        raise RuntimeError("pysdl2 is not installed")
        
    with _sdl_init_lock:
        if not _sdl_initialized:
            # Set hints to enable advanced drivers (explicitly disabling Steam so SDL2 won't hook it)
            sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_PS4, b"1")
            sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_PS4_RUMBLE, b"1")
            sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_PS5, b"1")
            sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_PS5_RUMBLE, b"1")
            sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_STEAM, b"0")
            sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_SWITCH, b"1")

            if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_SENSOR) == 0:
                _sdl_initialized = True
            else:
                err = sdl2.SDL_GetError().decode("utf-8", errors="ignore")
                raise RuntimeError(f"SDL_Init failed: {err}")


def is_virtual_controller(controller) -> bool:
    joystick = sdl2.SDL_GameControllerGetJoystick(controller)
    if not joystick:
        return False
        
    # Get device path to check if it's virtual
    path = None
    if hasattr(sdl2, "SDL_GameControllerGetPath"):
        p = sdl2.SDL_GameControllerGetPath(controller)
        if p:
            path = p.decode("utf-8", errors="ignore")
            
    if not path and hasattr(sdl2, "SDL_JoystickGetPath"):
        p = sdl2.SDL_JoystickGetPath(joystick)
        if p:
            path = p.decode("utf-8", errors="ignore")
            
    if path:
        path_lower = path.lower()
        if "root" in path_lower or "virtual" in path_lower or "vigem" in path_lower:
            return True
            
    # Check if the device name contains indicator strings
    name = sdl2.SDL_GameControllerName(controller)
    if name:
        name_str = name.decode("utf-8", errors="ignore").lower()
        if "virtual" in name_str or "vigem" in name_str:
            return True
            
    return False


def is_steam_controller(controller) -> bool:
    joystick = sdl2.SDL_GameControllerGetJoystick(controller)
    if not joystick:
        return False
    vid = sdl2.SDL_JoystickGetVendor(joystick)
    return vid == 0x28DE


class SDLControllerDirect:
    """Direct reader for any gamepad using SDL2."""

    def __init__(self, device):
        self.device = device
        self.state = GamepadState()
        self.samples = deque(maxlen=2048)
        self._gyro_enabled = False
        self._accel_enabled = False
        self._name = "Game Controller"
        self._last_pump = 0.0

        name_bytes = sdl2.SDL_GameControllerName(self.device)
        if name_bytes:
            self._name = name_bytes.decode("utf-8", errors="ignore")

        # Enable gyroscope sensor
        if sdl2.SDL_GameControllerHasSensor(self.device, sdl2.SDL_SENSOR_GYRO):
            if sdl2.SDL_GameControllerSetSensorEnabled(self.device, sdl2.SDL_SENSOR_GYRO, sdl2.SDL_TRUE) == 0:
                self._gyro_enabled = True

        # Enable accelerometer sensor
        if sdl2.SDL_GameControllerHasSensor(self.device, sdl2.SDL_SENSOR_ACCEL):
            if sdl2.SDL_GameControllerSetSensorEnabled(self.device, sdl2.SDL_SENSOR_ACCEL, sdl2.SDL_TRUE) == 0:
                self._accel_enabled = True

    @classmethod
    def open_first(cls) -> SDLControllerDirect | None:
        if sdl2 is None:
            return None
            
        try:
            init_sdl()
        except Exception:
            return None

        sdl2.SDL_PumpEvents()
        num_joysticks = sdl2.SDL_NumJoysticks()
        for i in range(num_joysticks):
            if sdl2.SDL_IsGameController(i):
                ctrl = sdl2.SDL_GameControllerOpen(i)
                if ctrl:
                    if is_virtual_controller(ctrl) or is_steam_controller(ctrl):
                        sdl2.SDL_GameControllerClose(ctrl)
                        continue
                    return cls(ctrl)
        return None

    def update(self) -> bool:
        if not self.device:
            return False

        now = time.perf_counter()
        if now - self._last_pump >= 0.1:
            sdl2.SDL_PumpEvents()
            self._last_pump = now
        else:
            sdl2.SDL_GameControllerUpdate()
            sdl2.SDL_SensorUpdate()

        # Check if the device is still connected
        joystick = sdl2.SDL_GameControllerGetJoystick(self.device)

        if not joystick or not sdl2.SDL_JoystickGetAttached(joystick):
            self.close()
            return False

        # Read buttons
        buttons = [0] * 19
        button_mapping = [
            (0, sdl2.SDL_CONTROLLER_BUTTON_A),
            (1, sdl2.SDL_CONTROLLER_BUTTON_B),
            (2, sdl2.SDL_CONTROLLER_BUTTON_X),
            (3, sdl2.SDL_CONTROLLER_BUTTON_Y),
            (4, sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER),
            (5, sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER),
            (6, sdl2.SDL_CONTROLLER_BUTTON_BACK),
            (7, sdl2.SDL_CONTROLLER_BUTTON_START),
            (8, sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK),
            (9, sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK),
            (10, sdl2.SDL_CONTROLLER_BUTTON_GUIDE),
            (11, sdl2.SDL_CONTROLLER_BUTTON_PADDLE1),
            (12, sdl2.SDL_CONTROLLER_BUTTON_PADDLE2),
            (13, sdl2.SDL_CONTROLLER_BUTTON_PADDLE3),
            (14, sdl2.SDL_CONTROLLER_BUTTON_PADDLE4),
            (15, sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP),
            (16, sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN),
            (17, sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT),
            (18, sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT),
        ]

        for idx, sdl_btn in button_mapping:
            buttons[idx] = int(sdl2.SDL_GameControllerGetButton(self.device, sdl_btn))

        self.state.buttons = buttons

        # Read axes (normalized to [-1.0, 1.0], Y-axis is inverted to match state convention)
        def get_axis_val(sdl_axis, invert=False):
            val = sdl2.SDL_GameControllerGetAxis(self.device, sdl_axis)
            norm = val / 32767.0
            if invert:
                norm = -norm
            return clamp(norm, -1.0, 1.0)

        self.state.lx = get_axis_val(sdl2.SDL_CONTROLLER_AXIS_LEFTX)
        self.state.ly = get_axis_val(sdl2.SDL_CONTROLLER_AXIS_LEFTY, invert=True)
        self.state.rx = get_axis_val(sdl2.SDL_CONTROLLER_AXIS_RIGHTX)
        self.state.ry = get_axis_val(sdl2.SDL_CONTROLLER_AXIS_RIGHTY, invert=True)

        # Read triggers (normalized to [0.0, 1.0])
        def get_trigger_val(sdl_axis):
            val = sdl2.SDL_GameControllerGetAxis(self.device, sdl_axis)
            return clamp(val / 32767.0, 0.0, 1.0)

        self.state.lt = get_trigger_val(sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT)
        self.state.rt = get_trigger_val(sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT)

        # Read sensors
        sample_time = time.perf_counter()
        if self._gyro_enabled:
            gyro_data = (ctypes.c_float * 3)()
            if sdl2.SDL_GameControllerGetSensorData(self.device, sdl2.SDL_SENSOR_GYRO, gyro_data, 3) == 0:
                # Convert rad/s to raw DS4 gyro units (1 rad/s is approx 939.85 units)
                self.state.gyro_x = int(round(gyro_data[0] * 939.85))
                self.state.gyro_y = int(round(gyro_data[1] * 939.85))
                self.state.gyro_z = int(round(gyro_data[2] * 939.85))
                self.state.has_imu = True
            else:
                self.state.has_imu = False
        else:
            self.state.has_imu = False

        if self._accel_enabled:
            accel_data = (ctypes.c_float * 3)()
            if sdl2.SDL_GameControllerGetSensorData(self.device, sdl2.SDL_SENSOR_ACCEL, accel_data, 3) == 0:
                # Convert m/s² to raw DS4 accel units (1 G = 9.80665 m/s² = 8192 units)
                self.state.accel_x = int(round(accel_data[0] * 835.3))
                self.state.accel_y = int(round(accel_data[1] * 835.3))
                self.state.accel_z = int(round(accel_data[2] * 835.3))

        self.state.updated_at = sample_time
        self.samples.append((self.state.lx, self.state.ly, self.state.rx, self.state.ry, sample_time))
        return True

    def close(self):
        if self.device:
            try:
                sdl2.SDL_GameControllerClose(self.device)
            except Exception:
                pass
            self.device = None

    @property
    def label(self) -> str:
        return self._name
