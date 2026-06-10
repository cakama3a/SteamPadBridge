from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import ctypes
from dataclasses import dataclass
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from . import __version__
from .state import OutputMode
from .steam_controller import SteamControllerDirect
from .vigem_bridge import ViGEmBridge


APP_NAME = "SteamPadBridge"
POLL_INTERVAL = 0.001
RECONNECT_INTERVAL = 1.0
MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONINFORMATION = 0x00000040
MB_ICONWARNING = 0x00000030
MB_ICONERROR = 0x00000010
MB_TOPMOST = 0x00040000
IDYES = 6

_about_lock = threading.Lock()
_about_open = False


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def config_path() -> Path:
    return app_dir() / "config.json"


def driver_installer_path() -> Path:
    primary = app_dir() / "drivers" / "ViGEmBusSetup.exe"
    if primary.exists():
        return primary
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "drivers" / "ViGEmBusSetup.exe"
        if bundled.exists():
            return bundled
    return primary


def is_vigembus_installed() -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["sc", "query", "ViGEmBus"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def show_message(title: str, text: str, error: bool = False):
    flags = MB_OK | MB_TOPMOST | (MB_ICONERROR if error else MB_ICONINFORMATION)
    ctypes.windll.user32.MessageBoxW(None, text, title, flags)


def ask_yes_no(title: str, text: str) -> bool:
    flags = MB_YESNO | MB_ICONWARNING | MB_TOPMOST
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags) == IDYES


def show_about_once():
    global _about_open
    with _about_lock:
        if _about_open:
            return
        _about_open = True
    try:
        text = (
            f"{APP_NAME} {__version__}\n"
            "Steam Controller -> virtual Xbox 360 / DualShock 4 bridge\n\n"
            "Vibe-coded by John Punch for Gamepadla.com.\n\n"
            "Uses ViGEmBus and ViGEmClient by Nefarius Software Solutions e.U.\n"
            "Uses pystray, Pillow, hidapi, vgamepad, and PyInstaller.\n\n"
            "ViGEmBus is required for the virtual controller device."
        )
        show_message(f"About {APP_NAME}", text)
    finally:
        with _about_lock:
            _about_open = False


def run_driver_installer():
    installer = driver_installer_path()
    if not installer.exists():
        show_message(
            APP_NAME,
            f"ViGEmBus is not installed, and the bundled installer was not found:\n\n{installer}\n\nRun download_vigembus.ps1 or place ViGEmBusSetup.exe there.",
            error=True,
        )
        return
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath '{installer}' -Verb RunAs"])
    except Exception as exc:
        show_message(APP_NAME, f"Failed to start ViGEmBus installer:\n\n{exc}", error=True)


@dataclass
class RuntimeStatus:
    driver_ok: bool = False
    steam_ok: bool = False
    virtual_ok: bool = False
    mode: OutputMode = OutputMode.XBOX360
    text: str = "Starting"
    ds4_imu: bool = False


