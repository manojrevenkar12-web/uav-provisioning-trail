"""The GDB remote protocol client against a scripted probe: framing, acknowledgements, resends, flash packets."""

from __future__ import annotations

import socket
import threading

import pytest

from uavtrail.targets.rsp import LinkError, ProtocolError, RspClient, checksum, escape


def frame(payload: bytes) -> bytes:
    return b"$" + payload + b"#" + checksum(payload)


class Probe:
    """Answers packets from a script; can NAK the first copy of a packet or garble a reply's checksum once."""

    def __init__(
        self, features: bytes = b"PacketSize=400", nak_first: bool = False, garble_reply: bool = False
    ) -> None:
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.features, self.nak_first, self.garble_reply = features, nak_first, garble_reply
        self.received: list[bytes] = []
        self.memory = bytearray(256)
        threading.Thread(target=self.serve, daemon=True).start()

    def reply(self, payload: bytes) -> bytes:
        if payload.startswith(b"qSupported"):
            return self.features
        if payload.startswith(b"m"):
            addr, n = (int(x, 16) for x in payload[1:].split(b","))
            return self.memory[addr : addr + n].hex().encode()
        if payload.startswith(b"M"):
            head, data = payload[1:].split(b":")
            addr, _ = (int(x, 16) for x in head.split(b","))
            raw = bytes.fromhex(data.decode())
            self.memory[addr : addr + len(raw)] = raw
            return b"OK"
        if payload.startswith(b"qRcmd"):
            return b"O" + b"reset done\n".hex().encode()
        if payload.startswith(b"vFlash"):
            return b"OK"
        return b"E01"

    def serve(self) -> None:
        conn, _ = self.server.accept()
        buf, naked, garbled = b"", False, False
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            while b"#" in buf and len(buf) >= buf.index(b"#") + 3:
                buf = buf[buf.index(b"$") :] if b"$" in buf else b""
                if not buf:
                    break
                end = buf.index(b"#")
                payload, buf = buf[1:end], buf[end + 3 :]
                if self.nak_first and not naked:
                    naked = True
                    conn.sendall(b"-")
                    continue
                conn.sendall(b"+")
                self.received.append(payload)
                answer = self.reply(payload)
                if self.garble_reply and not garbled and payload.startswith(b"m"):
                    garbled = True
                    conn.sendall(b"$" + answer + b"#00")  # wrong checksum: the client must NAK and get it again
                conn.sendall(frame(answer))
                if payload.startswith(b"qRcmd"):
                    conn.sendall(frame(b"OK"))


def test_memory_round_trip_and_features() -> None:
    p = Probe()
    with RspClient("127.0.0.1", p.port) as c:
        assert c.packet_size == 0x400 and not c.supports_flash_packets
        c.write_memory(16, bytes(range(100)))
        assert c.read_memory(16, 100) == bytes(range(100))
        assert c.monitor("reset") == "reset done\n"


def test_a_nak_makes_the_client_resend() -> None:
    p = Probe(nak_first=True)
    with RspClient("127.0.0.1", p.port) as c:
        assert c.features["PacketSize"] == "400"
    assert p.received[0].startswith(b"qSupported")


def test_a_reply_with_a_bad_checksum_is_refused_and_resent() -> None:
    p = Probe(garble_reply=True)
    with RspClient("127.0.0.1", p.port) as c:
        p.memory[0:4] = b"\x01\x02\x03\x04"
        assert c.read_memory(0, 4) == b"\x01\x02\x03\x04"


def test_probes_with_a_flash_driver_get_flash_packets() -> None:
    p = Probe(features=b"PacketSize=400;qXfer:memory-map:read+")
    with RspClient("127.0.0.1", p.port) as c:
        assert c.supports_flash_packets
        c.flash_erase(0x08000000, 0x4000)
        c.flash_write(0x08000000, b"#$}*abc")
        c.flash_done()
    assert p.received[1] == b"vFlashErase:8000000,4000"
    assert p.received[2] == b"vFlashWrite:8000000:" + escape(b"#$}*abc")
    assert escape(b"#$}*") == b"}\x03}\x04}]}\x0a"


def test_errors_and_dead_links_are_told_apart() -> None:
    p = Probe()
    with RspClient("127.0.0.1", p.port) as c, pytest.raises(ProtocolError):
        c.ok("Z0,0,0")
    with pytest.raises(LinkError):
        RspClient("127.0.0.1", 1, timeout=0.5).connect()
