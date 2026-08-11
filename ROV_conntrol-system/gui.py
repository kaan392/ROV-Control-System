"""Terminal tabanlı arayüz modülü.

Rich kütüphanesi kullanarak CMD'de canlı joystick ve kontrol değerlerini gösterir.
"""

import os
import time
from datetime import datetime
from communication import ControlPacket
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

def get_logo_text():
    """OBLIVION ASCII"""
    logo_left = Text(
        "\n"
        "   ██████╗ ██████╗ ██╗     ██╗██╗   ██╗██╗ ██████╗ ███╗   ██╗  \n"
        "  ██╔═══██╗██╔══██╗██║     ██║██║   ██║██║██╔═══██╗████╗  ██║  \n"
        "  ██║   ██║██████╔╝██║     ██║██║   ██║██║██║   ██║██╔██╗ ██║  \n"
        "  ██║   ██║██╔══██╗██║     ██║╚██╗ ██╔╝██║██║   ██║██║╚██╗██║  \n"
        "  ╚██████╔╝██████╔╝███████╗██║ ╚████╔╝ ██║╚██████╔╝██║ ╚████║  \n"
        "   ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝  \n",
        style="bold yellow",
    )
    
    logo_right = Text(
        "\n"
        "  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n"
        "  ░                                             ░\n"
        "  ░    ═══ 🤖 ROV CONTROL STATION 🤖 ═══        ░\n"
        "  ░                                             ░\n"
        "  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n",
        style="bold magenta",
    )
    
    dual_logo = Table.grid(padding=1)
    dual_logo.add_row(logo_left, logo_right)
    return dual_logo


def show_waiting_screen(waiting_message=""):
    with Live(console=console, refresh_per_second=2, auto_refresh=True) as live:
        while True:
            waiting_panel = Panel(
                f"[bold yellow]⏳ {waiting_message}[/bold yellow]\n[dim cyan]⟐ Waiting for connection ⟐[/dim cyan]",
                title="[bold]~ SYSTEM WAITING ~[/bold]",
                border_style="yellow",
                padding=(2, 2),
            )
            
            main_content = Table.grid(padding=1)
            main_content.add_row(get_logo_text())
            main_content.add_row(waiting_panel)
            
            live.update(main_content)
            time.sleep(2)


def get_fpv_sticks_panel(control_values):
    """Kare & Hassas 2D Stick Position göstergesi."""
    
    def render_square_grid(x_val, y_val, reverse_y=False):
        # Kare görünüm için 13 sütun x 7 satır
        COLS = 13
        ROWS = 7
        CENTER_COL = 6
        CENTER_ROW = 3
        
        effective_y = -y_val if reverse_y else y_val
        
        col = max(0, min(COLS - 1, int(round((x_val + 1.0) * CENTER_COL))))
        row = max(0, min(ROWS - 1, int(round((1.0 - effective_y) * CENTER_ROW))))
        
        rendered_text = Text()
        for r in range(ROWS):
            for c in range(COLS):
                if r == row and c == col:
                    rendered_text.append("⊕", style="bold bright_green")
                elif r == CENTER_ROW and c == CENTER_COL:
                    rendered_text.append("┼", style="dim cyan")
                elif r == CENTER_ROW:
                    rendered_text.append("─", style="dim cyan")
                elif c == CENTER_COL:
                    rendered_text.append("│", style="dim cyan")
                else:
                    rendered_text.append("·", style="dim")
            if r < ROWS - 1:
                rendered_text.append("\n")
        return rendered_text

    # Sol Stick: Strafe (X) & Forward (Y -> Visual Reverse)
    left_stick = render_square_grid(control_values.strafe, control_values.forward, reverse_y=True)
    # Sağ Stick: Yaw (X) & Vertical (Y -> Visual Reverse)
    right_stick = render_square_grid(control_values.yaw, control_values.vertical, reverse_y=True)

    grid_table = Table.grid(padding=1)
    grid_table.add_column(justify="center")
    grid_table.add_column(justify="center")
    
    left_box = Panel(left_stick, title="[bold cyan]LEFT[/bold cyan]", border_style="cyan", padding=(0, 1))
    right_box = Panel(right_stick, title="[bold magenta]RIGHT[/bold magenta]", border_style="magenta", padding=(0, 1))

    grid_table.add_row(left_box, right_box)

    fpv_panel = Panel(
        grid_table,
        title="[bold yellow]~ STICK POSITIONS ~[/bold yellow]",
        border_style="yellow",
        padding=(0, 1),
        width=46
    )
    return fpv_panel