class SteamPadBridgeApp:
    def __init__(self):
        self.base_dir = app_dir()
        self.status = RuntimeStatus(mode=self._load_mode())
        self._icons = {color: self._make_icon(color) for color in ("green", "yellow", "red", "gray")}
        self.icon = pystray.Icon(APP_NAME, self._icons["gray"], APP_NAME)
        self.stop_event = threading.Event()
        self.controller = None
        self.bridge = None
        self.lock = threading.Lock()
        self._last_driver_check = 0.0
        self._last_status_text = ""
        self._last_status_color = "gray"

    def run(self):
        self._ensure_driver_first_run()
        self.icon.menu = self._build_menu()
        worker = threading.Thread(target=self._worker_loop, daemon=True)
        worker.start()
        self.icon.run()
        self.stop_event.set()
        self._close_runtime()

    def _ensure_driver_first_run(self):
        if is_vigembus_installed():
            return
        if ask_yes_no(
            APP_NAME,
            "ViGEmBus is required to create a virtual Xbox 360 or DualShock 4 controller.\n\nInstall the bundled ViGEmBus driver now?",
        ):
            run_driver_installer()
            show_message(APP_NAME, "Finish the ViGEmBus installer, then start SteamPadBridge again.")
            sys.exit(0)

    def _worker_loop(self):
        last_reconnect = 0.0
        while not self.stop_event.is_set():
            now = time.perf_counter()
            try:
                if now - self._last_driver_check >= 2.0:
                    self.status.driver_ok = is_vigembus_installed()
                    self._last_driver_check = now
                if not self.status.driver_ok:
                    self._set_status("ViGEmBus not installed", "red")
                    time.sleep(1.0)
                    continue

                if self.bridge is None:
                    self._connect_bridge()

                if self.controller is None and now - last_reconnect >= RECONNECT_INTERVAL:
                    last_reconnect = now
                    self._connect_controller()

                if self.controller and self.bridge:
                    changed = self.controller.update()
                    self.status.steam_ok = self.controller.device is not None
                    if changed:
                        self.bridge.update(self.controller.state)
                    label = self.controller.label if self.controller else "Steam Controller"
                    imu = " + IMU" if self.status.ds4_imu else ""
                    self._set_status(f"{label} -> {self.status.mode.value}{imu}", "green")
                else:
                    self.status.steam_ok = False
                    self._set_status("Waiting for Steam Controller", "yellow")
            except Exception as exc:
                self._set_status(str(exc), "red")
                self._close_runtime(keep_controller=False)
                time.sleep(1.0)
            time.sleep(POLL_INTERVAL)

    def _connect_controller(self):
        try:
            self.controller = SteamControllerDirect.open_first()
        except Exception:
            self.controller = None
        self.status.steam_ok = self.controller is not None

    def _connect_bridge(self):
        self.bridge = ViGEmBridge(self.status.mode)
        self.bridge.connect()
        self.status.virtual_ok = True
        self.status.ds4_imu = self.bridge.supports_ds4_imu

    def _close_runtime(self, keep_controller: bool = True):
        if self.bridge:
            self.bridge.close()
            self.bridge = None
        self.status.virtual_ok = False
        self.status.ds4_imu = False
        if not keep_controller and self.controller:
            self.controller.close()
            self.controller = None

    def _set_mode(self, mode: OutputMode):
        if self.status.mode == mode:
            return
        with self.lock:
            self.status.mode = mode
            self._save_mode(mode)
            self._close_runtime()
            self.icon.menu = self._build_menu()
            self.icon.update_menu()

    def _set_status(self, text: str, color: str):
        if text == self._last_status_text and color == self._last_status_color:
            return
        self._last_status_text = text
        self._last_status_color = color
        self.status.text = text
        self.icon.title = f"{APP_NAME}: {text}"
        self.icon.icon = self._icons.get(color, self._icons["gray"])

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda item: f"Status: {self.status.text}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Xbox 360 Controller",
                lambda icon, item: self._set_mode(OutputMode.XBOX360),
                checked=lambda item: self.status.mode == OutputMode.XBOX360,
                radio=True,
            ),
            pystray.MenuItem(
                "DualShock 4",
                lambda icon, item: self._set_mode(OutputMode.DS4),
                checked=lambda item: self.status.mode == OutputMode.DS4,
                radio=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Install ViGEmBus", lambda icon, item: run_driver_installer()),
            pystray.MenuItem("Reconnect", lambda icon, item: self._force_reconnect()),
            pystray.MenuItem("About", lambda icon, item: show_about_once()),
            pystray.MenuItem("Exit", lambda icon, item: self._quit()),
        )

    def _force_reconnect(self):
        with self.lock:
            if self.controller:
                self.controller.close()
            self.controller = None
            self._close_runtime(keep_controller=False)

    def _quit(self):
        self.stop_event.set()
        self.icon.stop()

    def _load_mode(self) -> OutputMode:
        try:
            with config_path().open("r", encoding="utf-8") as f:
                value = json.load(f).get("mode", OutputMode.XBOX360.value)
            return OutputMode(value)
        except Exception:
            return OutputMode.XBOX360

    def _save_mode(self, mode: OutputMode):
        try:
            with config_path().open("w", encoding="utf-8") as f:
                json.dump({"mode": mode.value}, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def _make_icon(color: str) -> Image.Image:
        palette = {
            "green": (40, 190, 80),
            "yellow": (240, 190, 50),
            "red": (220, 70, 70),
            "gray": (120, 125, 130),
        }
        fill = palette.get(color, palette["gray"])
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((8, 14, 56, 50), radius=12, fill=(35, 38, 42), outline=(230, 230, 230), width=2)
        draw.ellipse((42, 6, 62, 26), fill=fill, outline=(20, 20, 20), width=2)
        draw.ellipse((18, 26, 28, 36), fill=(230, 230, 230))
        draw.ellipse((36, 26, 46, 36), fill=(230, 230, 230))
        draw.rectangle((29, 30, 35, 32), fill=(230, 230, 230))
        return img


def main():
    SteamPadBridgeApp().run()


if __name__ == "__main__":
    main()
