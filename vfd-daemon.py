#!/usr/bin/env python3
"""VFD Daemon - rotating screens with optional UDP input"""
import serial
import time
import socket
import argparse
import subprocess
import threading

SERIAL_PORT = '/dev/ttyUSB1'
UDP_PORT = 5566

# =============================================================================
# DEFAULT DISPLAY SCREENS - Edit these to customize what shows when idle
# Each screen is a function returning (line1, line2) or None to skip
# Screens rotate every SCREEN_INTERVAL seconds
# =============================================================================
SCREEN_INTERVAL = 30  # seconds between screen changes
DEFAULT_FRESHNESS = 43200  # 12 hours - UDP content considered stale after this (0 = infinite)

def screen_clock_stats():
    """Clock and system stats"""
    line1 = time.strftime('%H:%M:%S %d/%m')
    line2 = f"L:{get_load()} {get_cpu_temp()}"
    return (line1, line2)

def screen_host_ip():
    """Hostname and external IP"""
    line1 = socket.gethostname()[:15]
    line2 = get_external_ip()
    return (line1, line2)

def screen_udp():
    """UDP content (skipped if no fresh data)"""
    if not _udp_content['lines']:
        return None
    freshness = _config['freshness']
    if freshness > 0 and time.time() - _udp_content['time'] > freshness:
        return None  # stale
    return _udp_content['lines']

# Add/remove/reorder screens here (return None to skip):
SCREENS = [
    screen_clock_stats,
    screen_host_ip,
    screen_udp,
]
# =============================================================================

# UDP content storage
_udp_content = {'lines': None, 'time': 0, 'show_until': 0}

# Runtime config (set from args in main)
_config = {'freshness': DEFAULT_FRESHNESS, 'udp_only': False}

# Cache for external IP
_ip_cache = {'ip': None, 'time': 0}
IP_CACHE_TTL = 20  # seconds

def sanitize_udp(data):
    """Sanitize UDP payload: decode, strip control chars, split lines"""
    try:
        text = data.decode('utf-8', errors='replace')
    except Exception:
        return None
    # Keep only printable ASCII + newline, strip VFD command prefix (0xFE)
    text = ''.join(c if c == '\n' or 0x20 <= ord(c) < 0x7F else '' for c in text)
    if not text.strip():  # reject if only whitespace
        return None
    lines = text.split('\n')[:2]
    line1 = lines[0][:15] if lines else ''
    line2 = lines[1][:15] if len(lines) > 1 else ''
    return (line1, line2)

def udp_listener(bind_addr):
    """Background thread: listen for UDP packets"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_addr, UDP_PORT))
    print(f"UDP listening on {bind_addr}:{UDP_PORT}")
    while True:
        try:
            data, _ = sock.recvfrom(1024)
            lines = sanitize_udp(data)
            if lines:
                now = time.time()
                _udp_content['lines'] = lines
                _udp_content['time'] = now
                _udp_content['show_until'] = now + SCREEN_INTERVAL  # jump to UDP immediately
        except Exception as e:
            print(f"UDP error: {e}")

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
    except Exception:
        ip = '?.?.?.?'
    _ip_cache['ip'] = ip
    _ip_cache['time'] = now
    return ip

def get_cpu_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return f"{int(f.read()) // 1000}C"
    except Exception:
        return "??C"

def get_load():
    try:
        with open('/proc/loadavg') as f:
            return f.read().split()[0]
    except Exception:
        return "?.??"

def get_active_screens():
    """Get list of screens that have content (non-None)"""
    active = []
    for screen_fn in SCREENS:
        result = screen_fn()
        if result is not None:
            active.append(result)
    return active if active else [screen_clock_stats()]  # fallback

def default_display():
    """Rotate through active screens based on time, jump to UDP on new message"""
    # Jump to UDP content if just received
    if time.time() < _udp_content['show_until']:
        return _udp_content['lines']
    # UDP-only mode: show UDP content or blank
    if _config['udp_only']:
        content = screen_udp()
        return content if content else ('', '')
    # Normal rotation
    screens = get_active_screens()
    screen_index = int(time.time() / SCREEN_INTERVAL) % len(screens)
    return screens[screen_index]

def main():
    parser = argparse.ArgumentParser(description='VFD Display Daemon')
    parser.add_argument('line1', nargs='?', default=None, help='Line 1 text (static mode)')
    parser.add_argument('line2', nargs='?', default='', help='Line 2 text (static mode)')
    parser.add_argument('-p', '--port', default=SERIAL_PORT, help='Serial port')
    parser.add_argument('-c', '--center', action='store_true', help='Center text (static mode)')
    parser.add_argument('-L', '--lan', action='store_true', help='Listen on all interfaces (0.0.0.0)')
    parser.add_argument('-u', '--udp-only', action='store_true', help='Only show UDP content (blank until received)')
    parser.add_argument('-f', '--freshness', type=int, default=DEFAULT_FRESHNESS,
                        help='UDP content freshness in seconds (0 = infinite, default: 43200)')
    args = parser.parse_args()

    # Set runtime config
    _config['freshness'] = args.freshness
    _config['udp_only'] = args.udp_only

    # Start UDP listener
    bind_addr = '0.0.0.0' if args.lan else '127.0.0.1'
    udp_thread = threading.Thread(target=udp_listener, args=(bind_addr,), daemon=True)
    udp_thread.start()

    # Static mode: command line args provided
    static_content = None
    if args.line1 is not None:
        static_content = (args.line1[:15], args.line2[:15])

    ser = serial.Serial(args.port, 9600, timeout=1)

    def fmt(text, force_center=None):
        """Format text for display, pad to 20 chars.
        Auto-centers unless text has leading/trailing spaces.
        force_center overrides auto-detection."""
        if force_center is None:
            # Auto-detect: center only if no manual spacing
            center = text == text.strip()
        else:
            center = force_center
        return text.center(15).ljust(20) if center else text.ljust(20)

    while True:
        try:
            if static_content:
                line1, line2 = static_content
                force_center = True if args.center else None
            else:
                line1, line2 = default_display()
                force_center = None  # auto-detect

            ser.write(bytes([0xFE, 0x48]))
            ser.write(fmt(line1, force_center).encode())
            ser.write(fmt(line2, force_center).encode())
            ser.flush()
            time.sleep(0.5)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
            try:
                ser.close()
                ser = serial.Serial(args.port, 9600, timeout=1)
            except Exception:
                pass

if __name__ == "__main__":
    main()
