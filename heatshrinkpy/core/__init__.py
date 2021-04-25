import array

from .consts import *
from .decoder import Reader
from .encoder import Writer

__all__ = ["Writer", "Reader", "Encoder", "encode", "decode"]


class Encoder:
    """High level interface to the Heatshrink encoders/decoders."""

    def __init__(self, encoder):
        self._encoder = encoder
        self._finished = False

    def _check_not_finished(self):
        """Throws an exception if the encoder has been closed."""

        if self._finished:
            msg = "Attempted to perform operation on a closed encoder."

            # TODO: ValueError isn't the right exception for this
            raise ValueError(msg)

    def _drain(self):
        """Empty data from the encoder state machine."""

        while True:
            more, buf = self._encoder.poll()

            yield buf

            # Done polling
            if not more:
                break

    def fill(self, buf):
        """Fill the encoder state machine with a buffer."""

        self._check_not_finished()

        if isinstance(buf, (str, memoryview, bool)):
            msg = "Cannot fill encoder with type '{.__name__}'"

            raise TypeError(msg.format(buf.__class__))

        buf = bytes(buf)

        out_buf = bytearray()

        while buf:
            full, sunk = self._encoder.sink(buf)
            buf = buf[sunk:]

            # Clear state machine
            for data in self._drain():
                out_buf.extend(data)

        return bytes(out_buf)

    def finish(self):
        """Close encoder and return any remaining data.

        Will throw an exception if fill() or finish() is used after
        this.

        """

        self._check_not_finished()

        out_buf = bytearray()

        while True:
            finished = self._encoder.finish()

            if finished:
                self._finished = True
                break

            for data in self._drain():
                out_buf.extend(data)

        return bytes(out_buf)

    @property
    def finished(self):
        """Returns true if the encoder has been closed."""

        return self._finished


def _encode_impl(encoder, buf):
    encoder = Encoder(encoder)
    return encoder.fill(buf) + encoder.finish()


def encode(
    data: bytes,
    window_sz2: int = DEFAULT_WINDOW_SZ2,
    lookahead_sz2: int = DEFAULT_LOOKAHEAD_SZ2,
) -> bytes:
    return _encode_impl(Writer(window_sz2, lookahead_sz2), data)


def decode(
    data: bytes,
    input_buffer_size: int = DEFAULT_INPUT_BUFFER_SIZE,
    window_sz2: int = DEFAULT_WINDOW_SZ2,
    lookahead_sz2: int = DEFAULT_LOOKAHEAD_SZ2,
) -> bytes:
    return _encode_impl(Reader(input_buffer_size, window_sz2, lookahead_sz2), data)
