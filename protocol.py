"""
protocol.py — v2 TCP protocol helpers for the WakeyWakey client.

Line-oriented framing over TCP (one command per line, ASCII):
  client -> server:  "command arg1 arg2 ...\n"
  server -> client:  single line (bare token, or one JSON object, no newlines)

Importable without a display.
"""

import base64
import json
import socket


class ProtocolError(Exception):
    """Raised when the peer sends something we cannot interpret."""


def command_line(name, *args):
    """Build a v2 command line without the trailing newline."""
    parts = [name] + [str(a) for a in args]
    return " ".join(parts)


def encode_submit_payload(sig, path):
    """Encode a submit_answer payload as base64(JSON).

    payload = {"sig": <sig echoed from get_test>, "path": [[c, r], ...]}
    Path points are floats in cell units, 0-indexed.
    """
    payload = {"sig": sig, "path": [[float(c), float(r)] for c, r in path]}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return base64.b64encode(raw).decode("ascii")


def decode_test(line):
    """Parse a get_test response line. Returns dict, or None for 'none'."""
    line = line.strip()
    if line == "none":
        return None
    test = json.loads(line)
    for key in ("test_id", "kind", "cols", "rows", "start", "exit", "walls", "sig"):
        if key not in test:
            raise ProtocolError("get_test response missing key: %s" % key)
    return test


def parse_submit_response(line):
    """Parse a submit_answer response.

    Returns ("accepted", None) or ("rejected", reason).
    """
    line = line.strip()
    if line == "accepted":
        return "accepted", None
    if line.startswith("rejected"):
        parts = line.split()
        reason = parts[1] if len(parts) > 1 else "unknown"
        return "rejected", reason
    raise ProtocolError("unexpected submit_answer response: %r" % line)


def decode_json_response(line):
    """Parse a JSON-object response line (get_user_preferences, get_test)."""
    return json.loads(line.strip())


class ProtocolClient:
    """Thin TCP client for the v2 line protocol.

    Not thread-safe; use it from a single worker thread. All methods
    raise OSError (or ProtocolError for bad payloads) on failure.
    """

    def __init__(self, host, port, timeout=2.0):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.sock = None
        self._buf = b""

    def connect(self):
        self.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self._buf = b""

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self._buf = b""

    @property
    def connected(self):
        return self.sock is not None

    def request(self, line):
        """Send one command line and read one response line."""
        if self.sock is None:
            raise OSError("not connected")
        self.sock.sendall((line + "\n").encode("ascii"))
        return self._read_line()

    def _read_line(self):
        while b"\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                self.close()
                raise OSError("connection closed by server")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("ascii")

    def get_alarm_state(self):
        """Returns 0 or 1."""
        return int(self.request(command_line("get_alarm_state")))

    def get_test(self):
        """Returns the active test dict, or None if no alarm is ringing."""
        return decode_test(self.request(command_line("get_test")))

    def submit_answer(self, test):
        """Submit the recorded path for the given test.

        Returns ("accepted", None) or ("rejected", reason).
        """
        payload = encode_submit_payload(test["sig"], test["_path"])
        line = command_line("submit_answer", test["test_id"], payload)
        return parse_submit_response(self.request(line))

    def set_wakeup_hour(self, hour):
        return self.request(command_line("set_wakeup_hour", hour))

    def set_wakeup_minute(self, minute):
        return self.request(command_line("set_wakeup_minute", minute))

    def set_wakeup_window(self, seconds):
        return self.request(command_line("set_wakeup_window", seconds))

    def set_utc_offset(self, minutes):
        return self.request(command_line("set_utc_offset", minutes))

    def set_grace_period(self, seconds):
        return self.request(command_line("set_grace_period", seconds))

    def get_timezone_time(self):
        return self.request(command_line("get_timezone_time"))

    def get_user_preferences(self):
        return decode_json_response(self.request(command_line("get_user_preferences")))
