# RAW UNIFIED MULTISTREAM LOGGER
## R.U.M.-Logger

Simultaneous raw recorder for UDP/Ethernet packets (tshark), CAN FD bus data (Vector and Peak devices), and reference cameras. Each measurement is saved in a timestamped subfolder for later conversion and evaluation.

Uploads are sent to the URL in `RUM_BACKEND`. HTTPS uploads accept self-signed certificates; proxy settings are read from `HTTP_PROXY` / `HTTPS_PROXY` (Windows also falls back to the system proxy).

Live status JSON files and camera preview PNGs are written to `./uploads/`, which is intended to stay out of version control.

## Example

```powershell
python rumlogger_main.py `
  --video-device-startindex 1 `
  --video-device-count 3 `
  --log-path "D:\recordings" `
  --crop-factor 1.8 `
  --ignore-camera "HP " `
  --stream-log "http://172.16.250.248:4241/Display_FID.events,http://172.16.250.248:4241/Display_CID.events"
```

| Parameter | Description |
|---|---|
| `--video-device-startindex` | First camera device index to open (0-based). Pass `1` to skip the built-in laptop camera. |
| `--video-device-count` | Maximum number of cameras to start (1–5, default 5). |
| `--log-path` | Base recording directory. A timestamped subfolder is created inside for each measurement. |
| `--crop-factor` | Approximate center-crop zoom (≥ 1.0). Requests 720p capture for values below 2 and 1080p for 2 or above. |
| `--ignore-camera` | Skip cameras whose name contains this string (case-insensitive). Repeat to ignore multiple cameras. |
| `--stream-log` | Capture HTTP/HTTPS responses into separate files inside the measurement folder. Pass a comma-separated list of URLs. |

## Installation

This repository includes `requirements.txt` and `pyproject.toml`. Install with Python 3.11 or newer:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Start the application with:

```powershell
rum-logger
```




