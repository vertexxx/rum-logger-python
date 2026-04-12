import os
import datetime
import threading
import argparse
import shutil
import cv2
import customtkinter as ctk
from tkinter import PhotoImage
import webbrowser
from PIL import Image
from PIL import ImageTk
import json
from customtkinter import CTkImage
import ctypes
import sys
import ctypes

from capture_peak_canfd import capture_peak_canfd
from capture_vector_canfd import capture_vector_canfd
from capture_stream import StreamCaptureThread, build_stream_capture_configs, is_supported_stream_url
#from capture_udp import capture_upd
from capture_tshark import TsharkCaptureThread
from capture_video import VideoCaptureThread  # Import the VideoCaptureThread class
#from capture_video2 import capture_video2
from FileUploadThread import FileUploadThread
from upload_paths import ensure_uploads_dir
from video_device_utils import format_resolution, get_camera_devices, get_requested_video_resolution, probe_video_device


log_file_path = ""
temp_log = ""
data_folder = ""
requested_log_directory = None

user_name="unknown"
device_name="unknown"
user_privileges=False
video_device_start = 0
video_device_count = 5
video_crop_factor = None
stream_log_urls = ()
stream_capture_configs = ()
ignored_camera_patterns = ()
discovered_video_devices = ()
video_devices = ()
video_threads = []
stream_capture_threads = []

MAX_VIDEO_DEVICES = 5
DEFAULT_VIDEO_DEVICE_COUNT = MAX_VIDEO_DEVICES
VIDEO_PROBE_RANGE = 12

# Assuming these threads are defined somewhere in your code
vector_canfd_thread = threading.Thread()
peak_canfd_thread = threading.Thread()
udp_thread = threading.Thread()
tshark_thread = None  # Initialize as None
upload_thread = None
shutdown_event = threading.Event()
shutdown_lock = threading.Lock()
shutdown_in_progress = False
gui_update_job = None
root = None
selected_drive_label = None
labels = {}
NON_VIDEO_STATUS_DICT = {
    #"udp": {"text": "Not started", "color": "gray"},
    "tshark": {"text": "Not started", "color": "gray"},
    "vector_canfd": {"text": "Not started", "color": "gray"},
    "peak_canfd": {"text": "Not started", "color": "gray"},
    "uploads": {"text": "Not started", "color": "gray"},
}
status_dict = {}
selected_drive_text = "Selected Location: None"

def parse_startup_options(argv):
    parser = argparse.ArgumentParser(
        description="Configure video device discovery.",
    )
    parser.add_argument(
        "--log-path",
        dest="log_path",
        default=None,
        help="Base recording directory to use. If missing, the folder is created and a timestamped measurement subfolder is added. If unavailable, the default storage location is used.",
    )
    parser.add_argument(
        "video_device_startindex",
        nargs="?",
        type=int,
        default=None,
        help="First video device index to use. Pass 1 to skip device 0.",
    )
    parser.add_argument(
        "--video-device-startindex",
        dest="video_device_startindex_option",
        type=int,
        default=None,
        help="First video device index to use. Pass 1 to skip device 0.",
    )
    parser.add_argument(
        "--video-device-count",
        "--max-video-devices",
        dest="video_device_count",
        type=int,
        default=DEFAULT_VIDEO_DEVICE_COUNT,
        help=f"Max number of video devices and threads to start (1-{MAX_VIDEO_DEVICES}).",
    )
    parser.add_argument(
        "-ignore-camera",
        "--ignore-camera",
        dest="ignore_cameras",
        action="append",
        default=[],
        help="Ignore cameras whose name contains this text. Repeat to ignore multiple cameras.",
    )
    parser.add_argument(
        "--crop-factor",
        dest="crop_factor",
        type=float,
        default=None,
        help="Approximate zoom factor for center-cropping video. Uses 720p capture for factors below 2 and 1080p capture for factors of 2 or more.",
    )
    parser.add_argument(
        "--stream-log",
        dest="stream_log_urls",
        action="append",
        default=[],
        help="Comma-separated HTTP or HTTPS URLs to log into per-stream files. Repeat the option to add more streams.",
    )
    args, _ = parser.parse_known_args(argv)

    if (
        args.video_device_startindex is not None
        and args.video_device_startindex_option is not None
        and args.video_device_startindex != args.video_device_startindex_option
    ):
        parser.error(
            "specify video-device-startindex either positionally or with --video-device-startindex, not both"
        )

    start_value = args.video_device_startindex_option
    if start_value is None:
        start_value = args.video_device_startindex if args.video_device_startindex is not None else 0

    if start_value < 0:
        parser.error("video-device-startindex must be greater than or equal to 0")

    if args.video_device_count < 1 or args.video_device_count > MAX_VIDEO_DEVICES:
        parser.error(f"video-device-count must be between 1 and {MAX_VIDEO_DEVICES}")

    if args.crop_factor is not None and args.crop_factor < 1.0:
        parser.error("crop-factor must be greater than or equal to 1.0")

    normalized_ignored_cameras = tuple(
        pattern.strip().lower()
        for pattern in args.ignore_cameras
        if pattern and pattern.strip()
    )

    normalized_log_directory = None
    if args.log_path and args.log_path.strip():
        normalized_log_directory = os.path.abspath(os.path.normpath(args.log_path.strip()))

    normalized_stream_log_urls = []
    for stream_log_value in args.stream_log_urls:
        for raw_url in stream_log_value.split(","):
            normalized_url = raw_url.strip()
            if not normalized_url:
                continue
            if not is_supported_stream_url(normalized_url):
                parser.error(f"stream-log only supports HTTP or HTTPS URLs: {normalized_url}")
            normalized_stream_log_urls.append(normalized_url)

    return (
        start_value,
        args.video_device_count,
        normalized_ignored_cameras,
        normalized_log_directory,
        args.crop_factor,
        tuple(normalized_stream_log_urls),
    )

