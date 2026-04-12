import threading
import datetime
import time
from PCANBasic import *

def capture_peak_canfd(target_folder, update_status_func=None, use_extended_identifiers=True, listen_only=True, stop_event=None):
    log_file_path = f"{target_folder}/peak_canfd_data.log"
    with open(log_file_path, 'a') as log_file:
        pcan = None
        channel = PCAN_USBBUS1
        try:
            if update_status_func:
                update_status_func("peak_canfd", "preparing interface", "yellow")
            
            # Initialize PCANBasic
            pcan = PCANBasic()
            #bitrate_fd = b"f_clock=80000000,nom_brp=10,nom_tseg1=13,nom_tseg2=2,nom_sjw=1,data_brp=4,data_tseg1=7,data_tseg2=2,data_sjw=1,iso_mode=1"
            #bitrate_fd = b"f_clock=80000000,nom_brp=10,nom_tseg1=5,nom_tseg2=2,nom_sjw=1,data_brp=4,data_tseg1=7,data_tseg2=2,data_sjw=1"
            bitrate_fd = b"f_clock=80000000,nom_brp=2,nom_tseg1=63,nom_tseg2=16,nom_sjw=16,data_brp=2,data_tseg1=15,data_tseg2=4,data_sjw=4,iso_mode=1"
            #bitrate_fd = b"f_clock=80000000,nom_brp=2,nom_tseg1=63,nom_tseg2=16,nom_sjw=16,data_brp=2,data_tseg1=15,data_tseg2=4,data_sjw=4"
            #bitrate_fd = b"f_clock_mhz=80, nom_brp=8, nom_tseg1=31, nom_tseg2=8, nom_sjw=8, data_brp=2, data_tseg1=15, data_tseg2=4, data_sjw=4"
            #bitrate_fd = b"f_clock=80000000,nom_brp=10,nom_tseg1=5,nom_tseg2=2,nom_sjw=1,data_brp=4,data_tseg1=7,data_tseg2=2,data_sjw=1"
            bitrate_nonfd = PCAN_BAUD_500K

            # Initialize the channel
            result = pcan.InitializeFD(channel, bitrate_fd)

            if result != PCAN_ERROR_OK:
                if update_status_func:
                    update_status_func("peak_canfd", "Initialization FD failed", "red")
                return
            
            # Set the device to listen-only mode if specified
            if listen_only:
                pcan.SetValue(channel, PCAN_LISTEN_ONLY, PCAN_PARAMETER_ON)
            
            if update_status_func:
                update_status_func("peak_canfd", "listening", "yellow")
            firstmessagerecieved=False
            
            # Capture and log CAN FD messages
            cnt_0x225=0
            while stop_event is None or not stop_event.is_set():
                result, msg, timestamp = pcan.ReadFD(channel)
                if result == PCAN_ERROR_OK:
                    current_time = time.time()
                    dlc=msg.DLC # Wie dumm ist das bitte?!?!
                    if dlc==9:
                        dlc=12
                    if dlc==10:
                        dlc=16
                    if dlc==11:
                        dlc=20
                    if dlc==12:
                        dlc=24
                    if dlc==13:
                        dlc=32
                    if dlc==14:
                        dlc=48
                    if dlc==15:
                        dlc=64
                    log_file.write(f"({current_time:.6f}) peak_canfd {msg.ID:X}#{''.join(f'{byte:02X}' for byte in msg.DATA[:dlc])}\n")
                    try:
                        if msg.ID == 550: #0x226
                            cnt_0x225=cnt_0x225+1
                            if cnt_0x225==1 or cnt_0x225%100==1:
                                update_status_func("peak_canfd", f"0x226 len:{str(len(msg.DATA))} dlc:{str(msg.DLC)}", "green")
                    except Exception as e:
                        pass
                    log_file.flush()
                    if not msg.MSGTYPE in [PCAN_MESSAGE_STANDARD, PCAN_MESSAGE_RTR, PCAN_MESSAGE_EXTENDED, PCAN_MESSAGE_FD, 12, 14]:
                        print(f"Unexpected message type: {msg.MSGTYPE}")
                        if update_status_func:
                            update_status_func("peak_canfd", f"Unexpected: {msg.MSGTYPE}", "orange")
                        firstmessagerecieved=False
                    else:
                        if firstmessagerecieved==False:
                            if update_status_func:
                                update_status_func("peak_canfd", "Receiving messages", "green")
                            firstmessagerecieved=True
                elif result != PCAN_ERROR_QRCVEMPTY:
                    error_text = pcan.GetErrorText(result)
                    print(f"Error reading message: {error_text[1]}")
                    #pcan.ResetFD(channel)
                    print("Resetting CAN FD channel if PEAK")
                    if stop_event is not None and stop_event.wait(5.0):
                        break
                #time.sleep(0.001)  # Add a small sleep interval to ensure the queue is read more frequently

        except Exception as e:
            if update_status_func:
                update_status_func("peak_canfd", "Error", "red")
            print(f"Error (Peak): {e}")
            print("Please make sure the Peak CAN FD driver is installed and the Peak hardware is connected.")
        finally:
            if pcan is not None:
                try:
                    pcan.Uninitialize(channel)
                except Exception:
                    pass
            if update_status_func and stop_event is not None and stop_event.is_set():
                update_status_func("peak_canfd", "Stopped", "gray")

if __name__ == "__main__":
    capture_peak_canfd(".")