"""Unit tests for protocol: command framing, payload round-trip, live TCP."""

import base64
import json
import socket
import threading
import time

from maze_view import generate_mock_test
from protocol import (
    ProtocolClient,
    ProtocolError,
    command_line,
    decode_test,
    encode_submit_payload,
    parse_submit_response,
)


def make_test():
    test = generate_mock_test(cols=4, rows=3, seed=5)
    test["_path"] = [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5]]
    return test


class TestCommandLine:
    def test_bare_command(self):
        assert command_line("get_alarm_state") == "get_alarm_state"

    def test_command_with_args(self):
        assert command_line("set_wakeup_hour", 7) == "set_wakeup_hour 7"

    def test_submit_command_shape(self):
        payload = encode_submit_payload("sig123", [[0.5, 0.5]])
        line = command_line("submit_answer", "id42", payload)
        assert line.split() == ["submit_answer", "id42", payload]


class TestSubmitPayloadRoundTrip:
    def test_encode_decode_round_trip(self):
        test = make_test()
        encoded = encode_submit_payload(test["sig"], test["_path"])
        # base64, ascii, single argument (no spaces or newlines)
        decoded_bytes = base64.b64decode(encoded)
        assert " " not in encoded and "\n" not in encoded
        payload = json.loads(decoded_bytes.decode("ascii"))
        assert payload["sig"] == test["sig"]
        assert payload["path"] == [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5]]

    def test_path_values_are_floats(self):
        encoded = encode_submit_payload("s", [[1, 2]])
        payload = json.loads(base64.b64decode(encoded).decode("ascii"))
        assert payload["path"] == [[1.0, 2.0]]
        assert all(isinstance(v, float) for point in payload["path"] for v in point)


class TestGetTestParsing:
    def test_parse_json_line(self):
        line = json.dumps(generate_mock_test(cols=3, rows=2, seed=1))
        test = decode_test(line)
        assert test["kind"] == "maze"
        assert test["cols"] == 3

    def test_none_response(self):
        assert decode_test("none") is None

    def test_missing_key_raises(self):
        try:
            decode_test('{"test_id": "x"}')
            assert False, "expected ProtocolError"
        except ProtocolError:
            pass


class TestSubmitResponseParsing:
    def test_accepted(self):
        assert parse_submit_response("accepted") == ("accepted", None)

    def test_rejected_with_reason(self):
        assert parse_submit_response("rejected crossed_wall") == (
            "rejected", "crossed_wall"
        )

    def test_unknown_reason(self):
        try:
            parse_submit_response("maybe")
            assert False, "expected ProtocolError"
        except ProtocolError:
            pass


class TestTcpFraming:
    """Live loopback server: verifies one-command-per-line framing."""

    def _server(self, responses):
        """Start a loopback server that answers each received line with the
        next pre-queued response (from `responses`, in order). Each response
        is a list of byte chunks, possibly split across several packets."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        received = []

        def serve():
            conn, _ = listener.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    received.append(line.decode("ascii"))
                    if responses:
                        for piece in responses.pop(0):
                            conn.sendall(piece)
                            time.sleep(0.01)  # force separate packets
            conn.close()
            listener.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        return port, received

    def test_request_sends_line_and_reads_line(self):
        port, received = self._server([[b"1\n"]])
        client = ProtocolClient("127.0.0.1", port)
        client.connect()
        try:
            assert client.get_alarm_state() == 1
        finally:
            client.close()
        assert received == ["get_alarm_state"]

    def test_submit_answer_framing_and_response(self):
        test = make_test()
        port, received = self._server([[b"accepted\n"]])
        client = ProtocolClient("127.0.0.1", port)
        client.connect()
        try:
            assert client.submit_answer(test) == ("accepted", None)
        finally:
            client.close()
        assert len(received) == 1
        parts = received[0].split()
        assert parts[0] == "submit_answer"
        assert parts[1] == test["test_id"]
        payload = json.loads(base64.b64decode(parts[2]).decode("ascii"))
        assert payload["sig"] == test["sig"]
        assert payload["path"] == test["_path"]

    def test_rejected_reason_round_trip(self):
        test = make_test()
        port, _ = self._server([[b"rejected bad_exit\n"]])
        client = ProtocolClient("127.0.0.1", port)
        client.connect()
        try:
            assert client.submit_answer(test) == ("rejected", "bad_exit")
        finally:
            client.close()

    def test_response_split_across_tcp_packets(self):
        # One logical response, sent in three packets; client reassembles it.
        port, _ = self._server([[b"re", b"jected ", b"teleport\n"]])
        client = ProtocolClient("127.0.0.1", port)
        client.connect()
        try:
            assert client.request("get_test") == "rejected teleport"
        finally:
            client.close()

    def test_get_test_none(self):
        port, _ = self._server([[b"none\n"]])
        client = ProtocolClient("127.0.0.1", port)
        client.connect()
        try:
            assert client.get_test() is None
        finally:
            client.close()

    def test_get_test_json(self):
        test = generate_mock_test(cols=3, rows=2, seed=2)
        port, _ = self._server([[json.dumps(test).encode("ascii") + b"\n"]])
        client = ProtocolClient("127.0.0.1", port)
        client.connect()
        try:
            assert client.get_test() == test
        finally:
            client.close()

    def test_request_without_connection_raises(self):
        client = ProtocolClient("127.0.0.1", 1)
        try:
            client.request("get_alarm_state")
            assert False, "expected OSError"
        except OSError:
            pass

    def test_eof_raises_oserror(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve():
            conn, _ = listener.accept()
            conn.close()
            listener.close()

        threading.Thread(target=serve, daemon=True).start()
        client = ProtocolClient("127.0.0.1", port)
        client.connect()
        try:
            client.get_alarm_state()
            assert False, "expected OSError"
        except OSError:
            pass
        finally:
            client.close()