def is_ignored_camera(camera_name, ignore_patterns):
    camera_name_lower = camera_name.lower()
    return any(ignore_pattern in camera_name_lower for ignore_pattern in ignore_patterns)

def get_active_video_devices():
    return tuple(
        video_device
        for video_device in discovered_video_devices
        if not video_device.get("ignored", False)
    )

def detect_video_devices(
    start_index,
    max_devices=DEFAULT_VIDEO_DEVICE_COUNT,
    probe_range=VIDEO_PROBE_RANGE,
    ignore_patterns=(),
    crop_factor=None,
):
    detected_devices = []
    camera_devices = list(get_camera_devices())
    effective_probe_range = max(probe_range, max_devices * 3)
    msmf_camera_index = 0
    active_device_count = 0
    requested_resolution = get_requested_video_resolution(crop_factor)

    for device_number in range(start_index, start_index + effective_probe_range):
        if camera_devices and msmf_camera_index >= len(camera_devices):
            break

        device_info = probe_video_device(device_number, requested_resolution=requested_resolution)
        if not device_info:
            continue

        if camera_devices:
            if device_info.get("backend") != "MSMF":
                continue

            if msmf_camera_index >= len(camera_devices):
                continue

            camera_device = camera_devices[msmf_camera_index]
            msmf_camera_index += 1

            if camera_device.get("status", "Unknown").upper() != "OK":
                continue

            device_info["name"] = camera_device.get("name", device_info["name"])
            device_info["display_name"] = camera_device.get("display_name", device_info["display_name"])
            device_info["status"] = camera_device.get("status", device_info["status"])
            device_info["ignored"] = is_ignored_camera(camera_device.get("name", ""), ignore_patterns)
        else:
            device_info["ignored"] = is_ignored_camera(device_info.get("name", ""), ignore_patterns)

        detected_devices.append(device_info)
        if not device_info.get("ignored", False):
            active_device_count += 1

        if active_device_count >= max_devices:
            break

    return tuple(detected_devices)

def build_status_dict():
    video_status = {
        video_device["status_name"]: {
            "text": "Ignored" if video_device.get("ignored", False) else "Not started",
            "color": "gray",
        }
        for video_device in discovered_video_devices
    }
    stream_status = {
        stream_config["status_name"]: {
            "text": "Not started",
            "color": "gray",
        }
        for stream_config in stream_capture_configs
    }
    return {
        **video_status,
        **stream_status,
        **NON_VIDEO_STATUS_DICT,
    }

def get_video_device(thread_name):
    for video_device in discovered_video_devices:
        if video_device["status_name"] == thread_name:
            return video_device
    return None

