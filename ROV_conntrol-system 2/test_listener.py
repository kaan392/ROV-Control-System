import socket
import sys

def main() -> None:
    port = 5032
    host = "127.0.0.1"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(1.0)
    print(f"UDP dinleniyor: {host}:{port}")
    print("Paket gelmesini bekliyorum...")

    try:
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            print(f"\nGelen paket: {addr}")
            print(data.decode("ascii", errors="replace"))
    except KeyboardInterrupt:
        print("\nDinleme durduruldu.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()