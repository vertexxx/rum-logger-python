import os
import csv
import subprocess
import tempfile
from functools import lru_cache

import cv2

POWERSHELL_COMMANDS = (
    "powershell.exe",
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
    "powershell",
)

CAMERA_METADATA_TIMEOUT_SECONDS = 20
HD_CAPTURE_RESOLUTION = (1280, 720)
FULL_HD_CAPTURE_RESOLUTION = (1920, 1080)


def get_camera_script_path():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "scripts", "get_camera_devices.ps1")


def format_resolution(width, height):
    if width > 0 and height > 0:
        return f"{width} x {height}"
    return "Unknown resolution"


def get_requested_video_resolution(crop_factor=None):
    if crop_factor is None:
        return None
    if crop_factor >= 2.0:
        return FULL_HD_CAPTURE_RESOLUTION
    return HD_CAPTURE_RESOLUTION


def request_capture_resolution(capture, requested_resolution):
    if requested_resolution is None:
        return

    requested_width, requested_height = requested_resolution
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)


def open_video_capture(device_number, requested_resolution=None):
    capture = cv2.VideoCapture(device_number)
    if capture.isOpened() or os.name != "nt":
        request_capture_resolution(capture, requested_resolution)
        return capture
    capture.release()
    capture = cv2.VideoCapture(device_number, cv2.CAP_DSHOW)
    request_capture_resolution(capture, requested_resolution)
    return capture


@lru_cache(maxsize=1)
def get_camera_devices():
    if os.name != "nt":
        return ()

    script_path = get_camera_script_path()
    if not os.path.exists(script_path):
        return ()

    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    temp_file_path = ""
    try:
        temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix=".csv")
        os.close(temp_file_descriptor)
        os.remove(temp_file_path)

        for powershell_command in POWERSHELL_COMMANDS:
            try:
                result = subprocess.run(
                    [
                        powershell_command,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        script_path,
                        "-OutputPath",
                        temp_file_path,
                    ],
                    timeout=CAMERA_METADATA_TIMEOUT_SECONDS,
                    check=False,
                    startupinfo=startupinfo,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                continue

            if result.returncode != 0 or not os.path.exists(temp_file_path) or os.path.getsize(temp_file_path) == 0:
                continue

            with open(temp_file_path, "r", encoding="utf-8-sig", newline="") as csv_file:
                devices = list(csv.DictReader(csv_file))

            if devices:
                break
        else:
            return ()
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass

    normalized_devices = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        device_name = (device.get("FriendlyName") or "").strip()
        if not device_name:
            continue
        normalized_devices.append(
            {
                "enumeration_index": int((device.get("EnumerationIndex") or "0").strip() or 0),
                "name": device_name,
                "display_name": (device.get("DisplayName") or device_name).strip() or device_name,
                "status": (device.get("Status") or "Unknown").strip() or "Unknown",
                "class": (device.get("Class") or "Unknown").strip() or "Unknown",
                "device_id": (device.get("DeviceId") or "").strip(),
                "occurrence": int((device.get("Occurrence") or "1").strip() or 1),
            }
        )

    return tuple(normalized_devices)


def probe_video_device(device_number, camera_device=None, requested_resolution=None):
    capture = open_video_capture(device_number, requested_resolution=requested_resolution)
    try:
        if not capture.isOpened():
            return None

        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        backend_name = "Unknown"
        if hasattr(capture, "getBackendName"):
            try:
                backend_name = capture.getBackendName()
            except cv2.error:
                backend_name = "Unknown"

        camera_name = f"Device {device_number}"
        display_name = camera_name
        camera_status = "Unknown"
        if camera_device:
            camera_name = camera_device.get("name") or camera_name
            display_name = camera_device.get("display_name") or camera_name
            camera_status = camera_device.get("status") or camera_status

        return {
            "device_number": device_number,
            "status_name": f"video{device_number}",
            "name": camera_name,
            "display_name": display_name,
            "status": camera_status,
            "backend": backend_name,
            "width": frame_width,
            "height": frame_height,
            "resolution": format_resolution(frame_width, frame_height),
        }
    finally:
        capture.release()