def get_stream_capture_config(thread_name):
    for stream_config in stream_capture_configs:
        if stream_config["status_name"] == thread_name:
            return stream_config
    return None

def get_status_label_text(thread_name):
    video_device = get_video_device(thread_name)
    if video_device:
        return f"Video {video_device['device_number']}: {video_device['display_name']}"
    stream_config = get_stream_capture_config(thread_name)
    if stream_config:
        return f"Stream: {stream_config['display_name']}"
    return thread_name.capitalize()

def log_detected_video_devices():
    if not discovered_video_devices:
        attach_to_log(f"No video devices detected from index {video_device_start}")
        return

    for video_device in discovered_video_devices:
        device_state = "Ignored" if video_device.get("ignored", False) else video_device["status"]
        attach_to_log(
            f"Detected video device {video_device['device_number']}: {video_device['display_name']} [{device_state}] ({video_device['resolution']})"
        )

def attach_to_log(message):
    global temp_log
    global log_file_path
    message = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n"
    print(message, end="")    
    if not log_file_path or log_file_path == "":
        temp_log += message
    else:
        if temp_log != "":
            with open(log_file_path, "a") as log_file:
                log_file.write(temp_log)
            temp_log = ""
        with open(log_file_path, "a") as log_file:
            log_file.write(message)

def create_folder(folder_path):
    if os.path.isdir(folder_path):
        return True

    if os.path.exists(folder_path):
        attach_to_log(f"Path exists but is not a folder: {folder_path}")
        return False

    try:
        os.makedirs(folder_path)
        attach_to_log(f"Folder created: {folder_path}")
        return True
    except Exception as e:
        attach_to_log(f"Failed to create folder {folder_path}: {e}")
        return False

def activate_log_folder(log_folder):
    attach_to_log(f"Target folder found: {log_folder}")
    if not create_folder(log_folder):
        return False

    global data_folder
    data_folder = log_folder

    global log_file_path
    log_file_path = os.path.join(log_folder, "log.txt")

    try:
        with open(log_file_path, "a", encoding="utf-8"):
            pass
        attach_to_log("Log file created successfully")
        return True
    except Exception as e:
        log_file_path = ""
        attach_to_log(f"Log file creation failed: {e}")
        return False

def initialize_log_folder_in_base(base_folder):
    if not create_folder(base_folder):
        return False

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_folder = os.path.join(base_folder, timestamp)
    return activate_log_folder(log_folder)

def get_available_storage_devices():
    storage_info = []

    try:
        wmic_output = os.popen("wmic logicaldisk get size, caption, freespace").read().splitlines()[1:]
        parsed_wmic_output = [drive.split() for drive in wmic_output if drive.strip() != ""]
        for drive in parsed_wmic_output:
            if len(drive) >= 3:
                storage_info.append([drive[0], drive[1], drive[2]])
    except Exception as e:
        attach_to_log(f"WMIC storage lookup failed: {e}")

    if storage_info:
        return storage_info

    attach_to_log("Falling back to Python-based storage detection")
    for drive_number in range(ord("A"), ord("Z") + 1):
        drive_caption = f"{chr(drive_number)}:"
        drive_root = f"{drive_caption}\\"
        if not os.path.exists(drive_root):
            continue
        try:
            usage = shutil.disk_usage(drive_root)
            storage_info.append([drive_caption, str(usage.free), str(usage.total)])
        except Exception as e:
            attach_to_log(f"Skipping drive {drive_caption}: {e}")

    return storage_info

def find_best_storage_device():
    storage_info = get_available_storage_devices()
    attach_to_log("Searching for best data storage device")
    #if devicename starts with "IT" ignore known network drives
    global device_name
    largest_storage=None
    try:
        if device_name.startswith("IT"):
            ignored_drives = {"G:", "T:", "W:", "X:", "Y:", "Z:"} #Prevent logging to network drives
        else:
            ignored_drives = {}
        storage_info = [drive for drive in storage_info if drive[0] not in ignored_drives]
        for drive in storage_info:
            drive_caption = drive[0]
            drive_size = int(drive[2])
            drive_freespace = int(drive[1])
            attach_to_log(f"{drive_caption}, {drive_size / (1024 * 1024 * 1024):.2f} GB, {drive_freespace / (1024 * 1024 * 1024):.2f} GB free")
        largest_storage = max([drive for drive in storage_info if int(drive[1]) > 5 * 1024 * 1024 * 1024], key=lambda x: int(x[2]), default=None)
    except Exception as e:
        attach_to_log(f"Error finding best storage device: {e}")
    if not largest_storage:
        largest_storage = next((drive for drive in storage_info if drive[0] == "C:"), None)
    attach_to_log(f"Best storage device: {largest_storage}")
    return largest_storage

