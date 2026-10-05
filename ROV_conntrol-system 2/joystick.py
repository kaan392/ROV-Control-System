import logging
import os
import sys
from io import StringIO

# Pygame splash mesajını gizle
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = StringIO()
sys.stderr = StringIO()

import pygame

sys.stdout = old_stdout
sys.stderr = old_stderr

AXIS_LABELS = ["X", "Y", "RX", "RY", "Z", "RZ", "Throttle", "Rudder"]

class JoystickError(Exception):
    pass

class JoystickState:
    def __init__(self, name, joystick_id, axes, axis_labels, buttons, hats):
        self.name = name
        self.id = joystick_id
        self.axes = axes
        self.axis_labels = axis_labels
        self.buttons = buttons
        self.hats = hats

class JoystickManager:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self._detect_joystick()

    def _detect_joystick(self):
        joystick_count = pygame.joystick.get_count()
        if joystick_count < 1:
            raise JoystickError("Hiç joystick bulunamadı.")

        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        logging.info("Joystick algılandı: %s", self.joystick.get_name())

    def get_state(self):
        if self.joystick is None:
            raise JoystickError("Joystick başlatılmadı.")

        pygame.event.pump()

        axes = {}
        axis_labels = {}
        axis_count = self.joystick.get_numaxes()
        for index in range(axis_count):
            label = AXIS_LABELS[index] if index < len(AXIS_LABELS) else f"A{index}"
            value = float(self.joystick.get_axis(index))
            axes[index] = value
            axis_labels[index] = label

        buttons = {}
        button_count = self.joystick.get_numbuttons()
        for index in range(button_count):
            buttons[index] = bool(self.joystick.get_button(index))

        hats = {}
        hat_count = self.joystick.get_numhats()
        for index in range(hat_count):
            hats[index] = self.joystick.get_hat(index)

        return JoystickState(
            name=self.joystick.get_name(),
            joystick_id=self.joystick.get_id(),
            axes=axes,
            axis_labels=axis_labels,
            buttons=buttons,
            hats=hats,
        )

    @staticmethod
    def is_joystick_available():
        pygame.init()
        pygame.joystick.init()
        return pygame.joystick.get_count() > 0
    
"""Oblivion"""