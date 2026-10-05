"""Terminal tabanlı arayüz modülü.

Rich kütüphanesi kullanarak CMD'de canlı joystick ve kontrol değerlerini gösterir.
"""

import os
import time
import traceback
from datetime import datetime
from communication import ControlPacket
from arduino_terminal_monitor import ArduinoFirmwareModel, RovCanvasView
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


def _tk_card(parent, tk, title):
    outer = tk.Frame(parent, bg="#172432", highlightthickness=1, highlightbackground="#273d4f")
    tk.Label(outer, text=title, bg="#172432", fg="#64dbe8", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=12, pady=(10, 5))
    body = tk.Frame(outer, bg="#111d29")
    body.pack(fill="both", expand=True, padx=1, pady=(0, 1))
    return outer, body


def _tk_value_row(parent, tk, row, caption, variable):
    tk.Label(parent, text=caption, bg="#111d29", fg="#8196a8", font=("Segoe UI", 9), anchor="w").grid(row=row, column=0, sticky="w", padx=(10, 8), pady=5)
    value = tk.Label(parent, textvariable=variable, bg="#111d29", fg="#e5f2f8", font=("Segoe UI", 9, "bold"), anchor="e")
    value.grid(row=row, column=1, sticky="ew", padx=(0, 10), pady=5)
    parent.grid_columnconfigure(1, weight=1)
    return value


def _draw_axis_bar(canvas, value):
    canvas.delete("all")
    width = max(canvas.winfo_width(), 110)
    height = max(canvas.winfo_height(), 16)
    center = width / 2
    canvas.create_rectangle(1, 2, width - 1, height - 2, fill="#172b39", outline="")
    canvas.create_line(center, 3, center, height - 3, fill="#71899a", width=1)
    marker = center + max(-1.0, min(1.0, value)) * (width / 2 - 7)
    canvas.create_oval(marker - 5, height / 2 - 5, marker + 5, height / 2 + 5, fill="#57d4b2", outline="")


def _draw_stick(canvas, x_value, y_value):
    canvas.delete("all")
    width = max(canvas.winfo_width(), 105)
    height = max(canvas.winfo_height(), 95)
    cx, cy = width / 2, height / 2
    radius = min(width, height) * 0.44
    canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline="#355062", width=1)
    canvas.create_oval(cx - radius * 0.52, cy - radius * 0.52, cx + radius * 0.52, cy + radius * 0.52,
                       outline="#294253", width=1, dash=(2, 4))
    canvas.create_line(cx - radius, cy, cx + radius, cy, fill="#355062", dash=(3, 4))
    canvas.create_line(cx, cy - radius, cx, cy + radius, fill="#355062", dash=(3, 4))
    for tick in (-0.5, 0.5):
        tx, ty = cx + tick * radius, cy + tick * radius
        canvas.create_line(tx, cy - 3, tx, cy + 3, fill="#91a9b8")
        canvas.create_line(cx - 3, ty, cx + 3, ty, fill="#91a9b8")
    canvas.create_text(cx + radius - 2, cy - 9, text="X", fill="#6c899a", anchor="e", font=("Segoe UI", 7, "bold"))
    canvas.create_text(cx + 7, cy + radius - 1, text="Y", fill="#6c899a", anchor="w", font=("Segoe UI", 7, "bold"))
    px = cx + max(-1.0, min(1.0, x_value)) * radius
    py = cy + max(-1.0, min(1.0, y_value)) * radius
    canvas.create_line(cx, cy, px, py, fill="#48cbb2", width=2)
    canvas.create_oval(px - 6, py - 6, px + 6, py + 6, fill="#c5fff0", outline="#48cbb2", width=2)