def initialize_log_folder(largest_storage):
    drive_root = f"{largest_storage[0]}{os.sep}"
    beer_logger_folder = os.path.join(drive_root, "RUM_LOGGER_DATA")
    return initialize_log_folder_in_base(beer_logger_folder)

def initialize_custom_log_folder(base_folder):
    attach_to_log(f"Custom log base directory requested: {base_folder}")
    return initialize_log_folder_in_base(base_folder)

def update_status(thread_name, text, color):
    if thread_name not in status_dict:
        status_dict[thread_name] = {"text": text, "color": color}
    else:
        status_dict[thread_name]["text"] = text
        status_dict[thread_name]["color"] = color
    attach_to_log(f"Statusupdate: {thread_name} ({color})): {text}")
    update_statusjson()

def update_statusjson():
    uploads_dir = ensure_uploads_dir()
    jsonfile = os.path.join(uploads_dir, f"{device_name}.json")
    try:
        with open(jsonfile, "w") as f:
            json.dump(status_dict, f)
    except Exception as e:
        attach_to_log(f"Error updating status json: {e}")   


def capture_video_wrapper():
    global video_threads
    video_threads = []
    active_video_devices = get_active_video_devices()
    uploads_dir = ensure_uploads_dir()

    for video_device in active_video_devices:
        video_thread = VideoCaptureThread(
            data_folder,
            update_status,
            device_number=video_device["device_number"],
            computername=device_name,
            status_name=video_device["status_name"],
            crop_factor=video_crop_factor,
            preview_folder=uploads_dir,
        )
        video_thread.daemon = True
        video_threads.append(video_thread)

    for video_thread in video_threads:
        video_thread.start()

    if active_video_devices:
        device_labels = [
            f"{video_device['device_number']}={video_device['display_name']} ({video_device['resolution']})"
            for video_device in active_video_devices
        ]
        attach_to_log(f"Video threads started for devices: {', '.join(device_labels)}")
    else:
        attach_to_log("No active video devices detected; no video threads started")

def capture_video_wrapper2():
    ...
    #capture_video2(data_folder, update_status)

#def capture_udp_wrapper():
#    capture_upd(data_folder, update_status)

def start_stream_capture_threads():
    global stream_capture_threads

    stream_capture_threads = []
    for stream_config in stream_capture_configs:
        stream_thread = StreamCaptureThread(
            data_folder,
            stream_config,
            update_status,
            stop_event=shutdown_event,
        )
        stream_thread.daemon = True
        stream_capture_threads.append(stream_thread)

    for stream_thread in stream_capture_threads:
        stream_thread.start()

    if stream_capture_threads:
        stream_targets = ", ".join(
            f"{stream_config['url']} -> {stream_config['filename']}"
            for stream_config in stream_capture_configs
        )
        attach_to_log(f"Stream threads started: {stream_targets}")

def capture_vector_canfd_wrapper():
    capture_vector_canfd(data_folder, update_status, stop_event=shutdown_event)
    attach_to_log("Vector CAN FD thread started")

def upload_wrapper():
    global upload_thread
    try:
        upload_thread = FileUploadThread(device_name, update_status, directory=ensure_uploads_dir())
        upload_thread.daemon = True
        upload_thread.start()
        attach_to_log("Upload thread started")
    except Exception as e:
        upload_thread = None
        attach_to_log(f"Error starting upload thread: {e}")


def capture_peak_canfd_wrapper():
    capture_peak_canfd(data_folder, update_status, stop_event=shutdown_event)
    attach_to_log("Peak CAN FD thread started")

