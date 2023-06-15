from enum import Enum, auto
from typing import Optional, Tuple, List

from .consts import *
from .common import OutputInfo, _validate_window_sz2, _validate_lookahead_sz2

HEATSHRINK_LITERAL_MARKER = 0x01
HEATSHRINK_BACKREF_MARKER = 0x00


class State(Enum):
    NOT_FULL = auto()
    FILLED = auto()
    SEARCH = auto()
    YIELD_TAG_BIT = auto()
    YIELD_LITERAL = auto()
    YIELD_BR_INDEX = auto()
    YIELD_BR_LENGTH = auto()
    SAVE_BACKLOG = auto()
    FLUSH_BITS = auto()
    DONE = auto()


class Writer:
    _window_sz2: int
    _lookahead_sz2: int

    _buffer: bytearray
    _input_size: int
    _match_scan_index: int
    _match_length: int
    _match_pos: int
    _outgoing_bits: int
    _outgoing_bits_count: int
    _state: State
    _current_byte: int
    _bit_index: int

    _finishing: bool

    _search_index: List[int]

    _oi: Optional[OutputInfo]

    def __init__(
        self, window_sz2=DEFAULT_WINDOW_SZ2, lookahead_sz2=DEFAULT_LOOKAHEAD_SZ2
    ):
        _validate_window_sz2(window_sz2)
        _validate_lookahead_sz2(lookahead_sz2, window_sz2)

        self._window_sz2 = window_sz2
        self._lookahead_sz2 = lookahead_sz2

        self._input_offset = (1 << self._window_sz2)
        self._input_buffer_size = (1 << self._window_sz2)
        self._lookahead_size = (1 << self._lookahead_sz2)

        self._search_index = [0] * (2 << self._window_sz2)

        self._state_handlers = {
            State.FILLED: self._do_indexing,
            State.SEARCH: self._step_search,
            State.YIELD_TAG_BIT: self._yield_tag_bit,
            State.YIELD_LITERAL: self._yield_literal,
            State.YIELD_BR_INDEX: self._yield_br_index,
            State.YIELD_BR_LENGTH: self._yield_br_length,
            State.SAVE_BACKLOG: self._save_backlog,
        }

        self._oi = None

        self.reset()

    @property
    def max_output_size(self):
        return 1 << self._window_sz2

    def reset(self):
        self._buffer = bytearray(2 << self._window_sz2)
        self._input_size = 0
        self._state = State.NOT_FULL
        self._match_scan_index = 0
        self._bit_index = 0x80
        self._current_byte = 0x00
        self._match_length = 0
        self._outgoing_bits = 0x0000
        self._outgoing_bits_count = 0
        self._finishing = False

    def sink(self, in_buf: bytes) -> Tuple[bool, int]:
        if self._finishing:
            raise RuntimeError("Can't sink more content when finishing")

        if self._state != State.NOT_FULL:
            raise RuntimeError("Can't sink more content before processing is done")

        write_offset = self._input_offset + self._input_size
        rem = self._input_buffer_size - self._input_size
        size = len(in_buf)
        if rem < size:
            size = rem

        self._buffer[write_offset:write_offset + size] = in_buf[:size]
        self._input_size += size
        if size == rem:
            self._state = State.FILLED

        return False, size

    def poll(self, out_buf_size: Optional[int] = None) -> Tuple[bool, bytes]:
        if out_buf_size is None:
            out_buf_size = self.max_output_size

        self._oi = OutputInfo(out_buf_size)

        while True:
            in_state = self._state
            if self._state in (State.NOT_FULL, State.DONE):
                return False, self._get_output()

            if self._state == State.FLUSH_BITS:
                self._state = self._flush_bit_buffer()
                return False, self._get_output()

            handler = self._state_handlers.get(self._state)
            if handler:
                self._state = handler()
            else:
                raise RuntimeError("Decoder poll unknown error")

            if self._state == in_state and self._oi.output_size == out_buf_size:
                return True, self._get_output()

    def finish(self) -> bool:
        self._finishing = True
        if self._state == State.NOT_FULL:
            self._state = State.FILLED
        return self._state == State.DONE

    def _get_output(self) -> bytes:
        try:
            return self._oi.get_output()
        finally:
            self._oi = None

    def _do_indexing(self) -> State:
        last = [-1] * 256
        end = self._input_offset + self._input_size
        for i in range(end):
            v = self._buffer[i]
            lv = last[v]
            self._search_index[i] = lv
            last[v] = i
        return State.SEARCH

    def _step_search(self) -> State:
        msi = self._match_scan_index
        fin = self._finishing
        if msi > self._input_size - (1 if fin else self._lookahead_size):
            return State.FLUSH_BITS if fin else State.SAVE_BACKLOG

        end = self._input_offset + msi
        start = end - self._input_buffer_size
        max_possible = self._lookahead_size
        if self._input_size - msi < self._lookahead_size:
            max_possible = self._input_size - msi

        match_pos = self._find_longest_match(start, end, max_possible)
        if match_pos is None:
            self._match_scan_index += 1
            self._match_length = 0
        else:
            self._match_pos, self._match_length = match_pos
            assert self._match_pos <= (1 << self._window_sz2)

        return State.YIELD_TAG_BIT

    def _yield_tag_bit(self) -> State:
        if self._can_take_byte():
            if self._match_length == 0:
                self._add_tag_bit(HEATSHRINK_LITERAL_MARKER)
                return State.YIELD_LITERAL
            else:
                self._add_tag_bit(HEATSHRINK_BACKREF_MARKER)
                self._outgoing_bits = self._match_pos - 1
                self._outgoing_bits_count = self._window_sz2
                return State.YIELD_BR_INDEX
        else:
            return State.YIELD_TAG_BIT

    def _yield_literal(self) -> State:
        if self._can_take_byte():
            self._push_literal_byte()
            return State.SEARCH
        else:
            return State.YIELD_LITERAL

    def _yield_br_index(self) -> State:
        if self._can_take_byte():
            if self._push_outgoing_bits() > 0:
                return State.YIELD_BR_INDEX
            else:
                self._outgoing_bits = self._match_length - 1
                self._outgoing_bits_count = self._lookahead_sz2
                return State.YIELD_BR_LENGTH
        else:
            return State.YIELD_BR_INDEX

    def _yield_br_length(self) -> State:
        if self._can_take_byte():
            if self._push_outgoing_bits() > 0:
                return State.YIELD_BR_LENGTH
            else:
                self._match_scan_index += self._match_length
                self._match_length = 0
                return State.SEARCH
        else:
            return State.YIELD_BR_LENGTH

    def _save_backlog(self) -> State:
        rem = self._input_buffer_size - self._match_scan_index
        shift_sz = self._input_buffer_size + rem
        src = self._input_buffer_size - rem
        self._buffer[:shift_sz] = self._buffer[src:src + shift_sz]
        self._match_scan_index = 0
        self._input_size -= src
        return State.NOT_FULL

    def _flush_bit_buffer(self) -> State:
        if self._bit_index == 0x80:
            return State.DONE
        elif self._can_take_byte():
            self._oi.buf[self._oi.output_size] = self._current_byte
            self._oi.output_size += 1
            return State.DONE
        else:
            return State.FLUSH_BITS

    def _add_tag_bit(self, tag: int):
        self._push_bits(1, tag)

    def _can_take_byte(self) -> bool:
        return self._oi.output_size < self._oi.buf_size

    def _find_longest_match(self, start: int, end: int, maxlen: int) -> Optional[Tuple[int, int]]:
        match_maxlen = 0
        match_index = 0
        pos = self._search_index[end]

        while pos - start >= 0:
            ml = 0
            if self._buffer[pos + match_maxlen] != self._buffer[end + match_maxlen]:
                pos = self._search_index[pos]
                continue

            for ml in range(1, maxlen + 1):
                if ml == maxlen or self._buffer[pos + ml] != self._buffer[end + ml]:
                    break

            if ml > match_maxlen:
                match_maxlen = ml
                match_index = pos
                if ml == maxlen:
                    break

            pos = self._search_index[pos]

        break_even_point = 1 + self._window_sz2 + self._lookahead_sz2
        if match_maxlen > (break_even_point // 8):
            return end - match_index, match_maxlen

        return None

    def _push_outgoing_bits(self) -> int:
        if self._outgoing_bits_count > 8:
            count = 8
            bits = (self._outgoing_bits >> (self._outgoing_bits_count - 8)) & 0xFF
        else:
            count = self._outgoing_bits_count
            bits = self._outgoing_bits & 0xFF

        if count > 0:
            self._push_bits(count, bits)
            self._outgoing_bits_count -= count

        return count

    def _push_bits(self, count: int, bits: int):
        assert count <= 8
        if count == 8 and self._bit_index == 0x80:
            self._oi.buf[self._oi.output_size] = bits
            self._oi.output_size += 1
        else:
            for i in range(count - 1, -1, -1):
                if bits & (1 << i):
                    self._current_byte |= self._bit_index
                self._bit_index >>= 1
                if self._bit_index == 0x00:
                    self._bit_index = 0x80
                    self._oi.buf[self._oi.output_size] = self._current_byte
                    self._oi.output_size += 1
                    self._current_byte = 0x00

    def _push_literal_byte(self):
        processed_offset = self._match_scan_index - 1
        input_offset = self._input_offset + processed_offset
        c = self._buffer[input_offset]
        self._push_bits(8, c)
