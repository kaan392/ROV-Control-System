"""Arduino-side firmware model plus a scalable ROV drawing for the Tk dashboard."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

WATCHDOG_SECONDS = 1.5
DEADZONE = 3
INVERSION = (-1, -1, 1, 1, -1, -1)


def _clamp(value: int) -> int:
    return max(-100, min(100, value))


def _extract(packet: str, key: str) -> int:
    match = re.search(rf"{key}[:=\s]*([+-]?\d+)", packet)
    return _clamp(int(match.group(1))) if match else 0


def calculate_outputs(packet: str) -> tuple[tuple[int, ...], bool]:
    """Mirror the supplied firmware's packet parser, mixer, and inversions."""
    if "STOP" in packet or "EMERGENCY" in packet:
        return (0, 0, 0, 0, 0, 0), True

    forward, strafe, vertical, yaw = (_extract(packet, key) for key in "FSVY")
    forward, strafe, vertical, yaw = (
        0 if -DEADZONE <= value <= DEADZONE else value
        for value in (forward, strafe, vertical, yaw)
    )
    values = [forward, forward, 0, 0, vertical, vertical]
    if yaw > 0:
        values[2] = yaw
    elif yaw < 0:
        values[3] = -yaw
    if strafe and not forward and not yaw:
        # After firmware direction inversion: right => M1/M3 positive;
        # left => M2/M4 positive. Other mixer behavior stays as supplied.
        values[0], values[1], values[2], values[3] = -strafe, strafe, strafe, -strafe
    return tuple(_clamp(value * invert) for value, invert in zip(values, INVERSION)), False


def percent_to_pwm(percent: int) -> int:
    return 1000 + (_clamp(percent) + 100) * 1000 // 200


@dataclass(frozen=True)
class FirmwareSnapshot:
    outputs: tuple[int, ...]
    emergency_stop: bool
    watchdog: str
    packet_age_ms: int | None
    last_packet: str


class ArduinoFirmwareModel:
    """In-process model updated from the command packet sent by the PC."""

    def __init__(self) -> None:
        self.outputs = (0, 0, 0, 0, 0, 0)
        self.emergency_stop = False
        self.last_rx: float | None = None
        self.last_packet = ""

    def receive(self, packet: str, now: float | None = None) -> FirmwareSnapshot:
        now = time.monotonic() if now is None else now
        self.last_packet = packet
        self.outputs, self.emergency_stop = calculate_outputs(packet)
        self.last_rx = now
        return self.snapshot(now)

    def snapshot(self, now: float | None = None) -> FirmwareSnapshot:
        now = time.monotonic() if now is None else now
        age = None if self.last_rx is None else now - self.last_rx
        if age is not None and age > WATCHDOG_SECONDS:
            self.outputs = (0, 0, 0, 0, 0, 0)
            self.emergency_stop = False
            watchdog = "TIMEOUT → NEUTRAL"
        elif age is None:
            watchdog = "WAITING"
        else:
            watchdog = "OK"
        return FirmwareSnapshot(
            self.outputs,
            self.emergency_stop,
            watchdog,
            None if age is None else int(age * 1000),
            self.last_packet,
        )


