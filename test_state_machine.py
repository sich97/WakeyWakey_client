"""Headless tests for the client App state machine (fake Tk, no display).

Exercises CONNECTING -> POLLING -> SHOWING_TEST -> SUBMITTING -> RESULT
with a synchronous fake socket layer, plus the mock_test loop.
"""

import client
from maze_view import CELL_PX, generate_mock_test


class FakeCanvas:
    def __init__(self, master, **kw):
        self.master = master
        self.width = kw.get("width", 100)
        self.height = kw.get("height", 100)
        self.bindings = {}
        self.items = []

    def grid(self, **kw):
        pass

    def bind(self, seq, fn):
        self.bindings[seq] = fn

    def delete(self, tag):
        self.items = []

    def create_rectangle(self, *a, **kw):
        self.items.append(("rect", a, kw))
        return len(self.items)

    def create_line(self, *a, **kw):
        self.items.append(("line", a, kw))
        return len(self.items)

    def create_text(self, *a, **kw):
        self.items.append(("text", a, kw))
        return len(self.items)

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height


class FakeToplevel:
    def __init__(self, master):
        self.master = master
        self.destroyed = False

    def title(self, t):
        pass

    def resizable(self, x, y):
        pass

    def geometry(self, g):
        pass

    def attributes(self, *a):
        pass

    def lift(self):
        pass

    def destroy(self):
        self.destroyed = True

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080


class FakeRoot:
    def __init__(self):
        self.pending = []
        self._id = 0

    def after(self, ms, fn):
        self._id += 1
        self.pending.append((ms, fn, self._id))
        return self._id

    def title(self, t):
        pass

    def geometry(self, g):
        pass

    def resizable(self, x, y):
        pass


class SyncThread:
    """Runs the worker inline so the pump below is deterministic."""

    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        self.target()


class FakeEvent:
    def __init__(self, x, y):
        self.x = x
        self.y = y


def pump(root, max_steps=500):
    steps = 0
    while root.pending and steps < max_steps:
        ms, fn, _ = root.pending.pop(0)
        fn()
        steps += 1
    return steps


def install_fakes(monkeypatch):
    monkeypatch.setattr(client.tk, "Canvas", FakeCanvas)
    monkeypatch.setattr(client.tk, "Toplevel", FakeToplevel)
    monkeypatch.setattr(client.threading, "Thread", SyncThread)


def make_fake_protocol(monkeypatch, states, tests, submit_response):
    class FakeProtocol:
        def __init__(self, host, port, timeout=2.0):
            pass

        def connect(self):
            pass

        def close(self):
            pass

        def get_alarm_state(self):
            # Steady state: alarm off once the scripted states run out.
            return states.pop(0) if states else 0

        def get_test(self):
            return tests.pop(0) if tests else None

        def submit_answer(self, test):
            assert "sig" in test
            return submit_response

    monkeypatch.setattr(client, "ProtocolClient", FakeProtocol)


def settings(mock):
    return {"address": "127.0.0.1", "port": 1, "mock_test": mock}


