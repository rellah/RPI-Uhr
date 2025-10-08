import socket
import struct

def get_ntp_time(server="192.168.12.210", port=123):
    data = b"\x1b" + 47 * b"\0"
    socket.setdefaulttimeout(5)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(data, (server, port))
            packet, _ = sock.recvfrom(1024)

        if packet and len(packet) >= 48:
            ntp_time = struct.unpack("!12I", packet[:48])[10]
            ntp_time -= 2208988800
            return ntp_time
    except (OSError, struct.error) as error:
        print(f"NTP request failed: {error}")
    return None