class RovCanvasView:
    """Responsive H10 pressure-tube plan view, embedded in the main UI."""

    MOTORS = (
        ("M1", -100, 156),
        ("M2", 100, 156),
        ("M3", -100, -156),
        ("M4", 100, -156),
        ("M5", -68, 0),
        ("M6", 68, 0),
    )
    BG = "#091521"
    MUTED = "#8196a8"
    CYAN = "#5bd8e8"

    @staticmethod
    def _motor_fields(entry):
        """Accept both (id, x, y) and (id, label, x, y) motor layouts."""
        if len(entry) == 3:
            motor_id, mx, my = entry
            return motor_id, motor_id, mx, my
        if len(entry) == 4:
            return entry
        raise ValueError(f"Motor kaydı 3 veya 4 alan içermeli: {entry!r}")

    def __init__(self, parent, tk_module) -> None:
        self.tk = tk_module
        self.frame = tk_module.Frame(parent, bg=self.BG)
        self.canvas = tk_module.Canvas(self.frame, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._draw_scene)
        self._last_state = None
        self._scene_size = None
        self._rotor_phases = [0.0] * len(self.MOTORS)
        self._last_rotation_update = None

    def _draw_scene(self, event=None) -> None:
        canvas = self.canvas
        width = max(canvas.winfo_width(), 300)
        height = max(canvas.winfo_height(), 300)
        size = (width, height)
        if size == self._scene_size:
            return
        self._scene_size = size
        canvas.delete("scene")
        w, h = width, height
        scene_height = max(240, h - 64)
        scale = min(w / 460, scene_height / 580)
        cx, cy = w / 2, scene_height / 2 + 4 * scale

        def xy(x, y):
            return cx + x * scale, cy + y * scale

        def line(x1, y1, x2, y2, **kwargs):
            a = xy(x1, y1)
            b = xy(x2, y2)
            canvas.create_line(*a, *b, tags="scene", **kwargs)

        def text(x, y, label, *, size=9, color=None, bold=False):
            px, py = xy(x, y)
            canvas.create_text(
                px, py, text=label, fill=color or self.MUTED,
                font=("Segoe UI", max(7, int(size * scale)), "bold" if bold else "normal"),
                tags="scene",
            )

        text(0, -254, "FRONT", size=9, color=self.CYAN, bold=True)
        line(0, -240, 0, -213, fill=self.CYAN, width=max(1, int(scale * 2)), arrow="last")

        # Four thrusters angle diagonally outward from the pressure tube.
        for side in (-1, 1):
            line(side * 48, -104, side * 100, -156, fill="#507489", width=max(5, int(9 * scale)), capstyle=self.tk.ROUND)
            line(side * 48, 104, side * 100, 156, fill="#507489", width=max(5, int(9 * scale)), capstyle=self.tk.ROUND)
        # Two vertical thrusters flank the central pressure tube.
        line(-57, 0, -78, 0, fill="#507489", width=max(5, int(9 * scale)), capstyle=self.tk.ROUND)
        line(57, 0, 78, 0, fill="#507489", width=max(5, int(9 * scale)), capstyle=self.tk.ROUND)

        # H10 is shown as a slim cylindrical capsule, not a wide rounded hull.
        x1, y1 = xy(-57, -188)
        x2, y2 = xy(57, 188)
        canvas.create_oval(x1, y1, x2, y2, fill="#142f40", outline=self.CYAN, width=max(2, int(3 * scale)), tags="scene")
        for seam_y in (-120, 120):
            canvas.create_arc(*xy(-47, seam_y - 13), *xy(47, seam_y + 13), start=0, extent=180,
                              outline="#47788b", width=max(1, int(2 * scale)), style="arc", tags="scene")
        text(0, 215, "REAR", size=9, color=self.CYAN, bold=True)

        # Motor pods and labels remain in the correct firmware locations.
        for entry in self.MOTORS:
            motor_id, name, mx, my = self._motor_fields(entry)
            px, py = xy(mx, my)
            radius = 26 * scale
            if my != 0:
                mount_points = []
                for corner in range(4):
                    theta = math.pi / 4 + corner * math.pi / 2
                    mount_points.extend((px + math.cos(theta) * 34 * scale, py + math.sin(theta) * 34 * scale))
                canvas.create_polygon(*mount_points, fill="#142633", outline="#527083", width=max(1, int(2 * scale)), tags="scene")
            canvas.create_oval(px - radius, py - radius, px + radius, py + radius,
                               fill="#0d1d29", outline="#527083", width=max(1, int(2 * scale)), tags="scene")
            label_x = mx + (-37 if mx < 0 else 37 if mx > 0 else 0)
            label_y = my - 34 if my < 0 else my + 37 if my > 0 else my - 43
            text(label_x, label_y, name, size=7, color="#bdcdd6", bold=True)

        if self._last_state is not None:
            self.update(self._last_state)

    def update(self, state: FirmwareSnapshot) -> None:
        self._last_state = state
        canvas = self.canvas
        if canvas.winfo_width() <= 1 or canvas.winfo_height() <= 1:
            return
        width, height = canvas.winfo_width(), canvas.winfo_height()
        scene_height = max(240, height - 64)
        scale = min(width / 460, scene_height / 580)
        cx, cy = width / 2, scene_height / 2 + 4 * scale
        canvas.delete("dynamic")
        now = time.monotonic()
        elapsed = 0.0 if self._last_rotation_update is None else min(0.1, max(0.0, now - self._last_rotation_update))
        self._last_rotation_update = now

        for index, entry in enumerate(self.MOTORS):
            motor_id, _name, mx, my = self._motor_fields(entry)
            value = state.outputs[index]
            x, y = cx + mx * scale, cy + my * scale
            radius = 27 * scale
            color = "#42d6ad" if value > DEADZONE else "#ffae64" if value < -DEADZONE else "#8196a8"

            # Keep neutral blades still, and integrate a deliberately slow rotor
            # phase so changing joystick values never causes an angle jump.
            if abs(value) > DEADZONE:
                speed_rps = 0.02 + 1.35 * (abs(value) / 100.0) ** 2
                direction = 1 if value > 0 else -1
                self._rotor_phases[index] = (
                    self._rotor_phases[index] + elapsed * speed_rps * 2 * math.pi * direction
                ) % (2 * math.pi)
            phase = self._rotor_phases[index]
            # Original swept three-blade silhouette, with a compact center cap.
            for blade in range(3):
                theta = phase + blade * (2 * math.pi / 3)
                ux, uy = math.cos(theta), math.sin(theta)
                vx, vy = -uy, ux
                root_r, tip_r = radius * 0.20, radius * 0.96
                half_width = radius * 0.115
                sweep = radius * 0.18
                points = (
                    (x + ux * root_r - vx * half_width, y + uy * root_r - vy * half_width),
                    (x + ux * (tip_r - sweep) - vx * half_width * 0.45, y + uy * (tip_r - sweep) - vy * half_width * 0.45),
                    (x + ux * tip_r + vx * half_width * 0.35, y + uy * tip_r + vy * half_width * 0.35),
                    (x + ux * (tip_r - radius * 0.18) + vx * half_width, y + uy * (tip_r - radius * 0.18) + vy * half_width),
                    (x + ux * root_r + vx * half_width, y + uy * root_r + vy * half_width),
                )
                flattened = [coordinate for point in points for coordinate in point]
                canvas.create_polygon(*flattened, fill=color, outline="#d6e7ed", width=max(1, int(scale)), tags="dynamic")
            canvas.create_oval(x - 5 * scale, y - 5 * scale, x + 5 * scale, y + 5 * scale,
                               fill="#eaf8ff", outline="", tags="dynamic")
            canvas.create_text(x, y + 32 * scale, text=f"{value:+d}%", fill=color,
                               font=("Segoe UI", max(8, int(10 * scale)), "bold"), tags="dynamic")

        footer_y = height - 8
        age = "--" if state.packet_age_ms is None else f"{state.packet_age_ms} ms"
        canvas.create_text(14, height - 49, anchor="w", text=f"WATCHDOG {state.watchdog}   •   RX {age}",
                           fill="#42d6ad" if state.watchdog == "OK" else "#ffae64",
                           font=("Segoe UI", max(7, int(8 * scale)), "bold"), tags="dynamic")
        for index, entry in enumerate(self.MOTORS):
            motor_id, _name, _mx, _my = self._motor_fields(entry)
            value = state.outputs[index]
            pwm = 1000 + (_clamp(value) + 100) * 1000 // 200
            column = index % 3
            row = index // 3
            label_x = width * (column + 0.5) / 3
            label_y = height - 31 if row == 0 else footer_y
            canvas.create_text(label_x, label_y, anchor="center", text=f"{motor_id} {pwm} µs",
                               fill="#d1e0e8", font=("Segoe UI", max(7, int(8 * scale))), tags="dynamic")
