"""
maze_view.py — pure view math for the v2 maze test (no display needed).

Everything here is a plain function of (active test, recorded points):
  point_to_cell / cell_to_pixels : coordinate conversions (cell size 24 px)
  MazeRenderer                   : (test, path, hint) -> list of draw ops
  generate_mock_test             : local sample maze for the mock_test flag

Draw ops (rendered in order by the Tk layer):
  ("bg", w, h)
  ("cell", x0, y0, x1, y1, color)
  ("wall", x0, y0, x1, y1)
  ("path", (x, y), ...)          # canvas-pixel polyline
  ("hint", text)
"""

import hashlib
import json
import random

CELL_PX = 24

_NEIGHBOR = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}
_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def point_to_cell(x, y):
    """Canvas pixels -> float cell coordinates (x/24, y/24)."""
    return (x / CELL_PX, y / CELL_PX)


def cell_to_pixels(c, r):
    """Cell (c, r) -> top-left corner pixel (c*24, r*24)."""
    return (c * CELL_PX, r * CELL_PX)


def cell_center(c, r):
    """Cell (c, r) -> center pixel."""
    return (c * CELL_PX + CELL_PX // 2, r * CELL_PX + CELL_PX // 2)


def point_in_cell(c, r, cell):
    """True when float point (c, r) is inside cell (c0, r0)."""
    c0, r0 = cell
    return c0 <= c < c0 + 1 and r0 <= r < r0 + 1


def path_ends_in_exit(path, exit_cell):
    """Cheap UX hint only: does the recorded path end inside the exit cell?

    This is NOT validation — the server is the only authority on the answer.
    """
    if not path:
        return False
    c, r = path[-1]
    return point_in_cell(c, r, exit_cell)


class MazeRenderer:
    """Pure (test, path_points, hint) -> draw ops. No Tk imports."""

    def __init__(self, cell_px=CELL_PX):
        self.cell_px = cell_px

    def size(self, test):
        """Canvas/window size in pixels, derived from the test."""
        return test["cols"] * self.cell_px, test["rows"] * self.cell_px

    def wall_pixels(self, c, r, side):
        """Wall [c, r, side] -> pixel segment endpoints (x0, y0, x1, y1)."""
        s = self.cell_px
        if side == "N":
            return (c * s, r * s, (c + 1) * s, r * s)
        if side == "S":
            return (c * s, (r + 1) * s, (c + 1) * s, (r + 1) * s)
        if side == "W":
            return (c * s, r * s, c * s, (r + 1) * s)
        if side == "E":
            return ((c + 1) * s, r * s, (c + 1) * s, (r + 1) * s)
        raise ValueError("bad wall side: %r" % side)

    def render(self, test, path_points=None, hint=None):
        """Return the full ordered list of draw ops for one frame."""
        s = self.cell_px
        ops = [("bg", test["cols"] * s, test["rows"] * s)]

        sc, sr = test["start"]
        ops.append(("cell", sc * s, sr * s, (sc + 1) * s, (sr + 1) * s, "green"))
        ec, er = test["exit"]
        ops.append(("cell", ec * s, er * s, (ec + 1) * s, (er + 1) * s, "red"))

        for c, r, side in test["walls"]:
            ops.append(("wall",) + self.wall_pixels(c, r, side))

        if path_points:
            pts = tuple((c * s, r * s) for c, r in path_points)
            if len(pts) >= 2:
                ops.append(("path", pts))

        if hint:
            ops.append(("hint", hint))
        return ops


def _canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("ascii")


def _carve(cols, rows, rng):
    """Randomized DFS (recursive backtracker). Returns { (c,r): set(sides) }."""
    walls = {(c, r): set("NSWE") for c in range(cols) for r in range(rows)}
    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        c, r = stack[-1]
        options = []
        for side, (dc, dr) in _NEIGHBOR.items():
            nc, nr = c + dc, r + dr
            if 0 <= nc < cols and 0 <= nr < rows and (nc, nr) not in visited:
                options.append((side, nc, nr))
        if not options:
            stack.pop()
            continue
        side, nc, nr = rng.choice(options)
        walls[(c, r)].discard(side)
        walls[(nc, nr)].discard(_OPPOSITE[side])
        visited.add((nc, nr))
        stack.append((nc, nr))
    return walls


def generate_mock_test(cols=21, rows=15, min_path_points=10, seed=None):
    """Build a locally-solved, self-consistent sample maze (mock_test mode).

    Same shape as the server's get_test JSON. No network involved; the sig is
    a dev HMAC and never leaves this machine. Deterministic when seeded.
    """
    rng = random.Random(seed)

    carved = _carve(cols, rows, rng)
    walls = []
    for c in range(cols):
        for r in range(rows):
            for side in ("N", "S", "E", "W"):
                if side in carved[(c, r)]:
                    walls.append([c, r, side])

    test = {
        "test_id": "%064x" % rng.getrandbits(256),
        "kind": "maze",
        "cols": cols,
        "rows": rows,
        "start": [0, 0],
        "exit": [cols - 1, rows - 1],
        "walls": walls,
        "min_path_points": min_path_points,
    }
    body = {k: v for k, v in test.items() if k != "sig"}
    sig = hashlib.sha256(b"wakey-mock-dev-key" + _canonical_json(body)).hexdigest()
    test["sig"] = sig
    return test