def start_and_join_threads():
    global tshark_thread, vector_canfd_thread, peak_canfd_thread

    if shutdown_event.is_set():
        attach_to_log("Shutdown requested before worker threads were started")
        return

    capture_video_wrapper()
    attach_to_log("All video threads created")
    upload_wrapper()
    attach_to_log("Upload thread created")
    start_stream_capture_threads()
    if stream_capture_threads:
        attach_to_log("Stream capture threads created")
    #video2_thread = threading.Thread(target=capture_video_wrapper2)
    #udp_thread = threading.Thread(target=capture_udp_wrapper)
    tshark_thread = TsharkCaptureThread(data_folder, update_status)  # Use TsharkCaptureThread
    tshark_thread.daemon = True
    attach_to_log("Tshark thread created")
    vector_canfd_thread = threading.Thread(target=capture_vector_canfd_wrapper, daemon=True)
    attach_to_log("Vector CAN FD thread created")
    peak_canfd_thread = threading.Thread(target=capture_peak_canfd_wrapper, daemon=True)
    attach_to_log("Peak CAN FD thread created")

    attach_to_log("All threads created")

    #video2_thread.start()
    vector_canfd_thread.start()
    peak_canfd_thread.start()
    #udp_thread.start()
    tshark_thread.start()
    attach_to_log("All threads started")

def join_thread(thread, thread_name, timeout=5):
    if thread is None or not thread.is_alive():
        return

    thread.join(timeout=timeout)
    if thread.is_alive():
        attach_to_log(f"{thread_name} thread did not stop within {timeout} seconds")
    else:
        attach_to_log(f"{thread_name} thread stopped")

def terminate_thread(thread):
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("Invalid thread ID")
    elif res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

def stop_all_threads():
    shutdown_event.set()

    if upload_thread and upload_thread.is_alive():
        upload_thread.stop()
    #if udp_thread.is_alive():
    #    udp_thread._stop()
    if tshark_thread and tshark_thread.is_alive():
        tshark_thread.stop()  # Use the stop method of TsharkCaptureThread
    for video_thread in video_threads:
        if video_thread.is_alive():
            video_thread.stop()
    for stream_thread in stream_capture_threads:
        if stream_thread.is_alive():
            stream_thread.stop()

    join_thread(upload_thread, "Upload", timeout=5)
    join_thread(tshark_thread, "Tshark", timeout=5)
    for video_thread in video_threads:
        join_thread(video_thread, f"{video_thread.status_name}", timeout=10)
    for stream_thread in stream_capture_threads:
        join_thread(stream_thread, stream_thread.filename, timeout=5)
    join_thread(vector_canfd_thread, "Vector CAN FD", timeout=5)
    join_thread(peak_canfd_thread, "Peak CAN FD", timeout=5)

def update_gui():
    global gui_update_job

    if shutdown_in_progress:
        return

    for thread_name, status in status_dict.items():
        if thread_name in labels:
            labels[thread_name].configure(text=status["text"], text_color=status["color"])
    selected_drive_label.configure(text=selected_drive_text)
    root.update_idletasks()
    #attach_to_log("GUI updated")
    gui_update_job = root.after(2000, update_gui)  # Update every 2 seconds

def open_folder():
    if data_folder:
        webbrowser.open(f"file:///{data_folder}")

def exit_program():
    global shutdown_in_progress, gui_update_job

    with shutdown_lock:
        if shutdown_in_progress:
            return
        shutdown_in_progress = True

    attach_to_log("Exiting program...")
    if gui_update_job is not None:
        try:
            root.after_cancel(gui_update_job)
        except Exception:
            pass
        gui_update_job = None
    stop_all_threads()
    try:
        root.quit()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass

