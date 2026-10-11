"""
path_capture.py — pure path-capture logic, factorable from Tk event handlers.

PathRecorder takes raw canvas points (pixels, canvas-relative event.x/y)
and maintains the recorded path as floats in cell units:
  - start-cell gating: recording begins only on a press inside the start cell
  - throttling: a point is appended only when >= min_step (0.25 cell) away
    from the last recorded point
  - release handling: release stops recording and returns the finished path
"""

import math

CELL_PX = 24
MIN_STEP = 0.25


class PathRecorder:
    def __init__(self, start_cell, cell_px=CELL_PX, min_step=MIN_STEP):
        self.start_cell = start_cell
        self.cell_px = cell_px
        self.min_step = min_step
        self.recording = False
        self.path = []

    def _to_cell(self, x, y):
        return (x / self.cell_px, y / self.cell_px)

    def press(self, x, y):
        """Canvas press (event.x, event.y). Begin recording if in start cell.

        Returns True if recording started, else False (caller shows the
        'start in the green cell' hint).
        """
        c, r = self._to_cell(x, y)
        c0, r0 = self.start_cell
        if c0 <= c < c0 + 1 and r0 <= r < r0 + 1:
            self.recording = True
            self.path = [[c, r]]
            return True
        self.recording = False
        self.path = []
        return False

    def motion(self, x, y):
        """Canvas motion with button 1 held. Appends when far enough."""
        if not self.recording:
            return
        c, r = self._to_cell(x, y)
        last_c, last_r = self.path[-1]
        if math.hypot(c - last_c, r - last_r) >= self.min_step:
            self.path.append([c, r])

    def release(self):
        """Button 1 released. Stops recording; returns the recorded path
        (list of [c, r] float pairs in cell units). Recording state resets."""
        self.recording = False
        finished, self.path = self.path, []
        return finished

    def clear(self):
        """Drop the in-progress path (used after a failed exit attempt)."""
        self.path = []
