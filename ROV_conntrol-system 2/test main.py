"""Oblivion - ROV Ground Control Station Main Module (Klavye Simülasyonlu Test Modu)"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback

# Windows'ta ayrı konsolda çalıştır
if __name__ == "__main__" and sys.platform == "win32":
    if not os.environ.get("ROV_CONSOLE_SPAWNED"):
        env = os.environ.copy()
        env["ROV_CONSOLE_SPAWNED"] = "1"
        subprocess.Popen(
            [sys.executable, __file__],
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        sys.exit(0)

# Klavye dinleyicisi için pynput kontrolü
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

from calibration import run_calibration
from communication import ControlPacket, UDPConnection
from controller import JoystickController
from gui import run_live_display, show_waiting_screen, console, get_logo_text
from joystick import JoystickError, JoystickManager
from rich.panel import Panel

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "joystick": {
        "deadzone": 0.08,
        "sensitivity": 1.0,
        "axis_mapping": {
            "forward": 1,
            "strafe": 0,
            "vertical": 3,
            "yaw": 2
        },
        "calibration": {}
    },
    "network": {
        "target_ip": "0.0.0.0",
        "target_port": 5032,
        "use_simulation": False,
        "local_port": None
    }
}


# =========================================================
# KLAVYEYİ JOYSTICK GİBİ SİMÜLE EDEN MOCK JOYSTICK SINIFLARI
# =========================================================
class KeyboardSimulatedState:
    """Arayüzün okuduğu Joystick State verilerini klavyeden günceller."""
    def __init__(self):
        self.name = "Klavye Simülatör Joystick (Test)"
        # Axis 0: Strafe (A=-1, D=1)
        # Axis 1: Forward (W=-1, S=1)
        # Axis 2: Yaw (Q=-1, E=1)
        # Axis 3: Vertical (R=1, F=-1)
        self.axes = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
        self.buttons = {i: False for i in range(16)}
        self.hats = {0: (0, 0)}
        
        # gui.py'ın beklediği eksen etiketleri (Eksik olan öznitelik eklendi)
        self.axis_labels = {
            0: "Strafe (X)",
            1: "Forward (Y)",
            2: "Yaw (RZ)",
            3: "Vertical (Z)",
            4: "Axis 4",
            5: "Axis 5"
        }
        self.button_labels = {i: f"Btn {i}" for i in range(16)}

    def get_axis(self, axis_index: int) -> float:
        return self.axes.get(axis_index, 0.0)

    def get_button(self, button_index: int) -> bool:
        return self.buttons.get(button_index, False)


class KeyboardJoystickManager:
    """Arayüzü kandıran ve klavye basışlarını Joystick sinyaline çeviren sınıf."""
    def __init__(self):
        self.state = KeyboardSimulatedState()
        self.is_connected = True
        
        if PYNPUT_AVAILABLE:
            # Klavyeyi arka planda dinlemek için Thread başlat
            self.listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release
            )
            self.listener.daemon = True
            self.listener.start()

    def _on_press(self, key):
        try:
            ch = key.char.lower() if hasattr(key, 'char') and key.char else None
            if ch == 'w':
                self.state.axes[1] = -1.0  # İleri
            elif ch == 's':
                self.state.axes[1] = 1.0   # Geri
            elif ch == 'a':
                self.state.axes[0] = -1.0  # Sol
            elif ch == 'd':
                self.state.axes[0] = 1.0   # Sağ
            elif ch == 'r':
                self.state.axes[3] = 1.0   # Yukarı
            elif ch == 'f':
                self.state.axes[3] = -1.0  # Aşağı
            elif ch == 'q':
                self.state.axes[2] = -1.0  # Yaw Sol
            elif ch == 'e':
                self.state.axes[2] = 1.0   # Yaw Sağ
        except Exception:
            pass

        if key == keyboard.Key.space:
            self.state.buttons[0] = True  # Buton 0 basıldı

    def _on_release(self, key):
        try:
            ch = key.char.lower() if hasattr(key, 'char') and key.char else None
            if ch in ['w', 's']:
                self.state.axes[1] = 0.0
            elif ch in ['a', 'd']:
                self.state.axes[0] = 0.0
            elif ch in ['r', 'f']:
                self.state.axes[3] = 0.0
            elif ch in ['q', 'e']:
                self.state.axes[2] = 0.0
        except Exception:
            pass

        if key == keyboard.Key.space:
            self.state.buttons[0] = False

    def get_state(self):
        return self.state

    def update(self):
        return self.state

    def poll(self):
        return self.state

    def close(self):
        pass


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG


def save_config(config: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        console.print(f"[red]Config kaydedilemedi: {e}[/red]")


def configure_axis_mapping(calibration_data: dict, default_mapping: dict) -> dict:
    mapping = dict(default_mapping)
    if calibration_data:
        for action, data in calibration_data.items():
            if isinstance(data, dict) and "axis" in data:
                mapping[action] = data["axis"]
    return mapping


def main():
    console.clear()

    # --- KLAVYE SIMULASYONU ILE BYPASS ---
    joystick_manager = KeyboardJoystickManager()
    state = joystick_manager.get_state()

    config = load_config()
    joystick_settings = config.get("joystick", DEFAULT_CONFIG["joystick"])
    calibration_data = joystick_settings.get("calibration", {})

    # Kalibrasyon Sorgusu Ekrani
    console.clear()
    console.print(get_logo_text())
    console.print(f"[bold cyan]Algılanan Cihaz:[/bold cyan] [bright_green]{state.name}[/bright_green]")
    if not PYNPUT_AVAILABLE:
        console.print("[bold red]Not: 'pynput' kütüphanesi bulunamadı. Klavyeden canlı veri testi için 'pip install pynput' yapabilirsiniz.[/bold red]\n")
    else:
        console.print("[bold yellow]Klavye Kontrolleri Aktif:[/bold yellow] W/S (İleri/Geri), A/D (Sol/Sağ), R/F (Yukarı/Aşağı), Q/E (Dönüş), Space (Ateş/Buton)\n")

    # Kalibrasyon adımını test için doğrudan geçiyoruz
    answer = "h"

    # Controller Hazırlığı
    controller = JoystickController(
        deadzone=joystick_settings.get("deadzone", 0.08),
        sensitivity=joystick_settings.get("sensitivity", 1.0),
        axis_mapping=configure_axis_mapping(calibration_data, joystick_settings.get("axis_mapping", {})),
        calibration=calibration_data,
    )

    # UDP Network Hazırlığı
    network_settings = config.get("network", DEFAULT_CONFIG["network"])
    udp_connection = UDPConnection(
        target_ip=network_settings.get("target_ip", "192.168.1.100"),
        target_port=network_settings.get("target_port", 5005),
        use_simulation=network_settings.get("use_simulation", False),
        local_port=network_settings.get("local_port"),
    )
    udp_connection.connect()

    # Canlı Dashboard'a Doğrudan Geçiş
    run_live_display(joystick_manager, controller, calibration_data, udp_connection)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            input("\nUygulama hatası. Hata mesajını kopyalamak için Enter'a basın...")
        except (EOFError, KeyboardInterrupt):
            pass