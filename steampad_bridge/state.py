from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OutputMode(str, Enum):
    XBOX360 = "xbox360"
    DS4 = "ds4"


@dataclass(slots=True)
class GamepadState:
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    lt: float = 0.0
    rt: float = 0.0
    buttons: list[int] = field(default_factory=lambda: [0] * 19)
    gyro_x: int = 0
    gyro_y: int = 0
    gyro_z: int = 0
    accel_x: int = 0
    accel_y: int = 0
    accel_z: int = 0
    has_imu: bool = False
    updated_at: float = 0.0

    @property
    def dpad_x(self) -> int:
        return self.buttons[18] - self.buttons[17]

    @property
    def dpad_y(self) -> int:
        return self.buttons[15] - self.buttons[16]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def axis_to_s16(value: float) -> int:
    value = clamp(value, -1.0, 1.0)
    return int(round(value * 32767.0))


def axis_to_u8(value: float, invert: bool = False) -> int:
    value = clamp(-value if invert else value, -1.0, 1.0)
    return int(round((value + 1.0) * 127.5))


def trigger_to_u8(value: float) -> int:
    return int(round(clamp(value, 0.0, 1.0) * 255.0))
