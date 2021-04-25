from enum import Enum, auto
from typing import Optional, Tuple

from .consts import *
from .common import OutputInfo, _validate_input_buffer_size, _validate_window_sz2, _validate_lookahead_sz2


class State(Enum):
    TAG_BIT = auto()
    YIELD_LITERAL = auto()
    BACKREF_INDEX_MSB = auto()
    BACKREF_INDEX_LSB = auto()
    BACKREF_COUNT_MSB = auto()
    BACKREF_COUNT_LSB = auto()
    YIELD_BACKREF = auto()


class Reader:
    _input_buffer_size: int
    _window_sz2: int
    _lookahead_sz2: int

    _input_buffer: bytearray
    _window_buffer: bytearray
    _input_size: int
    _input_index: int
    _output_count: int
    _output_index: int
    _head_index: int
    _state: State
    _current_byte: int
    _bit_index: int

    _oi: Optional[OutputInfo]

    def __init__(
        self,
        input_buffer_size: int = DEFAULT_INPUT_BUFFER_SIZE,
        window_sz2: int = DEFAULT_WINDOW_SZ2,
        lookahead_sz2: int = DEFAULT_LOOKAHEAD_SZ2,
    ):
        _validate_input_buffer_size(input_buffer_size)
        _validate_window_sz2(window_sz2)
        _validate_lookahead_sz2(lookahead_sz2, window_sz2)

        self._input_buffer_size = input_buffer_size
        self._window_sz2 = window_sz2
        self._lookahead_sz2 = lookahead_sz2

        self._state_handlers = {
            State.TAG_BIT: self._tag_bit,
            State.YIELD_LITERAL: self._yield_literal,
            State.BACKREF_INDEX_MSB: self._backref_index_msb,
            State.BACKREF_INDEX_LSB: self._backref_index_lsb,
            State.BACKREF_COUNT_MSB: self._backref_count_msb,
            State.BACKREF_COUNT_LSB: self._backref_count_lsb,
            State.YIELD_BACKREF: self._yield_backref,
        }

        self._oi = None

        self.reset()

    @property
    def max_output_size(self):
        return 1 << self._window_sz2

    def reset(self):
        self._input_buffer = bytearray(self._input_buffer_size)
        self._window_buffer = bytearray((1 << self._window_sz2))
        self._state = State.TAG_BIT
        self._input_size = 0
        self._input_index = 0
        self._bit_index = 0x00
        self._current_byte = 0x00
        self._output_count = 0
        self._output_index = 0
        self._head_index = 0

    def sink(self, in_buf: bytes) -> Tuple[bool, int]:
        if not isinstance(in_buf, bytes):
            raise ValueError("in_buf must be a bytes object")

        rem = self._input_buffer_size - self._input_size
        if rem == 0:
            return True, 0

        size = len(in_buf)
        if rem < size:
            size = rem

        self._input_buffer[self._input_size : self._input_index + size] = in_buf[:size]
        self._input_size += size
        return False, size

    def poll(self, out_buf_size: Optional[int] = None) -> Tuple[bool, bytes]:
        if out_buf_size is None:
            out_buf_size = self.max_output_size

        self._oi = OutputInfo(out_buf_size)
        while True:
            in_state = self._state
            handler = self._state_handlers.get(self._state)
            if handler:
                self._state = handler()
            else:
                raise RuntimeError("Decoder poll unknown error")

            if self._state == in_state:
                try:
                    return self._oi.output_size == out_buf_size, self._oi.get_output()
                finally:
                    self._oi = None

    def finish(self) -> bool:
        if self._state == State.YIELD_BACKREF:
            return False
        return self._input_size == 0

    def _tag_bit(self) -> State:
        bits = self._get_bits(1)
        if bits is None:
            return State.TAG_BIT
        elif bits:
            return State.YIELD_LITERAL
        elif self._window_sz2 > 8:
            return State.BACKREF_INDEX_MSB
        else:
            self._output_index = 0
            return State.BACKREF_INDEX_LSB

    def _yield_literal(self) -> State:
        if self._oi.output_size < self._oi.buf_size:
            byte = self._get_bits(8)
            if byte is None:
                return State.YIELD_LITERAL
            mask = (1 << self._window_sz2) - 1
            c = byte & 0xFF
            self._window_buffer[self._head_index & mask] = c
            self._head_index += 1
            self._push_byte(c)
            return State.TAG_BIT
        else:
            return State.YIELD_LITERAL

    def _backref_index_msb(self) -> State:
        assert self._window_sz2 > 8
        bits = self._get_bits(self._window_sz2 - 8)
        if bits is None:
            return State.BACKREF_INDEX_MSB
        self._output_index = bits << 8
        return State.BACKREF_INDEX_LSB

    def _backref_index_lsb(self) -> State:
        bits = self._get_bits(self._window_sz2 if self._window_sz2 < 8 else 8)
        if bits is None:
            return State.BACKREF_INDEX_LSB
        self._output_index |= bits
        self._output_index += 1
        self._output_count = 0
        return (
            State.BACKREF_COUNT_MSB
            if self._lookahead_sz2 > 8
            else State.BACKREF_COUNT_LSB
        )

    def _backref_count_msb(self) -> State:
        assert self._lookahead_sz2 > 8
        bits = self._get_bits(self._lookahead_sz2 - 8)
        if bits is None:
            return State.BACKREF_COUNT_MSB
        self._output_count = bits << 8
        return State.BACKREF_COUNT_LSB

    def _backref_count_lsb(self) -> State:
        bits = self._get_bits(self._lookahead_sz2 if self._lookahead_sz2 < 8 else 8)
        if bits is None:
            return State.BACKREF_COUNT_LSB
        self._output_count |= bits
        self._output_count += 1
        return State.YIELD_BACKREF

    def _yield_backref(self) -> State:
        count = self._oi.buf_size - self._oi.output_size
        if count > 0:
            count = min(count, self._output_count)
            mask = (1 << self._window_sz2) - 1
            neg_offset = self._output_index
            assert neg_offset <= mask + 1
            assert count <= (1 << self._lookahead_sz2)

            for i in range(count):
                c = self._window_buffer[(self._head_index - neg_offset) & mask]
                self._push_byte(c)
                self._window_buffer[self._head_index & mask] = c
                self._head_index += 1

            self._output_count -= count
            if self._output_count == 0:
                return State.TAG_BIT
        return State.YIELD_BACKREF

    def _get_bits(self, count: int) -> Optional[int]:
        accumulator = 0

        if count > 15:
            return None

        if self._input_size == 0 and self._bit_index < (1 << (count - 1)):
            return None

        for i in range(count):
            if self._bit_index == 0x00:
                if self._input_size == 0:
                    return None
                self._current_byte = self._input_buffer[self._input_index]
                self._input_index += 1
                if self._input_index == self._input_size:
                    self._input_index = 0
                    self._input_size = 0
                self._bit_index = 0x80
            accumulator <<= 1
            if self._current_byte & self._bit_index:
                accumulator |= 0x01
            self._bit_index >>= 1

        return accumulator

    def _push_byte(self, value: int):
        self._oi.buf[self._oi.output_size] = value
        self._oi.output_size += 1