def log_ethernet_adapters():
    """Log all ethernet adapters with their configured IP addresses and subnet masks."""
    try:
        import subprocess
        result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            attach_to_log("Failed to retrieve network adapter information via ipconfig")
            return
        
        lines = result.stdout.split('\n')
        current_adapter = None
        adapter_info = {}
        
        for line in lines:
            line = line.strip()
            
            # Detect adapter name (lines ending with ':' that contain adapter info)
            if line and line.endswith(':') and not line.startswith('IPv') and not line.startswith('Physical'):
                current_adapter = line[:-1]  # Remove the trailing ':'
                if current_adapter not in adapter_info:
                    adapter_info[current_adapter] = {'ips': [], 'subnets': []}
            
            # Extract IPv4 addresses (lines starting with "IPv4 Address")
            if current_adapter and line.startswith('IPv4 Address'):
                parts = line.split(':')
                if len(parts) > 1:
                    ip = parts[1].strip().split('(')[0].strip()  # Handle format with gateway info
                    if ip:
                        adapter_info[current_adapter]['ips'].append(ip)
            
            # Extract Subnet Masks (lines starting with "Subnet Mask")
            if current_adapter and line.startswith('Subnet Mask'):
                parts = line.split(':')
                if len(parts) > 1:
                    subnet = parts[1].strip()
                    if subnet:
                        adapter_info[current_adapter]['subnets'].append(subnet)
        
        # Log the adapter information
        if adapter_info:
            attach_to_log("Ethernet Adapters Configuration:")
            for adapter_name, info in adapter_info.items():
                if info['ips'] or info['subnets']:
                    for i, ip in enumerate(info['ips']):
                        subnet = info['subnets'][i] if i < len(info['subnets']) else "N/A"
                        attach_to_log(f"  {adapter_name}: IP={ip}, Subnet={subnet}")
        else:
            attach_to_log("No ethernet adapter information found")
    
    except subprocess.TimeoutExpired:
        attach_to_log("Timeout retrieving network adapter information")
    except Exception as e:
        attach_to_log(f"Error retrieving network adapter information: {e}")

def main():
    attach_to_log("######################################################")
    attach_to_log("# Welcome to the                                     #")
    attach_to_log("#         Raw Unified Multistream - Logger           #")
    attach_to_log("######################################################")
    attach_to_log("#                R.U.M. - Logger                     #")
    attach_to_log("######################################################")
    
    try:
        global user_name
        user_name = os.getlogin()
        attach_to_log(f"Username: {user_name}")
    except Exception as e:
        attach_to_log(f"Error retrieving username: {e}")

    try:
        try:
            global user_privileges
            user_privileges = ctypes.windll.shell32.IsUserAnAdmin() != 0
            privileges = "Admin" if user_privileges else "User"
        except Exception as e:
            privileges = f"Error checking privileges: {e}"
        attach_to_log(f"Privileges: {privileges}")
    except Exception as e:
        is_admin = False
        attach_to_log(f"Error retrieving privileges: {e}")

    try:
        global device_name
        device_name = os.getenv('COMPUTERNAME') or "unknown"
        attach_to_log(f"Device Name: {device_name}")
    except Exception as e:
        attach_to_log(f"Error retrieving device name: {e}")

    log_ethernet_adapters()

    attach_to_log(f"Video device start index: {video_device_start}")
    attach_to_log(f"Video device count limit: {video_device_count}")
    if video_crop_factor is not None:
        attach_to_log(f"Video crop factor: {video_crop_factor}")
        requested_resolution = get_requested_video_resolution(video_crop_factor)
        if requested_resolution is not None:
            attach_to_log(f"Requested video capture resolution: {format_resolution(*requested_resolution)}")
    if requested_log_directory:
        attach_to_log(f"Requested log directory: {requested_log_directory}")
    if stream_capture_configs:
        configured_streams = ", ".join(
            f"{stream_config['url']} -> {stream_config['filename']}"
            for stream_config in stream_capture_configs
        )
        attach_to_log(f"Configured stream logging: {configured_streams}")
    if ignored_camera_patterns:
        attach_to_log(f"Ignoring camera name matches: {list(ignored_camera_patterns)}")
    log_detected_video_devices()

    try:
        if shutdown_event.is_set():
            return

        global selected_drive_text
        if requested_log_directory:
            if initialize_custom_log_folder(requested_log_directory):
                selected_drive_text = f"Selected Location: {requested_log_directory}"
                if not shutdown_event.is_set():
                    start_and_join_threads()
                return

            attach_to_log("Falling back to automatically selected storage device")

        largest_storage = find_best_storage_device()
        if largest_storage and initialize_log_folder(largest_storage):
            selected_drive_text = f"Selected Location: {largest_storage[0]}"
            if not shutdown_event.is_set():
                start_and_join_threads()
        elif largest_storage:
            attach_to_log(f"Unable to initialize default log folder on {largest_storage[0]}")
        else:
            attach_to_log("No suitable storage device found.")
    except Exception as e:
        attach_to_log(f"Fatal startup error: {e}")

