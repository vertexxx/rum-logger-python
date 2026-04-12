import os
import threading
import time
from urllib.parse import unquote, urlsplit

import requests
import urllib3

from FileUploadThread import get_system_proxies


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


DEFAULT_STREAM_CHUNK_SIZE = 64 * 1024
DEFAULT_STREAM_FILE_BUFFER_SIZE = 1024 * 1024
DEFAULT_STREAM_RETRY_DELAY_SECONDS = 2.0
DEFAULT_STREAM_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_STREAM_READ_TIMEOUT_SECONDS = None
STATUS_UPDATE_INTERVAL_SECONDS = 5.0
INVALID_WINDOWS_FILENAME_CHARACTERS = '<>:"/\\|?*'
WINDOWS_RESERVED_FILENAMES = {
	"CON",
	"PRN",
	"AUX",
	"NUL",
	"COM1",
	"COM2",
	"COM3",
	"COM4",
	"COM5",
	"COM6",
	"COM7",
	"COM8",
	"COM9",
	"LPT1",
	"LPT2",
	"LPT3",
	"LPT4",
	"LPT5",
	"LPT6",
	"LPT7",
	"LPT8",
	"LPT9",
}


def is_supported_stream_url(url):
	parsed_url = urlsplit(url)
	return parsed_url.scheme.lower() in {"http", "https"} and bool(parsed_url.netloc)


def sanitize_stream_output_filename(filename):
	sanitized_filename = "".join(
		"_" if character in INVALID_WINDOWS_FILENAME_CHARACTERS or ord(character) < 32 else character
		for character in filename
	)
	sanitized_filename = sanitized_filename.strip().strip(".")

	if not sanitized_filename:
		sanitized_filename = "stream.log"

	file_stem, file_extension = os.path.splitext(sanitized_filename)
	if file_stem.upper() in WINDOWS_RESERVED_FILENAMES:
		sanitized_filename = f"{file_stem}_stream{file_extension}"

	return sanitized_filename


def derive_stream_output_filename(url):
	parsed_url = urlsplit(url)
	path_segments = [segment for segment in parsed_url.path.split("/") if segment]
	if path_segments:
		candidate_filename = unquote(path_segments[-1])
	else:
		candidate_filename = f"{parsed_url.netloc.replace(':', '_')}.log"

	return sanitize_stream_output_filename(candidate_filename)


def build_stream_capture_configs(stream_urls):
	stream_capture_configs = []
	used_filenames = set()

	for stream_index, stream_url in enumerate(stream_urls, start=1):
		base_filename = derive_stream_output_filename(stream_url)
		filename_root, filename_extension = os.path.splitext(base_filename)
		candidate_filename = base_filename
		duplicate_index = 2

		while candidate_filename.casefold() in used_filenames:
			candidate_filename = f"{filename_root}_{duplicate_index}{filename_extension}"
			duplicate_index += 1

		used_filenames.add(candidate_filename.casefold())
		stream_capture_configs.append(
			{
				"status_name": f"stream_log_{stream_index}",
				"url": stream_url,
				"filename": candidate_filename,
				"display_name": candidate_filename,
			}
		)

	return tuple(stream_capture_configs)


def format_byte_count(byte_count):
	scaled_value = float(byte_count)
	for unit in ("B", "KB", "MB", "GB", "TB"):
		if scaled_value < 1024 or unit == "TB":
			if unit == "B":
				return f"{int(scaled_value)} {unit}"
			return f"{scaled_value:.1f} {unit}"
		scaled_value /= 1024

	return f"{int(byte_count)} B"


def shorten_error_message(error_message, max_length=80):
	normalized_error_message = " ".join(str(error_message).split())
	if len(normalized_error_message) <= max_length:
		return normalized_error_message
	return normalized_error_message[: max_length - 3] + "..."


