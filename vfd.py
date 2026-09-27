#!/usr/bin/env python3
"""VFD Display - send arbitrary text"""
import serial
import serial.tools.list_ports
import argparse
import sys
import time

CH340_VID_PID = (0x1a86, 0x7523)

def find_vfd_port():
    """Auto-detect CH340-based VFD display serial port."""
    for port in serial.tools.list_ports.comports():
        if (port.vid, port.pid) == CH340_VID_PID:
            return port.device
    return None

def send(port, line1="", line2="", keep=False):
    ser = serial.Serial(port, 9600, timeout=1)

    def write():
        ser.write(bytes([0xFE, 0x48]))
        l1 = line1[:15].center(15).ljust(20)
        l2 = line2[:15].center(15).ljust(20)
        # ASCII only: multi-byte UTF-8 would shift line 2 off its offset
        ser.write((l1 + l2).encode('ascii', 'replace'))
        ser.flush()

    try:
        if keep:
            while True:
                write()
                time.sleep(0.5)
        else:
            write()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Send text to a USB2VFD display')
    parser.add_argument('line1', help='Line 1 text')
    parser.add_argument('line2', nargs='?', default='', help='Line 2 text')
    parser.add_argument('-k', '--keep', action='store_true',
                        help='Keep updating (prevents intro screen)')
    parser.add_argument('-p', '--port', default=None,
                        help='Serial port (auto-detects CH340 if omitted)')
    args = parser.parse_args()

    port = args.port or find_vfd_port()
    if port is None:
        print("No CH340 VFD display found. Is it plugged in? Use -p to specify the port.")
        sys.exit(1)

    send(port, args.line1, args.line2, args.keep)
