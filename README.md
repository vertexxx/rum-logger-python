# R.U.M.-Logger

Simultaneous raw recorder for UDP/Ethernet packets (tshark), CAN FD bus data (Vector and Peak devices), and reference cameras. Each measurement is saved in a timestamped subfolder for later conversion and evaluation.

Uploads are sent to the URL in `RUM_BACKEND`. HTTPS uploads accept self-signed certificates; proxy settings are read from `HTTP_PROXY` / `HTTPS_PROXY` (Windows also falls back to the system proxy).

Live status JSON files and camera preview PNGs are written to `./uploads/`, which is intended to stay out of version control.

## Installation

This repository now includes a `requirements.txt` and `pyproject.toml` so it can be installed as a normal editable Python project.

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install the project in editable mode from the repository root.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

If you only want the dependencies without installing the project metadata, use:

```powershell
python -m pip install -r requirements.txt
```

This also installs `PyInstaller`, so `compile.bat` can be used without a separate build-tool install step.

Start the application with either of these commands:

```powershell
rum-logger
python .\rumlogger_main.py
```

## External prerequisites

Some runtime dependencies are not Python packages and still need to be installed separately on Windows:

- Wireshark/tshark for Ethernet capture and for the `scripts/pcap2csv.py` converter.
- Vector hardware drivers for `python-can` with the Vector backend.
- PEAK PCAN drivers and the vendor DLL used by `PCANBasic.py`.
- Camera drivers required by OpenCV/Media Foundation for your devices.

## Full example

```
python rumlogger_main.py \
  --video-device-startindex 1 \
  --video-device-count 3 \
  --log-path "D:\recordings" \
  --crop-factor 1.8 \
  --ignore-camera "HP " \
  --ignore-camera "Anker"
```

| Parameter | Description |
|---|---|
| `--video-device-startindex` / positional | First camera device index to open (0-based). Pass `1` to skip the built-in laptop camera. |
| `--video-device-count` | Maximum number of cameras to start (1–5, default 5). |
| `--log-path` | Base recording directory. A timestamped subfolder is created inside for each measurement. Falls back to the default storage location if the path cannot be created. |
| `--crop-factor` | Approximate center-crop zoom (≥ 1.0). Requests 720p capture for values below 2 and 1080p for 2 or above; writes a pixel-exact centered cutout from each frame. |
| `--ignore-camera` | Skip cameras whose name contains this string (case-insensitive). Repeat to ignore multiple cameras. Ignored cameras appear as `Ignored` in the UI. |


Use `--stream-log` to capture one or more HTTP or HTTPS responses into separate files inside the measurement folder. Pass a comma-separated list or repeat the option, for example: `python rumlogger_main.py --stream-log "http://172.16.250.248:4241/Display_FID.events,http://172.16.250.248:4241/Display_CID.events"`. Each URL starts its own thread and writes the received bytes into a file named from the URL path such as `Display_FID.events` and `Display_CID.events`. Finite responses are written once and closed; long-lived streaming responses keep appending until the logger exits.

<img width="639" height="866" alt="image" src="https://github.com/user-attachments/assets/e5892c3a-e8a4-4333-b823-79935d79e129" />



