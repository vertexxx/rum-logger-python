import time
import os
import threading
import datetime
import cv2

from upload_paths import ensure_uploads_dir
from video_device_utils import format_resolution, get_requested_video_resolution, open_video_capture


def get_center_crop_bounds(frame_width, frame_height, crop_factor):
    if crop_factor is None or crop_factor <= 1.0:
        return 0, 0, frame_width, frame_height

    crop_width = max(1, min(frame_width, int(round(frame_width / crop_factor))))
    crop_height = max(1, min(frame_height, int(round(frame_height / crop_factor))))
    offset_x = max((frame_width - crop_width) // 2, 0)
    offset_y = max((frame_height - crop_height) // 2, 0)
    return offset_x, offset_y, crop_width, crop_height

class VideoCaptureThread(threading.Thread):
    def __init__(self, target_folder, update_status_func, capture_time=30, device_number=0, computername="unknown", status_name=None, crop_factor=None, preview_folder=None):
        super().__init__()
        self.target_folder = target_folder
        self.update_status_func = update_status_func
        self.capture_time = capture_time
        self.device_number = device_number
        self.computername = computername
        self.status_name = status_name or "video" + str(self.device_number)
        self.crop_factor = crop_factor
        self.preview_folder = preview_folder or ensure_uploads_dir()
        self._stop_event = threading.Event()

    def get_device_folder(self):
        return os.path.join(self.target_folder, f"device{self.device_number}")

    def ensure_device_folder(self):
        try:
            os.makedirs(self.get_device_folder(), exist_ok=True)
            return True
        except Exception as e:
            self.update_status_func(self.status_name, f"Error: {e}", "red")
            return False

    def log(self, message, color="yellow"):
        print("capture_video thread: " + message)
        self.update_status_func(self.status_name, message, color)
        try:
            with open(os.path.join(self.get_device_folder(), "log_video.txt"), "a") as log_file:
                log_file.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        except Exception as e:
            self.update_status_func(self.status_name, f"Error: {e}", "red")

    def run(self):
        if not self.ensure_device_folder():
            return

        fourcc = cv2.VideoWriter.fourcc(*'mp4v')
        requested_resolution = get_requested_video_resolution(self.crop_factor)

        cap = open_video_capture(self.device_number, requested_resolution=requested_resolution)
        if not cap.isOpened():
            self.log(f"No device {str(self.device_number)}.", "gray")
            return

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        crop_x, crop_y, crop_width, crop_height = get_center_crop_bounds(frame_width, frame_height, self.crop_factor)
        outsize = (crop_width, crop_height)

        if requested_resolution is not None:
            requested_width, requested_height = requested_resolution
            self.log(
                f"Requested {format_resolution(requested_width, requested_height)}, captured {format_resolution(frame_width, frame_height)}, output {format_resolution(crop_width, crop_height)} (center crop {self.crop_factor})",
                "green",
            )
        elif self.crop_factor is not None:
            self.log(
                f"Captured {format_resolution(frame_width, frame_height)}, output {format_resolution(crop_width, crop_height)} (center crop {self.crop_factor})",
                "green",
            )
        else:
            self.log(format_resolution(frame_width, frame_height), "green")

        file_count = 1

        while not self._stop_event.is_set():
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            #self.log(f"opening device", "green")
            output_path = os.path.join(
                self.get_device_folder(),
                f"output_{file_count}_{timestamp}_device{self.device_number}.mp4",
            )
            out = cv2.VideoWriter(output_path, fourcc, 30.0, outsize)
            #self.log(f"device opened", "green")
            file_start_time = time.time()
            framecount=0

            while time.time() - file_start_time < self.capture_time:
                ret, frame = cap.read()
                if not ret:
                    self.log("Error: Failed to capture frame.", "red")
                    break
                if self.crop_factor is not None and self.crop_factor > 1.0:
                    frame = frame[crop_y:crop_y + crop_height, crop_x:crop_x + crop_width]
                out.write(frame)
                framecount += 1
                # Write a rolling preview image for the device.
                if framecount % 150 == 0:
                    try:
                        preview_path = os.path.join(
                            self.preview_folder,
                            f"{self.computername}_{self.device_number}.png",
                        )
                        cv2.imwrite(preview_path, frame)
                    except Exception as e:
                        self.log(f"Error: {e}", "red")
                if self._stop_event.is_set():
                    break

            out.release()
            file_count += 1

        cap.release()
        self.log("Video capture completed.", "green")

    def stop(self):
        self._stop_event.set()

# Example usage:
# target_folder = "path_to_target_folder"
# update_status_func = lambda name, text, color: print(f"{name}: {text} ({color})")
# video_thread = VideoCaptureThread(target_folder, update_status_func)
# video_thread.start()
# To stop the thread:
# video_thread.stop()
# video_thread.join()
