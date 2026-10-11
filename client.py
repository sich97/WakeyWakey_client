"""
client.py — WakeyWakey v2 client: a dumb terminal.

Implements the SPEC_v2.md state machine:
    CONNECTING -> POLLING -> SHOWING_TEST -> SUBMITTING -> RESULT (loop)

The client NEVER validates the awake test. It fetches the server's test,
renders it, records the user's path, submits it, and shows the server's
verdict. Only the server can stop the alarm.

GUI reliability rules (the v1 fix):
  - one Canvas per window, fixed size, non-resizable; canvas fills the window
  - ALL input via event.x / event.y on the canvas (<Button-1>, <B1-Motion>)
  - no x_root/y_root, no manual window-offset math
  - every frame is redrawn from state: maze + path = f(active test, points)
  - cell size fixed at 24 px; window size derived from the test

Logic lives in protocol.py / maze_view.py / path_capture.py (no display
needed); this module is only the Tk glue.
"""

import configparser
import threading
import tkinter as tk

from maze_view import MazeRenderer, generate_mock_test, path_ends_in_exit
from path_capture import PathRecorder
from protocol import ProtocolClient

CONNECTING = "CONNECTING"
POLLING = "POLLING"
SHOWING_TEST = "SHOWING_TEST"
SUBMITTING = "SUBMITTING"
RESULT = "RESULT"

POLL_MS = 1000
RESULT_MS = 2000
MAX_BACKOFF_S = 30.0
MOCK_COLS = 21
MOCK_ROWS = 15
MOCK_MIN_POINTS = 10

STATUS_W = 420
STATUS_H = 150


def load_settings(path="settings.ini"):
    """Load settings.ini -> {"address", "port", "mock_test"}."""
    config = configparser.ConfigParser()
    config.read(path)
    return {
        "address": config["SERVER"]["Address"],
        "port": int(config["SERVER"]["Port"]),
        "mock_test": config["CLIENT"]["Mock test"].strip().lower()
        in ("1", "true", "yes", "on"),
    }