class StreamCaptureThread(threading.Thread):
	def __init__(
		self,
		target_folder,
		stream_config,
		update_status_func,
		stop_event=None,
		chunk_size=DEFAULT_STREAM_CHUNK_SIZE,
		file_buffer_size=DEFAULT_STREAM_FILE_BUFFER_SIZE,
		retry_delay_seconds=DEFAULT_STREAM_RETRY_DELAY_SECONDS,
		connect_timeout_seconds=DEFAULT_STREAM_CONNECT_TIMEOUT_SECONDS,
		read_timeout_seconds=DEFAULT_STREAM_READ_TIMEOUT_SECONDS,
	):
		super().__init__(name=stream_config["status_name"])
		self.target_folder = target_folder
		self.stream_config = stream_config
		self.status_name = stream_config["status_name"]
		self.url = stream_config["url"]
		self.filename = stream_config["filename"]
		self.output_path = os.path.join(target_folder, self.filename)
		self.update_status_func = update_status_func
		self.shared_stop_event = stop_event
		self.local_stop_event = threading.Event()
		self.chunk_size = chunk_size
		self.file_buffer_size = file_buffer_size
		self.retry_delay_seconds = retry_delay_seconds
		self.request_timeout = (connect_timeout_seconds, read_timeout_seconds)
		self.bytes_written = 0
		self._response = None
		self.session = requests.Session()
		self.session.verify = False
		self.session.trust_env = True

		system_proxies = get_system_proxies()
		if system_proxies:
			self.session.proxies.update(system_proxies)

	def should_stop(self):
		return self.local_stop_event.is_set() or (
			self.shared_stop_event is not None and self.shared_stop_event.is_set()
		)

	def set_status(self, text, color):
		if self.update_status_func:
			self.update_status_func(self.status_name, text, color)

	def close_response(self):
		if self._response is None:
			return

		try:
			self._response.close()
		except Exception:
			pass
		finally:
			self._response = None

	def wait_for_retry(self):
		retry_until = time.monotonic() + self.retry_delay_seconds
		while not self.should_stop() and time.monotonic() < retry_until:
			remaining_time = retry_until - time.monotonic()
			self.local_stop_event.wait(min(0.25, remaining_time))
		return self.should_stop()

	def stream_into_file(self, output_file):
		received_any_data = False
		last_flush_time = time.monotonic()
		last_status_update_time = 0.0

		with self.session.get(self.url, stream=True, timeout=self.request_timeout) as response:
			self._response = response
			response.raise_for_status()
			self.set_status(f"connected {self.filename}", "yellow")

			for chunk in response.iter_content(chunk_size=self.chunk_size):
				if self.should_stop():
					break
				if not chunk:
					continue

				output_file.write(chunk)
				self.bytes_written += len(chunk)
				received_any_data = True

				current_time = time.monotonic()
				if current_time - last_flush_time >= 1.0:
					output_file.flush()
					last_flush_time = current_time

				if current_time - last_status_update_time >= STATUS_UPDATE_INTERVAL_SECONDS:
					self.set_status(
						f"receiving {self.filename} ({format_byte_count(self.bytes_written)})",
						"green",
					)
					last_status_update_time = current_time

		output_file.flush()
		self.close_response()
		return received_any_data

	def run(self):
		try:
			with open(self.output_path, "ab", buffering=self.file_buffer_size) as output_file:
				while not self.should_stop():
					try:
						self.set_status(f"connecting {self.filename}", "yellow")
						received_any_data = self.stream_into_file(output_file)

						if self.should_stop():
							break

						if received_any_data:
							self.set_status(
								f"finished {self.filename} ({format_byte_count(self.bytes_written)})",
								"blue",
							)
							return

						self.set_status(f"connected, waiting for data: {self.filename}", "yellow")
						if self.wait_for_retry():
							break
					except requests.HTTPError as error:
						status_code = getattr(error.response, "status_code", "unknown")
						self.set_status(f"http {status_code}: {self.filename}", "red")
						if self.wait_for_retry():
							break
					except requests.RequestException as error:
						if self.should_stop():
							break
						self.set_status(
							f"retrying {self.filename}: {shorten_error_message(error)}",
							"orange",
						)
						if self.wait_for_retry():
							break
					finally:
						self.close_response()
		except Exception as error:
			self.set_status(f"error {self.filename}: {shorten_error_message(error)}", "red")
		finally:
			self.close_response()
			self.session.close()
			if self.should_stop():
				self.set_status(
					f"stopped {self.filename} ({format_byte_count(self.bytes_written)})",
					"gray",
				)

	def stop(self):
		self.local_stop_event.set()
		self.close_response()
		self.session.close()