def get_status_panel(state, control_values, calibration_status, udp_connection, axis_mapping=None):
    ACTION_NAMES = {
        "forward": "İleri / Geri",
        "strafe": "Yanal Sağ / Sol",
        "vertical": "Yukarı / Aşağı",
        "yaw": "Dönüş Sağ / Sol"
    }
    
    reverse_mapping = {}
    action_by_axis = {}
    if axis_mapping:
        for action, axis_idx in axis_mapping.items():
            reverse_mapping[axis_idx] = ACTION_NAMES.get(action, action)
            action_by_axis[axis_idx] = action

    # Status Panel Metni
    device_info = Text()
    device_info.append(" Device : ", style="bold cyan")
    device_info.append(f"{state.name[:20]}\n", style="bright_cyan")
    
    device_info.append(" Time   : ", style="bold cyan")
    device_info.append(f"{datetime.now().strftime('%H:%M:%S')}\n", style="bright_cyan")
    
    device_info.append(" Status : ", style="bold cyan")
    if calibration_status:
        device_info.append("CALIBRATED\n", style="bold green")
    else:
        device_info.append("UNCALIBRATED\n", style="bold yellow")

    device_info.append(" Target : ", style="bold cyan")
    device_info.append(f"{udp_connection.target_ip}:{udp_connection.target_port}\n", style="bright_white")
    
    device_info.append(" Mode   : ", style="bold cyan")
    mode_text = "SIMULATION" if udp_connection.use_simulation else "REAL HW"
    device_info.append(f"{mode_text}\n", style="magenta")

    # PWM çıkış değerleri
    f_val = f"{int(control_values.forward*100):+4d}"
    s_val = f"{int(control_values.strafe*100):+4d}"
    v_val = f"{int(control_values.vertical*100):+4d}"
    y_val = f"{int(control_values.yaw*100):+4d}"
    
    device_info.append(" Out PWM: ", style="bold cyan")
    device_info.append(f"F:{f_val} S:{s_val} V:{v_val} Y:{y_val}", style="yellow")

    status_panel = Panel(
        device_info,
        title="[bold blue]~ SYSTEM STATUS ~[/bold blue]",
        border_style="blue",
        padding=(0, 2),
        width=46
    )

    # Joystick Eksen Tablosu
    axes_table = Table(
        title="[bold magenta]~ JOYSTICK AXES ~[/bold magenta]", 
        show_header=True, 
        header_style="bold magenta", 
        border_style="magenta",
        title_justify="center"
    )
    axes_table.add_column("[cyan]Axis[/cyan]", style="cyan", width=22, no_wrap=True)
    axes_table.add_column("[yellow]Value[/yellow]", justify="right", style="yellow", width=7, no_wrap=True)
    axes_table.add_column("[bright_yellow]% PWM[/bright_yellow]", justify="right", style="bold bright_yellow", width=8, no_wrap=True)
    axes_table.add_column("[green]Status Bar[/green]", justify="center", style="green", width=22, no_wrap=True)

    for axis_index, raw_value in state.axes.items():
        raw_label = state.axis_labels.get(axis_index, f"A{axis_index}")
        
        if axis_index in reverse_mapping:
            display_label = f"{reverse_mapping[axis_index]} ({raw_label})"
            action = action_by_axis[axis_index]
            calc_val = getattr(control_values, action)
            pct_val = int(calc_val * 100)
            disp_value = calc_val
        else:
            display_label = f"{raw_label} ({axis_index})"
            pct_val = int(raw_value * 100)
            disp_value = raw_value
        
        pct_str = f"%{pct_val:+d}"

        # Status Bar çizimi
        pos = int(round((disp_value + 1.0) * 10))
        pos = max(0, min(20, pos))

        if pos < 10:
            bar = "░" * pos + "█" * (10 - pos) + "│" + "░" * 10
        elif pos > 10:
            bar = "░" * 10 + "│" + "█" * (pos - 10) + "░" * (20 - pos)
        else:
            bar = "░" * 10 + "│" + "░" * 10

        axes_table.add_row(display_label, f"{disp_value:+.2f}", pct_str, bar)

    return status_panel, axes_table


def run_live_display(joystick_manager, controller, calibration_data, udp_connection):
    console.clear()
    
    with Live(console=console, refresh_per_second=10, auto_refresh=True) as live:
        try:
            while True:
                state = joystick_manager.get_state()
                control_values = controller.process(state.axes)
                packet = ControlPacket(
                    forward=int(control_values.forward * 100),
                    strafe=int(control_values.strafe * 100),
                    vertical=int(control_values.vertical * 100),
                    yaw=int(control_values.yaw * 100),
                )
                udp_connection.send(packet)

                status_panel, axes_table = get_status_panel(
                    state, 
                    control_values, 
                    bool(calibration_data),
                    udp_connection,
                    axis_mapping=controller.axis_mapping
                )

                fpv_panel = get_fpv_sticks_panel(control_values)

                # Sol Taraf Grid (System Status + Stick Positions)
                left_column = Table.grid()
                left_column.add_row(status_panel)
                left_column.add_row(fpv_panel)

                # Yan yana hizalama gridi
                side_by_side = Table.grid(padding=2)
                side_by_side.add_column()
                side_by_side.add_column()
                side_by_side.add_row(left_column, axes_table)

                # Footer (Üst boşluk azaltıldı)
                footer = Text()
                footer.append("⟐ ~ ", style="bold cyan")
                footer.append("Underwater ROV Command Interface", style="bold yellow")
                footer.append(" ~ ⟐", style="bold cyan")
                
                # Tüm içerik
                main_content = Table.grid(padding=0)
                main_content.add_row(get_logo_text())
                main_content.add_row(side_by_side)
                main_content.add_row(footer)
                
                live.update(main_content)
                time.sleep(0.05)

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Sistem kapatılıyor...[/bold yellow]")