import time
import serial

PORT = "COM3"  


def main():
    ser = serial.Serial(
        port=PORT,
        baudrate=9600,
        bytesize=serial.SEVENBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE,
        timeout=1.0,
    )

    print(f"Opened {PORT}")


    def send_frame(raw: bytes) -> str:
        ser.write(raw)
        ser.flush()
        line = ser.readline().decode("ascii", errors="replace").strip()
        print("REPLY:", repr(line))
        return line

    # 1) Build PC mode frame (command 54, head 0)
    pc_mode_frame = b""  
    send_frame(pc_mode_frame)
    time.sleep(0.5)

    # 2) Build measurement frame (command 10, head 0)
    meas_frame = b""  
    send_frame(meas_frame)

    ser.close()


if __name__ == "__main__":
    main()
