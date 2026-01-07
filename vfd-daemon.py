#!/usr/bin/env python3
"""VFD Daemon - displays from args, file, or falls back to clock/stats"""
import serial
import time
import os
import socket
import argparse
import subprocess

PORT = '/dev/ttyUSB1'
DISPLAY_FILE = '/tmp/vfd.txt'

# =============================================================================
# DEFAULT DISPLAY SCREENS - Edit these to customize what shows when idle
# Each screen is a function returning (line1, line2)
# Screens rotate every SCREEN_INTERVAL seconds
# =============================================================================
SCREEN_INTERVAL = 30  # seconds between screen changes

def screen_clock_stats():
    """Screen 1: Clock and system stats"""
    line1 = time.strftime('%H:%M:%S %d/%m')  # 14 chars: "HH:MM:SS DD/MM"
    line2 = f"L:{get_load()} {get_cpu_temp()}"
    return (line1, line2)

def screen_host_ip():
    """Screen 2: Hostname and external IP"""
    line1 = socket.gethostname()[:15]
    line2 = get_external_ip()
    return (line1, line2)

# Add/remove/reorder screens here:
SCREENS = [
    screen_clock_stats,
    screen_host_ip,
]
# =============================================================================

# Cache for external IP
_ip_cache = {'ip': None, 'time': 0}
IP_CACHE_TTL = 20  # seconds

def get_external_ip():
    """Fetch external IP with caching"""
    now = time.time()
    if _ip_cache['ip'] and (now - _ip_cache['time']) < IP_CACHE_TTL:
        return _ip_cache['ip']
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '5', 'ifconfig.me'],
            capture_output=True, text=True
        )
        ip = result.stdout.strip()[:15] if result.returncode == 0 else '?.?.?.?'
    except:
        ip = '?.?.?.?'
    _ip_cache['ip'] = ip
    _ip_cache['time'] = now
    return ip

def get_cpu_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return f"{int(f.read()) // 1000}C"
    except:
        return "??C"

def get_load():
    with open('/proc/loadavg') as f:
        return f.read().split()[0]

def parse_display_file():
    """Read and validate display file. Returns (line1, line2) or None."""
    try:
        if not os.path.exists(DISPLAY_FILE):
            return None
        
        # Check file age - ignore if older than 60s (stale)
        if time.time() - os.path.getmtime(DISPLAY_FILE) > 60:
            return None
        
        with open(DISPLAY_FILE, 'r') as f:
            lines = f.read().splitlines()
        
        line1 = lines[0] if len(lines) > 0 else ""
        line2 = lines[1] if len(lines) > 1 else ""
        
        return (line1[:15], line2[:15])
    except:
        return None

def default_display():
    """Fallback: rotate through SCREENS based on time"""
    screen_index = int(time.time() / SCREEN_INTERVAL) % len(SCREENS)
    return SCREENS[screen_index]()

def main():
    parser = argparse.ArgumentParser(description='VFD Display Daemon')
    parser.add_argument('line1', nargs='?', default=None, help='Line 1 text')
    parser.add_argument('line2', nargs='?', default='', help='Line 2 text')
    parser.add_argument('-p', '--port', default=PORT, help='Serial port')
    parser.add_argument('-f', '--file', default=DISPLAY_FILE, help='Display file path')
    parser.add_argument('-c', '--center', action='store_true', help='Center text')
    args = parser.parse_args()
    
    # Static mode: command line args provided
    static_content = None
    if args.line1 is not None:
        static_content = (args.line1[:15], args.line2[:15])

    ser = serial.Serial(args.port, 9600, timeout=1)

    def fmt(text, center):
        """Format text for display: optionally center, then pad to 20 chars"""
        return text.center(15).ljust(20) if center else text.ljust(20)

    while True:
        try:
            # Priority: 1) CLI args, 2) file, 3) default clock
            if static_content:
                content = static_content
                center = args.center
            else:
                content = parse_display_file()
                if content is None:
                    content = default_display()
                center = True  # always center file/default content

            line1, line2 = content

            ser.write(bytes([0xFE, 0x48]))
            ser.write(fmt(line1, center).encode())
            ser.write(fmt(line2, center).encode())
            ser.flush()
            time.sleep(0.5)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
            try:
                ser.close()
                ser = serial.Serial(args.port, 9600, timeout=1)
            except:
                pass

if __name__ == "__main__":
    main()