def center(c, r):
    return (c * CELL_PX + CELL_PX // 2, r * CELL_PX + CELL_PX // 2)


def draw_path_to_exit(app, steps=100):
    """Feed press + motion events: straight line from start center to exit
    center. The client never validates walls, so a straight line is legal
    input for exercising the state machine."""
    ec, er = app.test["exit"]
    x0, y0 = center(0, 0)
    x1, y1 = center(ec, er)
    press = app._canvas.bindings["<Button-1>"]
    motion = app._canvas.bindings["<B1-Motion>"]
    press(FakeEvent(x0, y0))
    for i in range(1, steps + 1):
        motion(FakeEvent(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps))
    release = app._canvas.bindings["<ButtonRelease-1>"]
    release(FakeEvent(x1, y1))


def status_text(app):
    texts = [kw["text"] for kind, _a, kw in app._status_canvas.items
             if kind == "text"]
    return " | ".join(texts)


class TestMockLoop:
    def test_mock_renders_and_loops_without_network(self, monkeypatch):
        install_fakes(monkeypatch)
        root = FakeRoot()
        app = client.App(root, settings(mock=True))
        assert app.protocol is None  # never touches the network

        pump(root)  # runs the initial _next_mock
        assert app.state == client.SHOWING_TEST
        assert app._test_window is not None
        assert app._canvas.width == app.test["cols"] * CELL_PX
        assert app._canvas.height == app.test["rows"] * CELL_PX

        draw_path_to_exit(app)
        assert app.state == client.RESULT
        assert "MOCK" in status_text(app)

        pump(root)  # next mock maze
        assert app.state == client.SHOWING_TEST
        assert app.test is not None


class TestStateMachine:
    def test_alarm_off_keeps_polling(self, monkeypatch):
        install_fakes(monkeypatch)
        make_fake_protocol(monkeypatch, states=[0, 0], tests=[],
                           submit_response=("accepted", None))
        root = FakeRoot()
        app = client.App(root, settings(mock=False))
        pump(root, 2)  # connect -> first poll; the poll loop reschedules itself
        assert app.state == client.POLLING
        assert "Alarm off" in status_text(app)
        assert len(root.pending) == 1  # next poll still scheduled

    def test_full_accept_flow(self, monkeypatch):
        install_fakes(monkeypatch)
        test = generate_mock_test(cols=9, rows=7, seed=11)
        make_fake_protocol(monkeypatch, states=[1], tests=[test],
                           submit_response=("accepted", None))
        root = FakeRoot()
        app = client.App(root, settings(mock=False))
        pump(root)
        assert app.state == client.SHOWING_TEST
        assert app.test["test_id"] == test["test_id"]
        # Window size is derived from the test.
        assert app._canvas.width == 9 * CELL_PX
        assert app._canvas.height == 7 * CELL_PX

        draw_path_to_exit(app)
        pump(root, 1)  # submit response -> RESULT
        assert app.state == client.RESULT
        assert "ACCEPTED" in status_text(app)
        pump(root, 2)  # poll -> response -> POLLING
        assert app.state == client.POLLING
        assert "Alarm off" in status_text(app)

    def test_rejected_flow_shows_reason(self, monkeypatch):
        install_fakes(monkeypatch)
        test = generate_mock_test(cols=9, rows=7, seed=12)
        make_fake_protocol(monkeypatch, states=[1, 0], tests=[test],
                           submit_response=("rejected", "crossed_wall"))
        root = FakeRoot()
        app = client.App(root, settings(mock=False))
        pump(root)
        assert app.state == client.SHOWING_TEST
        draw_path_to_exit(app)
        pump(root, 1)  # submit response -> RESULT
        assert app.state == client.RESULT
        assert "REJECTED (crossed_wall)" in status_text(app)
        pump(root, 1)  # back to POLLING
        assert app.state == client.POLLING

    def test_press_outside_start_gives_hint_and_no_submit(self, monkeypatch):
        install_fakes(monkeypatch)
        test = generate_mock_test(cols=9, rows=7, seed=13)
        submitted = []

        class SpyProtocol:
            def __init__(self, host, port, timeout=2.0):
                pass

            def connect(self):
                pass

            def close(self):
                pass

            def get_alarm_state(self):
                return 1

            def get_test(self):
                return test

            def submit_answer(self, t):
                submitted.append(t)
                return ("accepted", None)

        monkeypatch.setattr(client, "ProtocolClient", SpyProtocol)
        root = FakeRoot()
        app = client.App(root, settings(mock=False))
        pump(root)
        assert app.state == client.SHOWING_TEST

        press = app._canvas.bindings["<Button-1>"]
        release = app._canvas.bindings["<ButtonRelease-1>"]
        x, y = center(4, 3)  # not the start cell
        press(FakeEvent(x, y))
        assert not app.recorder.recording
        release(FakeEvent(x, y))
        assert app.state == client.SHOWING_TEST
        assert submitted == []
        assert any(
            kw.get("text") == "Start in the green cell"
            for kind, _a, kw in app._canvas.items if kind == "text"
        )

    def test_failed_exit_check_keeps_showing_test(self, monkeypatch):
        install_fakes(monkeypatch)
        test = generate_mock_test(cols=9, rows=7, seed=14)
        make_fake_protocol(monkeypatch, states=[1], tests=[test],
                           submit_response=("accepted", None))
        root = FakeRoot()
        app = client.App(root, settings(mock=False))
        pump(root)
        assert app.state == client.SHOWING_TEST

        # Press in start, release immediately (single point, not in exit).
        press = app._canvas.bindings["<Button-1>"]
        release = app._canvas.bindings["<ButtonRelease-1>"]
        x, y = center(0, 0)
        press(FakeEvent(x, y))
        release(FakeEvent(x, y))
        assert app.state == client.SHOWING_TEST
        assert app.recorder.path == []  # cleared
        assert any(
            "Did not reach the exit" in kw.get("text", "")
            for kind, _a, kw in app._canvas.items if kind == "text"
        )

    def test_alarm_cleared_between_poll_and_get_test(self, monkeypatch):
        install_fakes(monkeypatch)
        make_fake_protocol(monkeypatch, states=[1], tests=[None],
                           submit_response=("accepted", None))
        root = FakeRoot()
        app = client.App(root, settings(mock=False))
        pump(root)
        # get_test answered "none" (race) -> back to polling.
        assert app.state == client.POLLING
        assert app.test is None
