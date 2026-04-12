import pyshark
import csv
import binascii
import os
from tkinter import Tk, filedialog

def pcap_to_csv(pcap_file):
    """
    Converts a PCAP file to a CSV file with fields:
    timestamp, source-ip, source-port, target-ip, target-port, data (hex encoded).

    :param pcap_file: Path to the input PCAP file.
    """
    try:
        # Generate output CSV file name
        csv_file = os.path.splitext(pcap_file)[0] + ".csv"

        # Open the PCAP file
        capture = pyshark.FileCapture(pcap_file)

        # Open the CSV file for writing
        with open(csv_file, mode='w', newline='') as file:
            writer = csv.writer(file, delimiter=';')
            # Write header
            writer.writerow(['timestamp', 'source-ip', 'source-port', 'target-ip', 'target-port', 'data'])
            
            print("starting converting packets")
            packets = 0
            
            for packet in capture:
                try:
                    # Extract timestamp
                    timestamp = packet.sniff_time.isoformat()

                    # Extract IP and transport layer details
                    src_ip = packet.ip.src if hasattr(packet, 'ip') else None
                    dst_ip = packet.ip.dst if hasattr(packet, 'ip') else None
                    src_port = None
                    dst_port = None

                    if hasattr(packet, 'udp'):
                        src_port = packet.udp.srcport
                        dst_port = packet.udp.dstport
                    elif hasattr(packet, 'tcp'):
                        src_port = packet.tcp.srcport
                        dst_port = packet.tcp.dstport

                    # Extract raw data (payload)
                    data = None
                    if hasattr(packet, 'data') and hasattr(packet.data, 'binary_value'):
                        try:
                            print(packet.data)
                            print(packet.data.binary_value)
                            data = binascii.hexlify(packet.data.binary_value).decode('utf-8')
                        except Exception:
                            data = None  # If hexlify fails, default to None
                    else:
                        try:
                            data = packet.data.data
                        except Exception as e:
                            pass
                        try:
                            packet.udp.payload.replace(":","")
                        except Exception as e:
                            pass
                    # Write to CSV row if essential fields exist
                    if src_ip and dst_ip and data!=None:
                        writer.writerow([timestamp, src_ip, src_port, dst_ip, dst_port, data])
                        packets=packets+1
                        if packets==1:
                            print(str(packets)+" parsed")
                        if packets==10:
                            print(str(packets)+" parsed")
                        if packets==100:
                            print(str(packets)+" parsed")
                        if packets==1000:
                            print(str(packets)+" parsed")
                        if packets%10000 == 0:
                            print(str(packets)+" parsed")
                except Exception as e:
                    print(f"Error processing packet: {e}")

        print(f"PCAP file converted successfully to {csv_file}")

    except Exception as e:
        print(f"Failed to convert PCAP to CSV: {e}")


if __name__ == "__main__":
    # Hide the root Tkinter window
    Tk().withdraw()

    # Open a file dialog to select the PCAP file
    pcap_file = filedialog.askopenfilename(
        title="Select a PCAP file",
        filetypes=[("PCAP files", "*.pcap"), ("All files", "*.*")]
    )

    if pcap_file:
        pcap_to_csv(pcap_file)
    else:
        print("No file selected.")
