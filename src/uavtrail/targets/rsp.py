"""A client for the GDB Remote Serial Protocol.

Debug probes on a flashing station speak it: OpenOCD, pyOCD and SEGGER's J-Link GDB server all expose the target
over a TCP port. So does QEMU's gdbstub, which is how this repository flashes emulated microcontrollers. The station
talks to all of them the same way; only the flash write differs (vFlash packets on a real probe, plain memory
writes on QEMU, see targets/mcu.py).

https://sourceware.org/gdb/current/onlinedocs/gdb.html/Remote-Protocol.html
"""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass, field

STOP_REPLY = re.compile(r"^[ST][0-9a-fA-F]{2}")


class ProtocolError(RuntimeError):
    """The other end answered something the protocol does not allow, or answered with an error."""


class LinkError(ConnectionError):
    """The link to the probe failed: refused, dropped, timed out or garbled beyond retry."""


def checksum(payload: bytes) -> bytes:
    return b"%02x" % (sum(payload) & 0xFF)


def escape(data: bytes) -> bytes:
    """Binary data in X/vFlashWrite packets: '#', '$', '}' and '*' are escaped as '}' followed by byte ^ 0x20."""
    out = bytearray()
    for b in data:
        if b in b"#$}*":
            out += bytes((0x7D, b ^ 0x20))
        else:
            out.append(b)
    return bytes(out)


@dataclass
class RspClient:
    host: str
    port: int
    timeout: float = 5.0
    retries: int = 3
    features: dict[str, str] = field(default_factory=dict)
    _sock: socket.socket | None = None
    _buf: bytes = b""

    # --------------------------------------------------------------------------- connection

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as e:
            raise LinkError(f"cannot reach the probe at {self.host}:{self.port}: {e}") from e
        self._sock.settimeout(self.timeout)
        # small packets and acknowledgements in both directions: without this, Nagle and delayed ACKs cost ~40 ms each
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        answer = self.request("qSupported:multiprocess+;swbreak+;hwbreak+")
        for item in answer.split(";"):
            if "=" in item:
                k, v = item.split("=", 1)
                self.features[k] = v
            elif item:
                self.features[item.rstrip("+-?")] = item[-1]

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._buf = b""

    def __enter__(self) -> RspClient:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def packet_size(self) -> int:
        return int(self.features.get("PacketSize", "400"), 16)

    @property
    def supports_flash_packets(self) -> bool:
        """Probes with a flash driver (OpenOCD, J-Link) announce the vFlash family through the memory map."""
        return self.features.get("qXfer:memory-map:read") == "+"

    # --------------------------------------------------------------------------- framing

    def _read(self) -> bytes:
        assert self._sock is not None
        try:
            chunk = self._sock.recv(65536)
        except TimeoutError as e:
            raise LinkError("the probe stopped answering") from e
        except OSError as e:
            raise LinkError(f"the link to the probe dropped: {e}") from e
        if not chunk:
            raise LinkError("the probe closed the link")
        return chunk

    def _packet(self) -> str:
        """The next whole packet, acknowledged; a packet with a bad checksum is NAKed and resent by the other end."""
        while True:
            while True:
                start = self._buf.find(b"$")
                if start >= 0:
                    end = self._buf.find(b"#", start)
                    if end >= 0 and len(self._buf) >= end + 3:
                        break
                self._buf += self._read()
            payload = self._buf[start + 1 : end]
            got = self._buf[end + 1 : end + 3]
            self._buf = self._buf[end + 3 :]
            assert self._sock is not None
            if got.lower() == checksum(payload):
                self._sock.sendall(b"+")
                return payload.decode("latin-1")
            self._sock.sendall(b"-")

    def send(self, payload: bytes) -> None:
        """Sends a packet and waits for its acknowledgement, resending on a NAK."""
        assert self._sock is not None, "not connected"
        frame = b"$" + payload + b"#" + checksum(payload)
        for _ in range(self.retries):
            self._sock.sendall(frame)
            while True:
                if not self._buf:
                    self._buf += self._read()
                ack, self._buf = self._buf[:1], self._buf[1:]
                if ack == b"+":
                    return
                if ack == b"-":
                    break
                if ack == b"$":  # no-ack mode or an early reply: keep it for _packet
                    self._buf = ack + self._buf
                    return
        raise LinkError("the probe kept rejecting a packet (bad line?)")

    def request(self, payload: str | bytes) -> str:
        """Sends a packet and returns its reply. A stop reply (T05..., S05) that arrives for a request that cannot
        cause one is left over from a target someone else let run, and is skipped: attaching to a running part
        halts it, and some probes report that stop before answering."""
        raw = payload.encode("latin-1") if isinstance(payload, str) else payload
        self.send(raw)
        answer = self._packet()
        while not raw.startswith((b"c", b"s", b"?", b"vCont")) and STOP_REPLY.match(answer):
            answer = self._packet()
        return answer

    def ok(self, payload: str | bytes) -> None:
        answer = self.request(payload)
        if answer != "OK":
            raise ProtocolError(f"{(payload if isinstance(payload, str) else payload[:16])!r} answered {answer!r}")

    # --------------------------------------------------------------------------- memory

    def read_memory(self, address: int, length: int) -> bytes:
        out = bytearray()
        step = max(16, (self.packet_size - 8) // 2)
        while len(out) < length:
            n = min(step, length - len(out))
            answer = self.request(f"m{address + len(out):x},{n:x}")
            if answer.startswith("E") and len(answer) == 3:
                raise ProtocolError(f"read at {address + len(out):#x} refused: {answer}")
            chunk = bytes.fromhex(answer)
            if not chunk:
                raise ProtocolError(f"empty read at {address + len(out):#x}")
            out += chunk
        return bytes(out)

    def write_memory(self, address: int, data: bytes) -> None:
        step = max(16, (self.packet_size - 32) // 2)
        for off in range(0, len(data), step):
            chunk = data[off : off + step]
            self.ok(f"M{address + off:x},{len(chunk):x}:{chunk.hex()}")

    def flash_erase(self, address: int, length: int) -> None:
        self.ok(f"vFlashErase:{address:x},{length:x}")

    def flash_write(self, address: int, data: bytes) -> None:
        step = max(64, self.packet_size - 64)
        for off in range(0, len(data), step):
            self.ok(b"vFlashWrite:%x:" % (address + off) + escape(data[off : off + step]))

    def flash_done(self) -> None:
        self.ok("vFlashDone")

    # --------------------------------------------------------------------------- control

    def monitor(self, command: str) -> str:
        """A probe-specific command ('reset halt' on OpenOCD, 'system_reset' on QEMU); returns what it printed."""
        answer = self.request("qRcmd," + command.encode().hex())
        out: list[str] = []
        while answer.startswith("O") and answer != "OK":
            out.append(bytes.fromhex(answer[1:]).decode(errors="replace"))
            answer = self._packet()
        if answer.startswith("E"):
            raise ProtocolError(f"monitor {command!r}: {answer}")
        return "".join(out)

    def resume(self) -> None:
        """Lets the target run. There is no reply until it stops, so none is awaited."""
        self.send(b"c")