class App:
    """Dumb-terminal state machine driving one Tk window."""

    def __init__(self, root, settings):
        self.root = root
        self.settings = settings
        self.mock = settings["mock_test"]
        self.protocol = None
        if not self.mock:
            self.protocol = ProtocolClient(settings["address"], settings["port"])

        self.renderer = MazeRenderer()
        self.state = CONNECTING
        self.test = None
        self.recorder = None
        self.backoff_s = 1.0
        self._gen = 0
        self._test_window = None
        self._canvas = None
        self._mock_count = 0

        self._build_status_window()
        if self.mock:
            self._draw_status("Mock test mode", "No network, no submission.")
            self._schedule(self._next_mock, 500)
        else:
            self._connect()

    # ---------------------------------------------------------- scheduling

    def _schedule(self, fn, ms):
        """Schedule the next state-machine step. A newer _schedule call
        invalidates any earlier step (generation token), so a stale callback
        can never fire a superseded transition."""
        self._gen += 1
        gen = self._gen

        def guarded():
            if gen == self._gen:
                fn()

        self.root.after(ms, guarded)

    # ------------------------------------------------------- status window

    def _build_status_window(self):
        self.root.title("WakeyWakey")
        self.root.geometry("%dx%d" % (STATUS_W, STATUS_H))
        self.root.resizable(False, False)
        canvas = tk.Canvas(
            self.root, width=STATUS_W, height=STATUS_H,
            bg="black", highlightthickness=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        self._status_canvas = canvas

    def _draw_status(self, main, sub=None):
        canvas = self._status_canvas
        canvas.delete("all")
        canvas.create_rectangle(0, 0, STATUS_W, STATUS_H, fill="black", outline="")
        canvas.create_text(
            STATUS_W // 2, 55, text=main, fill="white",
            font=("TkDefaultFont", 14, "bold"),
        )
        if sub:
            canvas.create_text(
                STATUS_W // 2, 100, text=sub, fill="#cccccc",
                font=("TkDefaultFont", 11),
            )

    # ------------------------------------------------------ network plumbing

    def _net(self, fn, on_done, on_error):
        """Run one socket round-trip on a worker thread; callbacks fire on
        the Tk mainloop via after(0, ...). Only one op in flight at a time."""

        def worker():
            try:
                result = fn()
            except Exception as exc:
                self.root.after(0, lambda: on_error(exc))
            else:
                self.root.after(0, lambda: on_done(result))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ state: connect

    def _connect(self):
        self._set_state(CONNECTING)
        self._draw_status(
            "Connecting to %s:%d ..." % (
                self.settings["address"], self.settings["port"]
            )
        )

        def ok(_):
            self.backoff_s = 1.0
            self._poll()

        def fail(err):
            delay = min(self.backoff_s, MAX_BACKOFF_S)
            self.backoff_s = min(self.backoff_s * 2, MAX_BACKOFF_S)
            self._draw_status(
                "Server unreachable",
                "Retrying in %.0f s (%s)" % (delay, err.__class__.__name__),
            )
            self._schedule(self._connect, int(delay * 1000))

        def do():
            self.protocol.connect()
            return True

        self._net(do, ok, fail)

    # ------------------------------------------------------------- state: polling

    def _poll(self):
        self._set_state(POLLING)
        self._draw_status("Polling alarm state ...")

        def on_state(state):
            if state == 1:
                self._fetch_test()
            else:
                self._draw_status("Alarm off", "Polling every 1 s.")
                self._schedule(self._poll, POLL_MS)

        def on_error(err):
            self.protocol.close()
            self._schedule(self._connect, int(self.backoff_s * 1000))

        self._net(self.protocol.get_alarm_state, on_state, on_error)

    def _fetch_test(self):
        def on_test(test):
            if test is None:
                self._draw_status("Alarm off", "Polling every 1 s.")
                self._schedule(self._poll, POLL_MS)
                return
            self._show_test(test)

        def on_error(err):
            self.protocol.close()
            self._schedule(self._connect, int(self.backoff_s * 1000))

        self._net(self.protocol.get_test, on_test, on_error)

    # -------------------------------------------------------- state: showing test

    def _show_test(self, test):
        self.test = test
        self.recorder = PathRecorder(test["start"])
        self._set_state(SHOWING_TEST)
        self._build_test_window(test)
        self._redraw_test(None)

    def _build_test_window(self, test):
        width, height = self.renderer.size(test)
        if self._test_window is not None:
            self._test_window.destroy()

        win = tk.Toplevel(self.root)
        win.title("WakeyWakey - awake test")
        win.resizable(False, False)
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        win.geometry("%dx%d+%d+%d" % (width, height, x, y))
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        win.lift()

        canvas = tk.Canvas(
            win, width=width, height=height, bg="white", highlightthickness=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        canvas.bind("<Button-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_motion)
        canvas.bind("<ButtonRelease-1>", self._on_release)

        self._test_window = win
        self._canvas = canvas

    def _close_test_window(self):
        if self._test_window is not None:
            self._test_window.destroy()
            self._test_window = None
            self._canvas = None

    def _redraw_test(self, hint):
        """Full redraw: maze + path are pure functions of (test, points)."""
        if self._canvas is None or self.test is None:
            return
        path = self.recorder.path if self.recorder is not None else None
        for op in self.renderer.render(self.test, path, hint):
            self._draw_op(self._canvas, op)

    def _draw_op(self, canvas, op):
        kind = op[0]
        if kind == "bg":
            canvas.delete("all")
            canvas.create_rectangle(0, 0, op[1], op[2], fill="white", outline="")
        elif kind == "cell":
            canvas.create_rectangle(
                op[1], op[2], op[3], op[4], fill=op[5], outline=""
            )
        elif kind == "wall":
            canvas.create_line(op[1], op[2], op[3], op[4], fill="black", width=3)
        elif kind == "path":
            if len(op[1]) >= 2:
                flat = [v for point in op[1] for v in point]
                canvas.create_line(*flat, fill="blue", width=4)
        elif kind == "hint":
            canvas.create_text(
                canvas.winfo_width() // 2, canvas.winfo_height() // 2,
                text=op[1], fill="red", font=("TkDefaultFont", 12, "bold"),
            )

    # ------------------------------------------------------ canvas input events

    def _on_press(self, event):
        if self.state != SHOWING_TEST or self.recorder is None:
            return
        if self.recorder.press(event.x, event.y):
            self._redraw_test(None)
        else:
            self._redraw_test("Start in the green cell")

    def _on_motion(self, event):
        if self.state != SHOWING_TEST or self.recorder is None:
            return
        self.recorder.motion(event.x, event.y)
        self._redraw_test(None)

    def _on_release(self, event):
        if self.state != SHOWING_TEST or self.recorder is None:
            return
        if not self.recorder.recording:
            return
        path = self.recorder.release()
        # Cheap UX hint only (allowed by the spec). The server is the only
        # authority; this check never blocks a submission of an exiting path.
        if path_ends_in_exit(path, self.test["exit"]):
            if self.mock:
                self._mock_success()
            else:
                self._submit(path)
        else:
            self._redraw_test("Did not reach the exit - try again")

    # ------------------------------------------------------- state: submitting

    def _submit(self, path):
        self._set_state(SUBMITTING)
        self._redraw_test("Sending answer ...")
        payload_test = dict(self.test)
        payload_test["_path"] = path

        def on_response(response):
            verdict, reason = response
            self._close_test_window()
            self.test = None
            self.recorder = None
            self._set_state(RESULT)
            if verdict == "accepted":
                self._draw_status("ACCEPTED", "The server stopped the alarm.")
            else:
                self._draw_status(
                    "REJECTED (%s)" % reason, "A fresh test is now active."
                )
            self._schedule(self._poll, POLL_MS)

        def on_error(err):
            # Lost the connection mid-submit. The alarm is still ringing on
            # the server (a submit that failed in transit is either unseen
            # or, if seen, already handled) - so reconnect and keep polling.
            self.protocol.close()
            self._close_test_window()
            self.test = None
            self.recorder = None
            self._draw_status(
                "Lost connection while submitting",
                "Alarm still active - reconnecting (%s)" % err.__class__.__name__,
            )
            self.backoff_s = 1.0
            self._schedule(self._connect, 1000)

        self._net(lambda: self.protocol.submit_answer(payload_test),
                  on_response, on_error)

    # ------------------------------------------------------------- mock mode

    def _next_mock(self):
        self._mock_count += 1
        test = generate_mock_test(
            MOCK_COLS, MOCK_ROWS, min_path_points=MOCK_MIN_POINTS,
            seed=self._mock_count,
        )
        self._show_test(test)
        self._redraw_test("MOCK TEST - no server, nothing is submitted")

    def _mock_success(self):
        self._close_test_window()
        self.test = None
        self.recorder = None
        self._set_state(RESULT)
        self._draw_status(
            "MOCK: reached the exit", "Nothing was submitted (mock_test)."
        )
        self._schedule(self._next_mock, RESULT_MS)

    # ---------------------------------------------------------------- helpers

    def _set_state(self, state):
        self.state = state


def main():
    settings = load_settings()
    root = tk.Tk()
    App(root, settings)
    root.mainloop()


if __name__ == "__main__":
    main()
