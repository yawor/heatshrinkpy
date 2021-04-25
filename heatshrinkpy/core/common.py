from .consts import *


class OutputInfo:
    def __init__(self, out_buf_size):
        self.buf = bytearray(out_buf_size)
        self.buf_size = out_buf_size
        self.output_size = 0

    def get_output(self) -> bytes:
        return bytes(self.buf[:self.output_size])


def _validate_input_buffer_size(value):
    if not (value > 0):
        raise ValueError('input_buffer_size must be > 0')


def _validate_window_sz2(value):
    if not (MIN_WINDOW_SZ2 <= value <= MAX_WINDOW_SZ2):
        raise ValueError(
            f'window_sz2 must be {MIN_WINDOW_SZ2} <= number <= {MAX_WINDOW_SZ2}')


def _validate_lookahead_sz2(value, window_sz2):
    if not (MIN_LOOKAHEAD_SZ2 <= value <= window_sz2):
        raise ValueError(
            f'lookahead_sz2 must be {MIN_LOOKAHEAD_SZ2} <= number <= {window_sz2}')
