"""Udp bağlantısı ve kontrol paketleri için modül.
"""
import logging
import socket
from dataclasses import dataclass
from typing import Optional

@dataclass
class ControlPacket:
    forward: int
    strafe: int
    vertical: int
    yaw: int

    def format(self) -> str:
        return f"F{self.forward},S{self.strafe},V{self.vertical},Y{self.yaw}"

class UDPConnection:
    def __init__(
        self,
        target_ip: str,
        target_port: int,
        use_simulation: bool = True,
        local_port: Optional[int] = None,
    ):
        self.target_ip = target_ip
        self.target_port = target_port
        self.use_simulation = use_simulation
        self.local_port = local_port
        self.socket: Optional[socket.socket] = None

    def connect(self):
        if self.use_simulation:
            logging.info(
                "UDP bağlantısı simülasyon modunda. Hedef: %s:%d",
                self.target_ip,
                self.target_port,
            )
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if self.local_port is not None:
                self.socket.bind(("0.0.0.0", self.local_port))
            logging.info(
                "UDP bağlantısı hazırlanıyor: %s:%d",
                self.target_ip,
                self.target_port,
            )
        except Exception as exc:
            logging.error("UDP soket oluşturulamadı: %s", exc)
            self.socket = None

    def send(self, packet: ControlPacket):
        message = packet.format().encode("ascii")
        if self.use_simulation:
            logging.info("Gönderilen UDP paket: %s", message.decode("ascii"))
            return
            """Oblivion"""
        if self.socket is None:
            raise RuntimeError("UDP soket hazır değil")

        self.socket.sendto(message, (self.target_ip, self.target_port))

    def close(self):
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
