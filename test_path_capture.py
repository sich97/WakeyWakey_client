"""Unit tests for path_capture.PathRecorder (no display needed)."""

import math

from path_capture import CELL_PX, MIN_STEP, PathRecorder

START = (0, 0)


def center(c, r):
    """Center pixel of cell (c, r)."""
    return (c * CELL_PX + CELL_PX // 2, r * CELL_PX + CELL_PX // 2)


class TestStartCellGating:
    def test_press_in_start_cell_starts_recording(self):
        rec = PathRecorder(START)
        x, y = center(0, 0)
        assert rec.press(x, y) is True
        assert rec.recording is True
        assert len(rec.path) == 1
        # First point is the press location in cell units (floats).
        assert rec.path[0] == [x / CELL_PX, y / CELL_PX]

    def test_press_outside_start_cell_does_not_start(self):
        rec = PathRecorder(START)
        x, y = center(3, 2)
        assert rec.press(x, y) is False
        assert rec.recording is False
        assert rec.path == []

    def test_press_on_cell_boundary_is_outside(self):
        # Exactly x=24 is the edge between cell 0 and cell 1 -> not inside (0,0).
        rec = PathRecorder(START)
        assert rec.press(CELL_PX, CELL_PX // 2) is False
        assert rec.path == []

    def test_start_cell_may_be_any_cell(self):
        rec = PathRecorder((2, 1))
        x, y = center(2, 1)
        assert rec.press(x, y) is True
        assert rec.path[0] == [x / CELL_PX, y / CELL_PX]
        assert rec.press(*center(0, 0)) is False

    def test_new_press_in_start_resets_in_progress_path(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        rec.motion(*center(5, 0))
        rec.press(*center(0, 0))
        assert len(rec.path) == 1


class TestThrottling:
    def test_motion_below_threshold_not_recorded(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        # 0.20 cell east of the press: below the 0.25-cell threshold.
        x = center(0, 0)[0] + 0.20 * CELL_PX
        rec.motion(x, center(0, 0)[1])
        assert len(rec.path) == 1

    def test_motion_at_threshold_recorded(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        x = center(0, 0)[0] + MIN_STEP * CELL_PX
        rec.motion(x, center(0, 0)[1])
        assert len(rec.path) == 2
        assert rec.path[1] == [x / CELL_PX, center(0, 0)[1] / CELL_PX]

    def test_throttle_measured_from_last_recorded_point(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        x0, y0 = center(0, 0)
        rec.motion(x0 + 0.3 * CELL_PX, y0)          # recorded (0.3 >= 0.25)
        rec.motion(x0 + 0.45 * CELL_PX, y0)         # 0.15 from last -> dropped
        rec.motion(x0 + 0.71 * CELL_PX, y0)         # 0.41 from last -> recorded
        assert len(rec.path) == 3
        assert math.isclose(rec.path[2][0], 0.5 + 0.71)
        assert math.isclose(rec.path[2][1], 0.5)

    def test_threshold_is_euclidean_not_axis(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        x0, y0 = center(0, 0)
        # 0.18 east + 0.18 south: each axis < 0.25 but Euclidean = 0.2546 >= 0.25
        dx = 0.18 * CELL_PX
        rec.motion(x0 + dx, y0 + dx)
        assert len(rec.path) == 2
        assert math.isclose(
            math.hypot(rec.path[1][0] - 0.5, rec.path[1][1] - 0.5),
            0.18 * math.sqrt(2),
        )

    def test_motion_without_recording_is_ignored(self):
        rec = PathRecorder(START)
        rec.motion(*center(9, 9))
        assert rec.path == []


class TestRelease:
    def test_release_returns_path_and_resets(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        rec.motion(*center(2, 0))
        finished = rec.release()
        assert rec.recording is False
        assert rec.path == []
        assert finished[0] == [0.5, 0.5]
        assert len(finished) >= 2
        assert finished[-1] == [2.5, 0.5]

    def test_release_without_recording_returns_empty(self):
        rec = PathRecorder(START)
        assert rec.release() == []

    def test_press_release_in_start_gives_single_point_path(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        finished = rec.release()
        assert finished == [[0.5, 0.5]]

    def test_recording_can_restart_after_release(self):
        rec = PathRecorder(START)
        rec.press(*center(0, 0))
        rec.release()
        rec.press(*center(0, 0))
        assert rec.recording is True
        assert len(rec.path) == 1
