"""Unit tests for maze_view: coordinate math, render ops, mock maze gen."""

import json

from maze_view import (
    CELL_PX,
    MazeRenderer,
    cell_center,
    cell_to_pixels,
    generate_mock_test,
    path_ends_in_exit,
    point_in_cell,
    point_to_cell,
)

RENDERER = MazeRenderer()


def small_test(cols=4, rows=3, walls=None):
    if walls is None:
        walls = [[0, 0, "E"], [1, 0, "S"], [2, 1, "N"]]
    return {
        "test_id": "ab" * 32,
        "kind": "maze",
        "cols": cols,
        "rows": rows,
        "start": [0, 0],
        "exit": [cols - 1, rows - 1],
        "walls": walls,
        "min_path_points": 10,
        "sig": "cd" * 32,
    }


class TestCoordinateMath:
    def test_point_to_cell(self):
        assert point_to_cell(0, 0) == (0.0, 0.0)
        assert point_to_cell(24, 48) == (1.0, 2.0)
        assert point_to_cell(12, 36) == (0.5, 1.5)

    def test_cell_to_pixels(self):
        assert cell_to_pixels(0, 0) == (0, 0)
        assert cell_to_pixels(2, 3) == (48, 72)

    def test_cell_center(self):
        assert cell_center(0, 0) == (12, 12)
        assert cell_center(3, 1) == (84, 36)

    def test_cell_pixel_size_is_24(self):
        assert CELL_PX == 24


class TestPointInCell:
    def test_inside(self):
        assert point_in_cell(0.0, 0.0, (0, 0))
        assert point_in_cell(0.99, 0.99, (0, 0))
        assert point_in_cell(1.5, 2.5, (1, 2))

    def test_far_edge_is_outside(self):
        assert not point_in_cell(1.0, 0.5, (0, 0))
        assert not point_in_cell(0.5, 1.0, (0, 0))

    def test_negative_is_outside(self):
        assert not point_in_cell(-0.1, 0.5, (0, 0))


class TestPathEndsInExit:
    def test_ends_in_exit_cell(self):
        assert path_ends_in_exit([[0.5, 0.5], [3.2, 2.7]], (3, 2))

    def test_does_not_end_in_exit_cell(self):
        assert not path_ends_in_exit([[0.5, 0.5], [2.9, 2.99]], (3, 2))

    def test_empty_path(self):
        assert not path_ends_in_exit([], (3, 2))


class TestWallPixels:
    def test_wall_north(self):
        assert RENDERER.wall_pixels(1, 2, "N") == (24, 48, 48, 48)

    def test_wall_south(self):
        assert RENDERER.wall_pixels(1, 2, "S") == (24, 72, 48, 72)

    def test_wall_west(self):
        assert RENDERER.wall_pixels(1, 2, "W") == (24, 48, 24, 72)

    def test_wall_east(self):
        assert RENDERER.wall_pixels(1, 2, "E") == (48, 48, 48, 72)

    def test_bad_side_raises(self):
        try:
            RENDERER.wall_pixels(0, 0, "X")
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestMazeRenderer:
    def test_size_derived_from_test(self):
        assert RENDERER.size(small_test()) == (4 * CELL_PX, 3 * CELL_PX)

    def test_render_order_and_shapes(self):
        test = small_test()
        ops = RENDERER.render(test)
        assert ops[0] == ("bg", 96, 72)
        assert ops[1] == ("cell", 0, 0, 24, 24, "green")          # start [0,0]
        assert ops[2] == ("cell", 72, 48, 96, 72, "red")          # exit [3,2]
        walls = [op for op in ops if op[0] == "wall"]
        assert len(walls) == len(test["walls"])
        assert ("wall", 24, 0, 24, 24) in walls                   # [0,0,"E"]
        assert ("wall", 24, 24, 48, 24) in walls                  # [1,0,"S"]
        assert ("wall", 48, 24, 72, 24) in walls                  # [2,1,"N"]

    def test_render_with_path(self):
        test = small_test()
        path = [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5]]
        ops = RENDERER.render(test, path)
        path_ops = [op for op in ops if op[0] == "path"]
        assert len(path_ops) == 1
        assert path_ops[0][1] == ((12, 12), (36, 12), (36, 36))

    def test_single_point_path_not_drawn(self):
        ops = RENDERER.render(small_test(), [[0.5, 0.5]])
        assert not any(op[0] == "path" for op in ops)

    def test_render_is_pure_function_of_state(self):
        test = small_test()
        path = [[0.5, 0.5], [2.0, 1.0]]
        assert RENDERER.render(test, path, "hint") == RENDERER.render(test, path, "hint")
        assert RENDERER.render(test, path) == RENDERER.render(test, path)

    def test_hint_op(self):
        ops = RENDERER.render(small_test(), None, "Start in the green cell")
        assert ops[-1] == ("hint", "Start in the green cell")


class TestMockMazeGeneration:
    def test_shape_matches_get_test_contract(self):
        test = generate_mock_test(cols=5, rows=4, seed=1)
        assert test["kind"] == "maze"
        assert test["cols"] == 5
        assert test["rows"] == 4
        assert test["start"] == [0, 0]
        assert test["exit"] == [4, 3]
        assert len(test["test_id"]) == 64
        int(test["test_id"], 16)  # 64 hex chars
        assert len(test["sig"]) == 64
        int(test["sig"], 16)
        assert test["min_path_points"] == 10

    def test_seeded_generation_is_deterministic(self):
        assert generate_mock_test(seed=42) == generate_mock_test(seed=42)
        assert generate_mock_test(seed=42) != generate_mock_test(seed=43)

    def test_walls_in_bounds_and_consistent(self):
        test = generate_mock_test(cols=6, rows=5, seed=7)
        wall_set = {(c, r, s) for c, r, s in test["walls"]}
        for c, r, side in wall_set:
            assert 0 <= c < 6
            assert 0 <= r < 5
            assert side in ("N", "S", "E", "W")
            dc, dr = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[side]
            nc, nr = c + dc, r + dr
            opposite = {"N": "S", "S": "N", "E": "W", "W": "E"}[side]
            if 0 <= nc < 6 and 0 <= nr < 5:
                # A wall on one side of a cell is the same wall on the
                # opposite side of the neighbor.
                assert (nc, nr, opposite) in wall_set
            else:
                # Boundary walls exist on the outside edge.
                pass

    def test_maze_is_fully_connected(self):
        """The backtracker carves a spanning tree: every cell reachable."""
        cols, rows, seed = 21, 15, 3
        test = generate_mock_test(cols=cols, rows=rows, seed=seed)
        open_walls = set()
        for c, r, side in test["walls"]:
            open_walls.add((c, r, side))

        neighbors = {
            "N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0),
        }
        seen = {(0, 0)}
        stack = [(0, 0)]
        while stack:
            c, r = stack.pop()
            for side, (dc, dr) in neighbors.items():
                nc, nr = c + dc, r + dr
                if 0 <= nc < cols and 0 <= nr < rows and (nc, nr) not in seen:
                    if (c, r, side) not in open_walls:
                        seen.add((nc, nr))
                        stack.append((nc, nr))
        assert len(seen) == cols * rows

    def test_render_accepts_mock_test(self):
        test = generate_mock_test(cols=6, rows=5, seed=9)
        ops = RENDERER.render(test)
        assert ops[0] == ("bg", 6 * CELL_PX, 5 * CELL_PX)
        assert len([op for op in ops if op[0] == "wall"]) == len(test["walls"])

    def test_min_path_points_parameter(self):
        assert generate_mock_test(min_path_points=42, seed=1)["min_path_points"] == 42
