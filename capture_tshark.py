import datetime
import json
import os
import threading
import re
import subprocess


def _hidden_subprocess_kwargs():
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


def get_first_physical_ethernet_adapter():
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-NetAdapter -Physical | "
            "Where-Object { $_.Name -like 'Ethernet*' -or $_.InterfaceDescription -match 'Ethernet' } | "
            "Sort-Object InterfaceIndex | "
            "Select-Object -First 1 InterfaceIndex, Name, InterfaceDescription, Status | "
            "ConvertTo-Json -Compress"
        ),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **_hidden_subprocess_kwargs(),
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Unable to query physical Ethernet adapters")

    try:
        adapter = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Unable to parse physical Ethernet adapter information") from error

    if not adapter:
        raise RuntimeError("No physical Ethernet adapter found")

    return adapter


def parse_tshark_interfaces(tshark_output):
    interfaces = []

    for line in tshark_output.splitlines():
        match = re.match(r"^(\d+)\.\s+(\S+)\s+\((.+)\)$", line.strip())
        if not match:
            continue

        interfaces.append(
            {
                "number": match.group(1),
                "device": match.group(2),
                "label": match.group(3),
            }
        )

    return interfaces


def resolve_tshark_ethernet_interface(tshark_path):
    ethernet_adapter = get_first_physical_ethernet_adapter()
    adapter_name = ethernet_adapter.get("Name", "")

    tshark_interfaces_output = subprocess.run(
        [tshark_path, "-D"],
        capture_output=True,
        text=True,
        check=False,
        **_hidden_subprocess_kwargs(),
    )
    if tshark_interfaces_output.returncode != 0:
        raise RuntimeError(tshark_interfaces_output.stderr.strip() or "Unable to list tshark interfaces")

    tshark_interfaces = parse_tshark_interfaces(tshark_interfaces_output.stdout)
    for tshark_interface in tshark_interfaces:
        if tshark_interface["label"] == adapter_name:
            return tshark_interface, ethernet_adapter

    raise RuntimeError(f"No tshark capture interface matched Ethernet adapter '{adapter_name}'")

class TsharkCaptureThread(threading.Thread):
    def __init__(self, target_folder, update_status_func, port=30303, duration=60*60*10):
        super().__init__()
        self.target_folder = target_folder
        self.update_status_func = update_status_func
        self.port = port
        self.duration = duration
        self.log_file_path = f"{target_folder}\\tshark_capture.pcap"
        self._stop_event = threading.Event()
        self.process = None

    def _get_capture_file_size(self):
        if not os.path.exists(self.log_file_path):
            return 0
        return os.path.getsize(self.log_file_path)

    def _wait_for_capture_activity(self, adapter_name):
        packets_received = False

        while self.process and self.process.poll() is None and not self._stop_event.is_set():
            file_size = self._get_capture_file_size()
            if file_size > 2048:
                self.update_status_func("tshark", "packets recieved", "green")
                packets_received = True
                break

            self.update_status_func(
                "tshark",
                f"Recording on {adapter_name}; waiting for packets ({file_size} bytes)",
                "yellow",
            )
            if self._stop_event.wait(5):
                break

        return packets_received

    def run(self):
        try:
            tshark_path = r"C:\Program Files\Wireshark\tshark.exe"
            if not os.path.exists(tshark_path):
                raise FileNotFoundError("tshark.exe not found in C:\\Program Files\\Wireshark")

            tshark_interface, ethernet_adapter = resolve_tshark_ethernet_interface(tshark_path)
            adapter_name = ethernet_adapter.get("Name") or tshark_interface["label"]

            command = [
                tshark_path,
                '-f', f'udp port {self.port}',
                '-a', f'duration:{self.duration}',
                '-i', tshark_interface['device'],
                '-w', self.log_file_path
            ]
            self.update_status_func(
                "tshark",
                f"Recording on {adapter_name} for {self.duration}s",
                "yellow",
            )
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **_hidden_subprocess_kwargs(),
            )
            packets_received = self._wait_for_capture_activity(adapter_name)
            _, stderr = self.process.communicate()

            if self.process.returncode == 0 and not self._stop_event.is_set() and not packets_received:
                self.update_status_func("tshark", f"Finished on {adapter_name}", "green")
            elif not self._stop_event.is_set():
                error_message = stderr.strip() or "tshark capture failed"
                self.update_status_func("tshark", f"Error: {error_message}", "red")

        except Exception as e:
            self.update_status_func("tshark", f"Error: {e}", "red")

    def stop(self):
        self._stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

# Example usage:
# target_folder = "path_to_target_folder"
# update_status_func = lambda msg: print(msg)
# tshark_thread = TsharkCaptureThread(target_folder, update_status_func)
# tshark_thread.start()
# To stop the thread:
# tshark_thread.stop()
# tshark_thread.join()

