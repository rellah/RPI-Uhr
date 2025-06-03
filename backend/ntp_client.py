import socket
import struct
import time

def get_ntp_time(server='192.168.12.210', port=123):
    try:
        # NTP-Paket erstellen
        data = b'\x1b' + 47 * b'\0'
        socket.setdefaulttimeout(5)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, (server, port))
        data, _ = sock.recvfrom(1024)
        
        # Zeit aus Paket extrahieren
        if data:
            ntp_time = struct.unpack('!12I', data)[10]
            ntp_time -= 2208988800  # NTP to Unix timestamp
            return ntp_time
    except Exception:
        return None