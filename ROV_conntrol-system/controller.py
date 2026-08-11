import math

from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class ControlOutput:
    forward: float
    strafe: float
    vertical: float
    yaw: float

class JoystickController:
    def __init__(self, deadzone: float = 0.08, sensitivity: float = 1.0, axis_mapping: Optional[Dict[str, int]] = None, calibration: Optional[Dict[str, Dict[str, float]]] = None):
        self.deadzone = max(0.0, min(deadzone, 0.3))
        self.sensitivity = max(0.1, min(sensitivity, 2.0))
        self.axis_mapping = axis_mapping or {"forward": 1, "strafe": 0, "vertical": 3, "yaw": 2}
        self.calibration = calibration or {}

    def process(self, raw_axes: Dict[int, float]) -> ControlOutput:
        return ControlOutput(
            forward=self._apply_axis(raw_axes, "forward"),
            strafe=self._apply_axis(raw_axes, "strafe"),
            vertical=self._apply_axis(raw_axes, "vertical"),
            yaw=self._apply_axis(raw_axes, "yaw"),
        )

    def _apply_axis(self, raw_axes: Dict[int, float], action: str) -> float:
        axis_index = self.axis_mapping.get(action, DEFAULT_AXIS_MAPPING[action])
        raw_value = raw_axes.get(axis_index, 0.0)
        calibrated = self._calibrate_axis(action, raw_value)
        normalized = self._normalize(calibrated)
        return self._apply_sensitivity(normalized)

    def _calibrate_axis(self, action: str, raw_value: float) -> float:
        calibration = self.calibration.get(action)
        if not calibration:
            return raw_value

        center = float(calibration.get("center", 0.0))
        min_value = float(calibration.get("min", -1.0))
        max_value = float(calibration.get("max", 1.0))
        """Oblivion"""
        if raw_value < center:
            denom = center - min_value
            if denom <= 0:
                return raw_value
            return max(-1.0, min(0.0, (raw_value - center) / denom))

        denom = max_value - center
        if denom <= 0:
            return raw_value
        return max(0.0, min(1.0, (raw_value - center) / denom))

    def _normalize(self, value: float) -> float:
        if abs(value) <= self.deadzone:
            return 0.0
        sign = math.copysign(1.0, value)
        scaled = (abs(value) - self.deadzone) / (1.0 - self.deadzone)
        return max(-1.0, min(sign * scaled, 1.0))

    def _apply_sensitivity(self, value: float) -> float:
        return max(-1.0, min(value * self.sensitivity, 1.0))

DEFAULT_AXIS_MAPPING = {"forward": 1, "strafe": 0, "vertical": 3, "yaw": 2}
