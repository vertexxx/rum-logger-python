import threading
import can
import time
import datetime
import binascii

def capture_vector_canfd(target_folder, update_status_func, channel_in=0, n_bitrate=500000, fd_bitrate=2000000, stop_event=None):
    log_file_path = f"{target_folder}/vector_canfd_data.log"
    with open(log_file_path, 'a') as log_file:
        bus = None
        try:
            update_status_func("vector_canfd", "prepareing interface "+str(channel_in), "yellow")
            bus = can.interface.Bus(channel=channel_in, bustype='vector', bitrate=n_bitrate, fd=True, app_name='python-can', data_bitrate=fd_bitrate)
            update_status_func("vector_canfd", "listening " +str(channel_in), "yellow")
            firstmsgrecieved=False
            while stop_event is None or not stop_event.is_set():
                message = bus.recv(timeout=1.0)
                if message is not None:
                    #timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    current_time = time.time()
                    log_message = f"({current_time:.6f}) Channel{str(message.channel)} {str(f'{message.arbitration_id:0x}').upper()}#{str(message.data.hex().upper())}\n"
                    log_file.write(log_message)
                    log_file.flush()
                    if firstmsgrecieved==False:
                        update_status_func("vector_canfd", "Messages recieved on Channel " +str(channel_in), "green")
                    firstmsgrecieved=True
        except can.interfaces.vector.VectorInitializationError as e:
            update_status_func("vector_canfd", "No HW", "grey")
            print(f"Error: {e}")
            print("Please make sure the Vector CAN FD driver is installed and the Vector hardware is connected.")
        except Exception as e:
            update_status_func("vector_canfd", "Error", "red")
            print(f"Error: {e}")
            print("Please make sure the Vector CAN FD driver is installed and the Vector hardware is connected.")
        finally:
            if bus is not None:
                try:
                    bus.shutdown()
                except Exception:
                    pass
            if stop_event is not None and stop_event.is_set():
                update_status_func("vector_canfd", "Stopped", "gray")