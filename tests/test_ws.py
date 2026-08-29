"""What the WebSocket codec promises: a handshake both ends agree on, and
a frame that comes back exactly what went in -- against a real socket
pair, both directions, because a codec only one end exercises is a codec
whose bugs you find in production."""

import socket
import threading

import pytest

from harneskills import ws


def pair():
    """A connected `(server_sock, client_sock)` -- the real thing, over
    loopback, not a mock of one."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.create_connection(listener.getsockname())
    server, _ = listener.accept()
    listener.close()
    return server, client


@pytest.fixture
def sockets():
    server, client = pair()
    yield server, client
    for sock in (server, client):
        try:
            sock.close()
        except OSError:
            pass


# --- the handshake -------------------------------------------------------

def test_the_spec_s_own_worked_example():
    # RFC 6455 s1.3's own test vector -- the one the standard hands you.
    assert ws.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_a_real_handshake_both_ends_agree_on(sockets):
    server, client = sockets

    def do_server():
        ws.handshake(server)

    thread = threading.Thread(target=do_server, daemon=True)
    thread.start()
    ws.connect(client, "127.0.0.1", 0)
    thread.join(2)
    assert not thread.is_alive()


def test_a_plain_http_request_is_refused_not_hung(sockets):
    server, client = sockets
    client.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    with pytest.raises(ws.ProtocolError):
        ws.handshake(server)


def test_a_server_that_answers_wrong_is_caught_not_trusted(sockets):
    server, client = sockets

    def do_server():
        # A 101 with the WRONG accept key -- a server that misimplements
        # the spec, or isn't a WebSocket server despite claiming to be.
        request, headers = ws._read_headers(server)
        server.sendall(b"HTTP/1.1 101 Switching Protocols\r\n"
                       b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                       b"Sec-WebSocket-Accept: bm90LXRoZS1yaWdodC1rZXk=\r\n\r\n")

    threading.Thread(target=do_server, daemon=True).start()
    with pytest.raises(ws.ProtocolError):
        ws.connect(client, "127.0.0.1", 0)


# --- frames ---------------------------------------------------------------

@pytest.mark.parametrize("payload", [b"", b"hi", b"x" * 125, b"x" * 126,
                                     b"x" * 65535, b"x" * 65536,
                                     "unicode: ☃".encode("utf-8")])
def test_a_frame_round_trips_through_a_reader_both_lengths_and_masking(payload):
    for mask in (False, True):
        raw = ws.frame(payload, ws.TEXT, mask=mask)
        server, client = pair()
        try:
            (client if mask else server).sendall(raw)
            reader = ws.Reader(server if mask else client, is_server=mask)
            assert reader.message() == (ws.TEXT, payload)
        finally:
            server.close()
            client.close()


def test_a_client_frame_must_be_masked(sockets):
    server, client = sockets
    client.sendall(ws.frame(b"hi", mask=False))   # a client MUST mask
    with pytest.raises(ws.ProtocolError):
        ws.Reader(server, is_server=True).message()


def test_a_server_frame_must_not_be_masked(sockets):
    server, client = sockets
    server.sendall(ws.frame(b"hi", mask=True))    # a server MUST NOT mask
    with pytest.raises(ws.ProtocolError):
        ws.Reader(client, is_server=False).message()


def test_fragments_are_reassembled_in_order(sockets):
    server, client = sockets
    # A browser fragments a large send whenever it feels like it -- built
    # by hand here, since `ws.frame` only ever emits one whole frame.
    first = bytes([0x01, 0x80 | 5]) + b"\x00\x00\x00\x00" + b"hello"
    # first fragment: FIN=0, opcode=TEXT(1) -> 0x01; masked, length 5
    second = bytes([0x80, 0x80 | 6]) + b"\x00\x00\x00\x00" + b" world"
    # final fragment: FIN=1, opcode=CONTINUATION(0) -> 0x80; masked, length 6
    client.sendall(first + second)
    assert ws.Reader(server, is_server=True).message() == (ws.TEXT, b"hello world")


def test_a_continuation_with_nothing_to_continue_is_a_protocol_error(sockets):
    server, client = sockets
    client.sendall(bytes([0x80, 0x80]) + b"\x00\x00\x00\x00")   # bare FIN+CONTINUE
    with pytest.raises(ws.ProtocolError):
        ws.Reader(server, is_server=True).message()


def test_a_new_message_inside_a_fragmented_one_is_a_protocol_error(sockets):
    server, client = sockets
    first = bytes([0x01, 0x80]) + b"\x00\x00\x00\x00"          # unfinished TEXT
    second = bytes([0x81, 0x80]) + b"\x00\x00\x00\x00"         # a fresh TEXT, FIN
    client.sendall(first + second)
    with pytest.raises(ws.ProtocolError):
        ws.Reader(server, is_server=True).message()


def test_a_fragmented_control_frame_is_refused(sockets):
    server, client = sockets
    client.sendall(bytes([0x09, 0x80]) + b"\x00\x00\x00\x00")  # PING, FIN=0
    with pytest.raises(ws.ProtocolError):
        ws.Reader(server, is_server=True).message()


def test_a_frame_over_the_limit_is_refused_not_buffered(sockets):
    server, client = sockets
    # A 64-bit length header claiming more than the limit -- refused
    # before a single payload byte is read, so this never allocates it.
    huge = ws.MAX_MESSAGE + 1
    header = bytes([0x81, 0x80 | 127]) + huge.to_bytes(8, "big") + b"\x00\x00\x00\x00"
    client.sendall(header)
    with pytest.raises(ws.ProtocolError):
        ws.Reader(server, is_server=True).message()


def test_ping_is_answered_with_pong_and_hidden_from_the_message_api(sockets):
    server, client = sockets
    client.sendall(ws.frame(b"ping-data", ws.PING, mask=True))
    client.sendall(ws.frame(b"hi", ws.TEXT, mask=True))
    reader = ws.Reader(server, is_server=True)
    assert reader.message() == (ws.TEXT, b"hi")   # PING never surfaces
    # The server answered on the same socket -- read it directly, since
    # a client Reader would try to unmask a frame the server never masks.
    first = client.recv(2)
    assert first[0] & 0x0F == ws.PONG


def test_close_ends_the_message_stream(sockets):
    server, client = sockets
    client.sendall(ws.close_frame(mask=True))
    assert ws.Reader(server, is_server=True).message() is None


def test_a_dropped_socket_ends_the_message_stream_too(sockets):
    server, client = sockets
    client.close()
    assert ws.Reader(server, is_server=True).message() is None


def test_a_read_timeout_is_not_mistaken_for_a_close(sockets):
    # socket.timeout has been a subclass of OSError since Python 3.10 (it
    # IS TimeoutError) -- a bare `except OSError` would swallow "nothing
    # arrived within the deadline" as "the peer is gone", which is a
    # different fact a caller that set a timeout is entitled to tell apart.
    server, client = sockets
    server.settimeout(0.2)
    with pytest.raises(socket.timeout):
        ws.Reader(server, is_server=True).message()
    # And the connection is still good afterwards.
    server.settimeout(None)
    client.sendall(ws.frame(b"still here", ws.TEXT, mask=True))
    assert ws.Reader(server, is_server=True).message() == (ws.TEXT, b"still here")
