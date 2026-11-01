"""Deterministic animation values for the native robot face.

This module has no Qt, sensor, or device dependency.  The UI owns the timer and
asks this controller for a frame using elapsed monotonic time.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AnimationFrame:
    eye_offset_x: float = 0.0
    eye_offset_y: float = 0.0
    eye_openness: float = 1.0
    mouth_phase: float = 0.0
    show_exclamation: bool = False
    direction: int = 0
    air_wave_side: int = 0


class RobotAnimationController:
    """Calculate one lightweight animation frame for a display expression."""

    EXPRESSIONS = frozenset((
        'waiting', 'monitoring', 'normal', 'detected',
        'comfortable', 'moving', 'purifying',
    ))

    def __init__(self, expression='waiting'):
        self.expression = 'waiting'
        self.set_expression(expression)

    def set_expression(self, expression):
        if expression not in self.EXPRESSIONS:
            expression = 'monitoring'
        changed = expression != self.expression
        self.expression = expression
        return changed

    def frame_at(self, elapsed):
        """Return drawing parameters for seconds elapsed in the current state."""
        elapsed = max(0.0, float(elapsed))
        if self.expression == 'monitoring':
            return AnimationFrame(eye_offset_x=7.0 * math.sin(elapsed * math.pi / 1.6))
        if self.expression == 'normal':
            return AnimationFrame(eye_openness=self._blink_openness(elapsed))
        if self.expression == 'detected':
            return AnimationFrame(show_exclamation=(elapsed % 1.6) < 0.95)
        if self.expression == 'comfortable':
            return AnimationFrame(eye_offset_y=3.0 * math.sin(elapsed * math.pi / 1.8))
        if self.expression == 'moving':
            direction = -1 if int(elapsed / 1.1) % 2 == 0 else 1
            return AnimationFrame(eye_offset_x=5.0 * direction, direction=direction)
        if self.expression == 'purifying':
            side = -1 if int(elapsed / 0.9) % 2 == 0 else 1
            return AnimationFrame(mouth_phase=elapsed * 5.0, air_wave_side=side)
        if self.expression == 'waiting':
            return AnimationFrame(mouth_phase=elapsed * 4.0)
        return AnimationFrame()

    @staticmethod
    def _blink_openness(elapsed):
        # A 280 ms blink every 2.8 seconds: open -> closed -> open.
        phase = elapsed % 2.8
        if phase >= 0.28:
            return 1.0
        return max(0.08, abs(phase - 0.14) / 0.14)
