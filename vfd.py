#!/usr/bin/env python3
"""VFD Display - send arbitrary text"""
import serial
import sys
import time

PORT = '/dev/ttyUSB1'

def send(line1="", line2="", keep=False):
    ser = serial.Serial(PORT, 9600, timeout=1)
    
    def write():
        ser.write(bytes([0xFE, 0x48]))
        l1 = line1[:15].center(15).ljust(20)
        l2 = line2[:15].center(15).ljust(20)
        ser.write((l1 + l2).encode())
        ser.flush()
    
    if keep:
        while True:
            write()
            time.sleep(0.5)
    else:
        write()
        time.sleep(0.1)
    
    ser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: vfd.py 'line1' ['line2'] [-k]")
        print("  -k = keep updating (prevents intro screen)")
        sys.exit(1)
    
    keep = '-k' in sys.argv
    args = [a for a in sys.argv[1:] if a != '-k']
    
    line1 = args[0] if len(args) > 0 else ""
    line2 = args[1] if len(args) > 1 else ""
    
    send(line1, line2, keep)
