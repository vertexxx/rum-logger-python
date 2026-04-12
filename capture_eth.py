import datetime
import binascii
import json
import socket
import subprocess

try:
    import pydivert
except ImportError:
    pydivert = None


DEFAULT_ETH_CAPTURE_FRIENDLY_NAME = "Ethernet"


def get_windows_adapter_details():
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-NetAdapter -IncludeHidden | Select-Object InterfaceIndex, Name, InterfaceDescription, Status, MacAddress | ConvertTo-Json -Compress",
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError:
        return {}

    if result.returncode != 0 or not result.stdout.strip():
        return {}

    try:
        adapters = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    if isinstance(adapters, dict):
        adapters = [adapters]

    adapter_details = {}
    for adapter in adapters:
        interface_index = adapter.get("InterfaceIndex")
        if interface_index is None:
            continue
        adapter_details[int(interface_index)] = {
            "friendly_name": adapter.get("Name") or "",
            "description": adapter.get("InterfaceDescription") or "",
            "status": adapter.get("Status") or "",
            "mac_address": adapter.get("MacAddress") or "",
        }

    return adapter_details


def format_capture_eth_device(device):
    label_parts = [f"ifIdx={device['index']}"]

    friendly_name = device.get("friendly_name")
    if friendly_name:
        label_parts.append(friendly_name)
    else:
        label_parts.append(device["name"])

    description = device.get("description")
    if description:
        label_parts.append(f"[{description}]")

    status = device.get("status")
    if status:
        label_parts.append(f"status={status}")

    symbolic_name = device.get("name")
    if symbolic_name and symbolic_name != friendly_name:
        label_parts.append(f"symbolic={symbolic_name}")

    return " | ".join(label_parts)


def find_capture_eth_device(preferred_friendly_name=DEFAULT_ETH_CAPTURE_FRIENDLY_NAME):
    normalized_preferred_name = preferred_friendly_name.casefold()

    for device in list_capture_eth_devices():
        if device.get("friendly_name", "").casefold() == normalized_preferred_name:
            return device

    return None


def resolve_capture_eth_interface_index(interface_index=None, preferred_friendly_name=DEFAULT_ETH_CAPTURE_FRIENDLY_NAME):
    if interface_index is not None:
        return interface_index, None

    preferred_device = find_capture_eth_device(preferred_friendly_name=preferred_friendly_name)
    if preferred_device is None:
        available_names = ", ".join(
            device.get("friendly_name") or device.get("name")
            for device in list_capture_eth_devices()
        )
        raise ValueError(
            f"No ethernet adapter named '{preferred_friendly_name}' found. Available devices: {available_names}"
        )

    return preferred_device["index"], preferred_device


def list_capture_eth_devices():
    devices = []
    adapter_details = get_windows_adapter_details()

    for interface_index, interface_name in socket.if_nameindex():
        adapter_detail = adapter_details.get(interface_index, {})
        devices.append({
            "index": interface_index,
            "name": interface_name,
            "friendly_name": adapter_detail.get("friendly_name", ""),
            "description": adapter_detail.get("description", ""),
            "status": adapter_detail.get("status", ""),
            "mac_address": adapter_detail.get("mac_address", ""),
        })

    return tuple(sorted(devices, key=lambda device: device["index"]))


def build_capture_eth_filter(port=30303, source_ip=None, target_ip=None, interface_index=None):
    filter_parts = [f"udp.DstPort == {port}"]

    if interface_index is not None:
        filter_parts.append(f"ifIdx == {interface_index}")
    if source_ip:
        filter_parts.append(f"ip.SrcAddr == {source_ip}")
    if target_ip:
        filter_parts.append(f"ip.DstAddr == {target_ip}")

    return " and ".join(filter_parts)

# 172.16.0.120
def capture_eth(
    target_folder,
    update_status_func,
    port=30303,
    source_ip=None,
    target_ip=None,
    interface_index=None,
    preferred_friendly_name=DEFAULT_ETH_CAPTURE_FRIENDLY_NAME,
):
    log_file_path = f"{target_folder}/eth_data.dat"

    resolved_interface_index, resolved_device = resolve_capture_eth_interface_index(
        interface_index=interface_index,
        preferred_friendly_name=preferred_friendly_name,
    )

    with open(log_file_path, 'a') as log_file:
        filter_str = build_capture_eth_filter(
            port=port,
            source_ip=source_ip,
            target_ip=target_ip,
            interface_index=resolved_interface_index,
        )

        firstmessagerecieved=False

        try:
            if pydivert is None:
                raise ImportError("pydivert is not installed")

            with pydivert.WinDivert(filter_str) as w:
                device_label = preferred_friendly_name
                if resolved_device is not None:
                    device_label = resolved_device.get("friendly_name") or resolved_device.get("name") or preferred_friendly_name
                update_status_func("eth", f"waiting for packets on {device_label} (ifIdx {resolved_interface_index})", "yellow")
                for packet in w:
                    if packet.is_outbound:
                        continue
                    if firstmessagerecieved==False:
                        update_status_func("eth", "recieving", "yellow")
                        firstmessagerecieved=True
                    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %Y-%m-%d %H:%M:%S')
                    hex_data = binascii.hexlify(packet.raw).decode('utf-8')
                    log_message = f"{timestamp} - {packet.src_addr}:{packet.src_port} -> {packet.dst_addr}:{packet.dst_port} - {hex_data}\n"
                    log_file.write(log_message)
                    log_file.flush()
                update_status_func("eth", "Finished", "blue")
        except Exception as e:
            update_status_func("eth", "Error", "red")
            print(f"Ethernet capture failed: {e}")
            print("Please run the script as an administrator and verify pydivert is installed.")


if __name__ == "__main__":
    selected_device = find_capture_eth_device()
    if selected_device is not None:
        print(f"Selected default adapter: {format_capture_eth_device(selected_device)}")
    else:
        print(f"Selected default adapter: not found for friendly name '{DEFAULT_ETH_CAPTURE_FRIENDLY_NAME}'")
    for device in list_capture_eth_devices():
        print(format_capture_eth_device(device))