def run():
    global video_device_start
    global video_device_count
    global ignored_camera_patterns
    global requested_log_directory
    global video_crop_factor
    global stream_log_urls
    global stream_capture_configs
    global discovered_video_devices
    global video_devices
    global status_dict
    global log_file_path
    global temp_log
    global gui_update_job
    global root
    global selected_drive_label
    global labels

    (
        video_device_start,
        video_device_count,
        ignored_camera_patterns,
        requested_log_directory,
        video_crop_factor,
        stream_log_urls,
    ) = parse_startup_options(sys.argv[1:])
    stream_capture_configs = build_stream_capture_configs(stream_log_urls)
    discovered_video_devices = detect_video_devices(
        video_device_start,
        max_devices=video_device_count,
        ignore_patterns=ignored_camera_patterns,
        crop_factor=video_crop_factor,
    )
    video_devices = get_active_video_devices()
    status_dict = build_status_dict()
    log_file_path = ""
    temp_log = ""
    linecharwidth=42

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    root = ctk.CTk()
    root.title("R.U.M. Logger")
    root.geometry("640x840")
    root.minsize(620, 800)
    root.attributes('-alpha',1)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)
    root.protocol("WM_DELETE_WINDOW", exit_program)


    image_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "res")
    root.iconbitmap(os.path.join(image_path, "favicon.ico"))

    title_image = ctk.CTkImage(Image.open(os.path.join(image_path, "titleimage.png")), size=(300,264)) #, size=(500, 150))
    title_label = ctk.CTkLabel(root, image=title_image, text="")
    title_label.grid(row=0, column=0, columnspan=2, padx=16, pady=(8, 4))

    small_text = ctk.CTkLabel(root, text="Raw Unified Multistream Logger", text_color="white", font=("Courier New", 18))
    small_text.grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 4))

    line_before_status = ctk.CTkLabel(root, text="─" * linecharwidth, text_color="gray")
    line_before_status.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="ew")

    labels = {}
    for i, thread_name in enumerate(status_dict.keys()):
        label = ctk.CTkLabel(root, text=status_dict[thread_name]["text"], text_color=status_dict[thread_name]["color"])
        label.grid(row=i+3, column=1, padx=(8, 16), pady=3, sticky="w")
        labels[thread_name] = label
        ctk.CTkLabel(root, text=get_status_label_text(thread_name), anchor="w", justify="left", wraplength=320).grid(row=i+3, column=0, padx=(16, 8), pady=3, sticky="ew")

    line_after_status = ctk.CTkLabel(root, text="─" * linecharwidth, text_color="gray")
    line_after_status.grid(row=len(status_dict) + 3, column=0, columnspan=2, padx=16, pady=(6, 8), sticky="ew")

    open_folder_button = ctk.CTkButton(root, text="Open Log Folder", command=open_folder)
    open_folder_button.grid(row=len(status_dict) + 4, column=0, padx=(16, 8), pady=6, sticky="ew")

    selected_drive_label = ctk.CTkLabel(root, text="Selected Location: None", text_color="white")
    selected_drive_label.grid(row=len(status_dict) + 4, column=1, padx=(8, 16), pady=6, sticky="w")

    line_before_version = ctk.CTkLabel(root, text="─" * linecharwidth, text_color="gray")
    line_before_version.grid(row=len(status_dict) + 5, column=0, columnspan=2, padx=16, pady=(4, 6), sticky="ew")

    exit_button = ctk.CTkButton(root, text="Exit", command=exit_program)
    exit_button.grid(row=len(status_dict) + 6, column=0, columnspan=2, padx=16, pady=6, sticky="ew")

    version_label = ctk.CTkLabel(root, text="Version 0.3.2", text_color="white")
    version_label.grid(row=len(status_dict) + 7, column=0, columnspan=2, padx=16, pady=(2, 0))
    copyright_label = ctk.CTkLabel(root, text="© 2024 Markus Welschof", text_color="white")
    copyright_label.grid(row=len(status_dict) + 8, column=0, columnspan=2, padx=16, pady=(0, 8))

    threading.Thread(target=main, daemon=True).start()
    gui_update_job = root.after(2000, update_gui)  # Start the GUI update loop
    root.mainloop()


if __name__ == "__main__":
    run()
