"""Oblivion - ROV Ground Control Station Main Module"""
import json
import os
import subprocess
import sys
import time

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
        "target_ip": "192.168.1.100",
        "target_port": 5005,
        "use_simulation": False,
        "local_port": None
    }
}

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
    
    # Joystick Bağlantı Bekleme
    joystick_manager = None
    while joystick_manager is None:
        try:
            joystick_manager = JoystickManager()
        except JoystickError:
            console.clear()
            console.print(Panel("[bold yellow]⏳ Joystick bekleniyor... Lütfen bir gamepad bağlayın.[/bold yellow]", border_style="yellow"))
            time.sleep(1.5)

    state = joystick_manager.get_state()
    config = load_config()
    joystick_settings = config.get("joystick", DEFAULT_CONFIG["joystick"])
    calibration_data = joystick_settings.get("calibration", {})

    # Kalibrasyon Sorgusu
    console.clear()
    console.print(get_logo_text())
    console.print(f"[bold cyan]Algılanan Cihaz:[/bold cyan] [bright_green]{state.name}[/bright_green]\n")
    
    if calibration_data:
        console.print("[green]Mevcut kalibrasyon verisi yüklendi.[/green]")
    else:
        console.print("[yellow]Henüz yapılmış bir kalibrasyon bulunamadı.[/yellow]")

    try:
        answer = input("\nYeniden kalibrasyon yapmak istiyor musunuz? (e/h): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        answer = "h"

    if answer in ["e", "evet", "y", "yes"]:
        calibration_data = run_calibration(joystick_manager, state)
        joystick_settings["calibration"] = calibration_data
        joystick_settings["axis_mapping"] = configure_axis_mapping(calibration_data, joystick_settings.get("axis_mapping", {}))
        config["joystick"] = joystick_settings
        save_config(config)

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
    main()