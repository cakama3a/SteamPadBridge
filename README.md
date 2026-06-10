# SteamPadBridge

SteamPadBridge is a small Windows tray application for Steam Controller 2 (2026). It reads the controller directly over HID and exposes it to games as a virtual controller through ViGEmBus.

This project targets the second-generation Steam Controller from 2026, not the original 2015 Steam Controller.

It is meant for the simple case: start the app, pick Xbox 360 or DualShock 4 from the tray menu, and play without adding the game to Steam as a non-Steam game.

## Features

- Direct Steam Controller 2 (2026) HID input.
- Virtual Xbox 360 output for broad XInput compatibility.
- Virtual DualShock 4 output for PlayStation-style input and gyro/accelerometer support.
- Tray-only workflow with connection status.
- First-run ViGEmBus check with a bundled installer option.
- Portable PyInstaller `--onedir` build.
- Optional release signing with a code-signing certificate/YubiKey.

## Requirements

- Windows 10 or Windows 11.
- Steam Controller 2 (2026) connected over USB or receiver.
- ViGEmBus installed.
- For development/builds: Python 3.10+.

ViGEmBus is required because Windows applications cannot create a system-wide virtual gamepad without a driver. SteamPadBridge does not install a custom kernel driver; it uses the public ViGEmBus virtual controller layer.

## Supported Output Modes

### Xbox 360 Controller

Best for maximum compatibility. Games see a standard XInput controller with ABXY buttons.

### DualShock 4

Best when the game supports PlayStation controllers or gyro input. SteamPadBridge feeds DS4 reports through ViGEmClient and maps Steam Controller 2 (2026) IMU data into DS4 gyro/accelerometer fields.

ViGEmBus does not emulate DualSense. DualShock 4 is the PlayStation target supported by the public ViGEmBus driver.

## First Run

1. Run `SteamPadBridge.exe`.
2. If ViGEmBus is missing, SteamPadBridge offers to run `drivers\ViGEmBusSetup.exe`.
3. Finish the driver installer.
4. Start `SteamPadBridge.exe` again.
5. Use the tray menu to choose `Xbox 360 Controller` or `DualShock 4`.

The app briefly reconnects the virtual device when you switch modes.

## Tray Menu

- `Status` shows the current Steam Controller 2 (2026) and virtual output state.
- `Xbox 360 Controller` switches to XInput output.
- `DualShock 4` switches to DS4 output.
- `Install ViGEmBus` launches the bundled driver installer.
- `Reconnect` recreates the HID and virtual controller connection.
- `About` shows project and dependency credits.
- `Exit` closes the app and removes the virtual controller.

## Release Folder Layout

The intended release artifact is a zip of the PyInstaller output folder:

```text
SteamPadBridge_PyInstaller/
  SteamPadBridge.exe
  drivers/
    ViGEmBusSetup.exe
    README.md
  _internal/
    ...
```

Do not publish a one-file build. The folder build is more transparent and tends to look less suspicious to antivirus software than a self-extracting executable.

## Development

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

If your system does not provide the `py` launcher, use `python` instead.

## Build

For a signed release build:

```bat
build.bat
```

or:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

By default the build searches `Cert:\CurrentUser\My` for a code-signing certificate whose subject contains `Ivan Panchenko`. If the private key is on a YubiKey or another hardware token, Windows should show the PIN prompt during the signing step.

For an unsigned local test build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -SkipSign
```

To use another certificate subject:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -CertificateSubject "Your Publisher Name"
```

The build verifies the final Authenticode signature. If verification is not `Valid`, the build fails.

Before building, close any running `SteamPadBridge.exe`; Windows locks the output DLLs while the app is running.

## Driver Bundle

To download the ViGEmBus installer into `drivers\ViGEmBusSetup.exe`:

```powershell
powershell -ExecutionPolicy Bypass -File .\download_vigembus.ps1
```

ViGEmBus is retired/archived by Nefarius, but its last signed release remains the quickest practical path for a DS4/XInput virtual gamepad layer.

## Credits

- SteamPadBridge: vibe-coded by John Punch for Gamepadla.com.
- ViGEmBus / ViGEmClient: Nefarius Software Solutions e.U.
- Python packages: pystray, Pillow, hidapi, vgamepad, PyInstaller.

## Notes and Limitations

- DualSense emulation is not supported by ViGEmBus.
- DS4 gyro support depends on the installed ViGEmClient exposing extended DS4 reports.
- Some games only read gyro from real HID devices or through their own controller stack; compatibility can vary.
- The app currently targets one Steam Controller 2 (2026) at a time.

## License

Add the final project license here before publishing the repository. If you bundle third-party binaries, keep their original license notices intact.