def run_live_display(joystick_manager, controller, calibration_data, udp_connection):
    """Tk dashboard; controller, packet format, and UDP architecture stay unchanged."""
    try:
        import tkinter as tk
        from arduino_terminal_monitor import ArduinoFirmwareModel, RovCanvasView

        root = tk.Tk()
    except Exception as exc:
        console.print(f"[yellow]Grafik arayüz açılamadı ({exc}); terminal paneline dönülüyor.[/yellow]")
        _run_rich_fallback(joystick_manager, controller, calibration_data, udp_connection)
        return

    def report_tk_callback_error(exc_type, exc_value, exc_traceback):
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        try:
            from tkinter import messagebox
            messagebox.showerror("ROV arayüz hatası", details)
        except Exception:
            console.print(f"[red]Arayüz hatası:\n{details}[/red]")

    root.report_callback_exception = report_tk_callback_error

    bg = "#0a1420"
    card_bg = "#172432"
    root.title("OBLIVION | ROV CONTROL STATION")
    root.geometry("1280x820")
    root.minsize(900, 590)
    root.configure(bg=bg)
    root.grid_rowconfigure(1, weight=1)
    root.grid_columnconfigure(0, weight=1)

    header = tk.Frame(root, bg="#101d2a", height=60)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    tk.Label(header, text="OBLIVION", bg="#101d2a", fg="#e7f4fa", font=("Segoe UI", 19, "bold")).pack(side="left", padx=(17, 10), pady=9)
    tk.Label(header, text="ROV CONTROL STATION", bg="#101d2a", fg="#5bd8e8", font=("Segoe UI", 9, "bold")).pack(side="left", pady=(19, 0))
    mode_label = tk.Label(header, text="LIVE", bg="#173d3c", fg="#61e1bb", font=("Segoe UI", 9, "bold"), padx=14, pady=6)
    mode_label.pack(side="right", padx=18, pady=12)

    content = tk.Frame(root, bg=bg, padx=9, pady=8)
    content.grid(row=1, column=0, sticky="nsew")
    content.grid_rowconfigure(0, weight=1)
    content.grid_columnconfigure(0, weight=0, minsize=400)
    content.grid_columnconfigure(1, weight=65, minsize=330)
    content.grid_columnconfigure(2, weight=25, minsize=190)

    left_column = tk.Frame(content, bg=bg)
    left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    left_column.configure(width=400)
    left_column.grid_propagate(False)
    left_column.grid_columnconfigure(0, weight=1)
    left_column.grid_rowconfigure(0, weight=3)
    left_column.grid_rowconfigure(1, weight=2)
    status_card, status_body = _tk_card(left_column, tk, "SYSTEM STATUS")
    status_card.grid(row=0, column=0, sticky="nsew", pady=(0, 7))
    status_vars = {key: tk.StringVar(value="—") for key in ("device", "time", "calibration", "target", "mode", "forward", "strafe", "vertical", "yaw")}
    status_widgets = {}
    online_badge = tk.Label(status_body, text="●  FIRMWARE MODEL / RX LOOP", bg="#12352f", fg="#62e1b6", font=("Consolas", 8, "bold"), anchor="w", padx=9, pady=6)
    online_badge.grid(row=0, column=0, columnspan=2, sticky="ew", padx=9, pady=(5, 8))
    for row, (key, caption) in enumerate((
        ("device", "DEVICE"), ("time", "TIME"), ("calibration", "CALIBRATION"),
        ("target", "UDP TARGET"), ("mode", "LINK MODE"),
    ), start=1):
        status_widgets[key] = _tk_value_row(status_body, tk, row, caption, status_vars[key])
    for key, color in (("device", "#64d9e8"), ("time", "#d3a6ff"), ("target", "#e6f4fa"), ("mode", "#c6a0ff")):
        status_widgets[key].configure(fg=color)
    divider = tk.Frame(status_body, bg="#273d4f", height=1)
    divider.grid(row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=6)
    for row, (key, caption) in enumerate((
        ("forward", "FORWARD"), ("strafe", "STRAFE"), ("vertical", "VERTICAL"), ("yaw", "YAW"),
    ), start=7):
        status_widgets[key] = _tk_value_row(status_body, tk, row, caption, status_vars[key])
        status_widgets[key].configure(font=("Consolas", 9, "bold"))
    status_body.grid_rowconfigure(11, weight=1)

    sticks_card, sticks_body = _tk_card(left_column, tk, "STICK POSITIONS")
    sticks_card.grid(row=1, column=0, sticky="nsew")
    sticks_body.grid_rowconfigure(1, weight=1)
    sticks_body.grid_columnconfigure(0, weight=1)
    sticks_body.grid_columnconfigure(1, weight=1)
    tk.Label(sticks_body, text="LEFT", bg="#111d29", fg="#9eb4c1", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, pady=(4, 0))
    tk.Label(sticks_body, text="RIGHT", bg="#111d29", fg="#9eb4c1", font=("Segoe UI", 8, "bold")).grid(row=0, column=1, pady=(4, 0))
    left_stick = tk.Canvas(sticks_body, width=88, height=145, bg="#111d29", highlightthickness=0)
    right_stick = tk.Canvas(sticks_body, width=88, height=145, bg="#111d29", highlightthickness=0)
    left_stick.grid(row=1, column=0, sticky="nsew", padx=3, pady=4)
    right_stick.grid(row=1, column=1, sticky="nsew", padx=3, pady=4)

    vehicle_card, vehicle_body = _tk_card(content, tk, "TOP VIEW")
    vehicle_card.grid(row=0, column=1, sticky="nsew", padx=4)
    vehicle_body.grid_rowconfigure(0, weight=1)
    vehicle_body.grid_columnconfigure(0, weight=1)
    firmware_model = ArduinoFirmwareModel()
    vehicle_view = RovCanvasView(vehicle_body, tk)
    vehicle_view.frame.grid(row=0, column=0, sticky="nsew")

    axes_card, axes_body = _tk_card(content, tk, "JOYSTICK AXES")
    axes_card.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
    axes_body.grid_columnconfigure(0, weight=1)
    axis_rows = {}
    tk.Label(axes_body, text="AXIS", bg="#111d29", fg="#8196a8", font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=11, pady=(7, 3))
    tk.Label(axes_body, text="INPUT       OUTPUT", bg="#111d29", fg="#8196a8", font=("Segoe UI", 8, "bold"), anchor="e").grid(row=0, column=1, sticky="e", padx=11, pady=(7, 3))

    footer = tk.Label(root, text="FIRMWARE VIEW SOFTWARE MODEL", bg="#101d2a", fg="#8196a8", font=("Segoe UI", 8, "bold"), pady=8)
    footer.grid(row=2, column=0, sticky="ew")

    action_names = {"forward": "İleri / Geri", "strafe": "Yanal Sağ / Sol", "vertical": "Yukarı / Aşağı", "yaw": "Dönüş Sağ / Sol"}
    reverse_mapping = {axis: action for action, axis in controller.axis_mapping.items()}
    running = {"value": True}

    def close_window():
        running["value"] = False
        udp_connection.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)

    def refresh():
        if not running["value"]:
            return
        state = joystick_manager.get_state()
        controls = controller.process(state.axes)
        packet = ControlPacket(
            forward=int(controls.forward * 100),
            strafe=int(controls.strafe * 100),
            vertical=int(controls.vertical * 100),
            yaw=int(controls.yaw * 100),
        )
        udp_connection.send(packet)
        firmware_state = firmware_model.receive(packet.format())
        vehicle_view.update(firmware_state)

        now = datetime.now()
        status_vars["device"].set(state.name[:24])
        status_vars["time"].set(now.strftime("%H:%M:%S"))
        status_vars["calibration"].set("CALIBRATED" if calibration_data else "UNCALIBRATED")
        status_vars["target"].set(f"{udp_connection.target_ip}:{udp_connection.target_port}")
        status_vars["mode"].set("SIMULATION" if udp_connection.use_simulation else "REAL HW")
        for key in ("forward", "strafe", "vertical", "yaw"):
            status_vars[key].set(f"{int(getattr(controls, key) * 100):+4d}%")
        for key in ("forward", "strafe", "vertical", "yaw"):
            value = getattr(controls, key)
            status_widgets[key].configure(fg="#57d4b2" if value > 0 else "#ffae64" if value < 0 else "#8ba0ae")
        status_widgets["calibration"].configure(fg="#57d4b2" if calibration_data else "#ffae64")
        online_badge.configure(fg="#62e1b6" if int(now.timestamp() * 2) % 2 else "#36b995")
        mode_label.configure(text="SIMULATION" if udp_connection.use_simulation else "LIVE", bg="#25394a" if udp_connection.use_simulation else "#173d3c", fg="#9fc5d4" if udp_connection.use_simulation else "#61e1bb")

        _draw_stick(left_stick, controls.strafe, controls.forward)
        _draw_stick(right_stick, controls.yaw, controls.vertical)

        for axis_index, raw_value in state.axes.items():
            if axis_index not in axis_rows:
                row = len(axis_rows) + 1
                row_frame = tk.Frame(axes_body, bg="#111d29")
                row_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=9, pady=7)
                row_frame.grid_columnconfigure(0, weight=1)
                name_var, input_var, output_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
                tk.Label(row_frame, textvariable=name_var, bg="#111d29", fg="#d6e4ea", font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=(2, 8))
                bar = tk.Canvas(row_frame, width=125, height=18, bg="#111d29", highlightthickness=0)
                bar.grid(row=1, column=0, sticky="ew", padx=2, pady=(4, 0))
                tk.Label(row_frame, textvariable=input_var, bg="#111d29", fg="#9eb4c1", font=("Consolas", 8)).grid(row=0, column=1, sticky="e")
                tk.Label(row_frame, textvariable=output_var, bg="#111d29", fg="#57d4b2", font=("Consolas", 8, "bold")).grid(row=1, column=1, sticky="e", pady=(4, 0))
                axis_rows[axis_index] = (name_var, input_var, output_var, bar)

            name_var, input_var, output_var, bar = axis_rows[axis_index]
            raw_label = state.axis_labels.get(axis_index, f"A{axis_index}")
            action = reverse_mapping.get(axis_index)
            if action:
                value = getattr(controls, action)
                name_var.set(f"{action_names.get(action, action)}  ({raw_label})")
                output_var.set(f"{int(value * 100):+d}%")
            else:
                value = raw_value
                name_var.set(f"{raw_label}  (A{axis_index})")
                output_var.set("—")
            input_var.set(f"{raw_value:+.2f}")
            _draw_axis_bar(bar, value)

        root.after(50, refresh)

    try:
        refresh()
        # Let Tk render the dashboard before closing the dedicated startup console.
        root.after(1200, _detach_windows_console)
        root.mainloop()
    except KeyboardInterrupt:
        close_window()


def _detach_windows_console():
    """Close the dedicated startup console after the Tk dashboard is ready."""
    if os.name == "nt" and os.environ.get("ROV_CONSOLE_SPAWNED") == "1":
        try:
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass


def _run_rich_fallback(joystick_manager, controller, calibration_data, udp_connection):
    """Keep the existing terminal dashboard available if Tk/Tcl is unavailable."""
    console.clear()
    firmware_model = ArduinoFirmwareModel()
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
                firmware_model.receive(packet.format())
                status_panel, axes_table = get_status_panel(state, control_values, bool(calibration_data), udp_connection, axis_mapping=controller.axis_mapping)
                fpv_panel = get_fpv_sticks_panel(control_values)
                left_column = Table.grid()
                left_column.add_row(status_panel)
                left_column.add_row(fpv_panel)
                side_by_side = Table.grid(padding=2)
                side_by_side.add_column()
                side_by_side.add_column()
                side_by_side.add_row(left_column, axes_table)
                main_content = Table.grid(padding=0)
                main_content.add_row(get_logo_text())
                main_content.add_row(side_by_side)
                live.update(main_content)
                time.sleep(0.05)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Sistem kapatılıyor...[/bold yellow]")
