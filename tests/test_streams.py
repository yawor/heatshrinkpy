import sys
import array
import functools
import io
import os
import unittest

from heatshrinkpy.streams import HeatshrinkFile

from .constants import TEXT
from .constants import COMPRESSED
from .utils import TestUtilsMixin
from .utils import random_string

TEST_FILENAME = 'test_{}_tmp'.format(os.getpid())


class HeatshrinkFileTest(TestUtilsMixin, unittest.TestCase):

    def setUp(self):
        self.fp = HeatshrinkFile(TEST_FILENAME, 'wb')

    def tearDown(self):
        if self.fp:
            self.fp.close()

        # Cleanup temporary file
        if os.path.exists(TEST_FILENAME):
            os.unlink(TEST_FILENAME)

    def test_open_missing_file(self):
        self.assertRaises(IOError, HeatshrinkFile, 'does_not_exist.txt')

    def test_mode_attribute_is_readonly(self):
        self.assertEqual(self.fp.mode, 'wb')
        with self.assertRaises(AttributeError):
            self.fp.mode = 'rb'

    def test_different_compress_params(self):
        # List of a tuple containing (window_sz2, lookahead_sz2)
        encode_params = [
            (8, 3),
            (11, 6),
            (4, 3),
            (15, 9),
        ]
        encoded = []

        for window_sz2, lookahead_sz2 in encode_params:
            kwargs = {
                'window_sz2': window_sz2,
                'lookahead_sz2': lookahead_sz2
            }

            with io.BytesIO() as dst:
                with HeatshrinkFile(dst, 'wb', **kwargs) as fp:
                    fp.write(TEXT)

                encoded.append(dst.getvalue())

        # Ensure that all have different values
        self.assertEqual(len(encoded), len(set(encoded)))

    def test_invalid_compress_params_values(self):
        datas = [
            (3, 4, 'window_sz2 must be 4 <= number <= 15'),
            (16, 4, 'window_sz2 must be 4 <= number <= 15'),
            (11, 2, 'lookahead_sz2 must be 3 <= number <= 11'),
            (8, 9, 'lookahead_sz2 must be 3 <= number <= 8')
        ]

        for window_sz2, lookahead_sz2, message in datas:
            with io.BytesIO() as dst:
                with self.assertRaises(ValueError) as cm:
                    HeatshrinkFile(dst,
                                   'wb',
                                   window_sz2=window_sz2,
                                   lookahead_sz2=lookahead_sz2)

                self.assertEqual(str(cm.exception), message)

    def test_invalid_modes(self):
        data = io.BytesIO()

        for mode in ['a+', 'w+', 'ab', 'r+', 'U', 'x', 'xb']:
            with self.assertRaisesRegex(ValueError, '^Invalid mode: .*$'):
                HeatshrinkFile(data, mode=mode)

    def test_round_trip(self):
        write_str = b'Testing\nAnd Stuff'

        self.fp.write(write_str)
        self.fp.close()

        self.fp = HeatshrinkFile(TEST_FILENAME)
        self.assertEqual(self.fp.read(), write_str)

    def test_with_large_files(self):
        test_sizes = [1000, 10000, 100000]

        for size in test_sizes:
            contents = random_string(size)
            contents = contents.encode('ascii')

            with HeatshrinkFile(TEST_FILENAME, mode='wb') as fp:
                fp.write(contents)

            with HeatshrinkFile(TEST_FILENAME) as fp:
                read_str = fp.read()

            self.assertEqual(read_str, contents)

    def test_buffered_large_files(self):
        test_sizes = [1000, 10000, 100000]

        for size in test_sizes:
            contents = random_string(size)
            contents = contents.encode('ascii')

            with HeatshrinkFile(TEST_FILENAME, mode='wb') as fp:
                fp.write(contents)

            with HeatshrinkFile(TEST_FILENAME) as fp:
                # Read small buffer sizes
                read_func = functools.partial(fp.read, 512)
                read_str = b''.join([s for s in iter(read_func, b'')])

            self.assertEqual(read_str, contents)

    def test_with_file_object(self):
        plain_file = open(TEST_FILENAME, 'wb')

        with HeatshrinkFile(plain_file, mode='wb') as encoded_file:
            encoded_file.write(TEXT)

        self.assertTrue(encoded_file.closed)
        # Shouldn't close the file, as it doesn't own it
        self.assertFalse(plain_file.closed)
        plain_file.close()

        with open(TEST_FILENAME, 'rb') as fp:
            self.assertTrue(len(fp.read()) > 0)

    def test_closed_true_when_file_closed(self):
        self.assertFalse(self.fp.closed)
        self.fp.close()
        self.assertTrue(self.fp.closed)

    def test_context_manager(self):
        with HeatshrinkFile(TEST_FILENAME, mode='wb') as fp:
            fp.write(b'Testing\n')
            fp.write(b'One, two...')

        self.assertTrue(fp.closed)

    def test_operations_on_closed_file(self):
        self.fp.close()
        self.assertRaises(ValueError, self.fp.write, b'abcde')
        self.assertRaises(ValueError, self.fp.seek, 0)

        self.fp = HeatshrinkFile(TEST_FILENAME, 'rb')
        self.fp.close()
        self.assertRaises(ValueError, self.fp.read)
        self.assertRaises(ValueError, self.fp.seek, 0)

    def test_cannot_write_in_read_mode(self):
        # Write some junk data
        self.fp.write(b'abcde')
        self.fp.close()

        self.fp = HeatshrinkFile(TEST_FILENAME)
        self.assertTrue(self.fp.readable())
        self.assertFalse(self.fp.writable())
        self.assertRaises(IOError, self.fp.write, b'abcde')

    def test_cannot_read_in_write_mode(self):
        self.assertTrue(self.fp.writable())
        self.assertFalse(self.fp.readable())
        self.assertRaises(IOError, self.fp.read)

    #################
    # Seeking
    #################
    def test_seeking_forwards(self):
        contents = TEXT

        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            self.assertEqual(fp.read(100), contents[:100])
            fp.seek(150)  # Move 50 forwards
            self.assertEqual(fp.read(100), contents[150:250])

    def test_seeking_backwards(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            contents = fp.read(100)
            fp.seek(0)
            self.assertEqual(fp.read(100), contents)

    def test_seeking_forward_from_current(self):
        contents = TEXT

        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            self.assertEqual(fp.read(100), contents[:100])
            fp.seek(50, io.SEEK_CUR)  # Move 50 forwards
            self.assertEqual(fp.read(100), contents[150:250])

    def test_seeking_backwards_from_current(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            contents = fp.read()
            fp.seek(-100, io.SEEK_CUR)
            self.assertEqual(fp.read(), contents[-100:])

    def test_seeking_beyond_beginning_from_current(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            self.assertRaises(IOError, fp.seek, -100, io.SEEK_CUR)

    def test_seeking_from_end(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            self.assertEqual(fp.read(100), TEXT[:100])
            seeked_pos = fp.seek(-100, io.SEEK_END)
            self.assertEqual(seeked_pos, len(TEXT) - 100)
            self.assertEqual(fp.read(100), TEXT[-100:])

    def test_seeking_from_end_beyond_beginning(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            # Go to end to get size
            size = fp.seek(0, io.SEEK_END)
            # Go to beginning
            self.assertNotRaises(fp.seek, -size, io.SEEK_END)
            # One before beginning
            self.assertRaises(IOError, fp.seek, -size - 1, io.SEEK_END)

    def test_tell(self):
        with io.BytesIO() as dst:
            with HeatshrinkFile(dst, mode='wb') as fp:
                bytes_written = fp.write(b'abcde')
                self.assertEqual(fp.tell(), bytes_written)

            dst.seek(0)  # Reset

            with HeatshrinkFile(dst) as fp:
                fp.read(3)
                self.assertEqual(fp.tell(), 3)

    def test_peek(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            pdata = fp.peek()
            self.assertNotEqual(len(pdata), 0)
            self.assertTrue(TEXT.startswith(pdata))
            self.assertEqual(fp.read(), TEXT)

    #################
    # Reading
    #################
    def test_read_whole_file(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            self.assertEqual(fp.read(), TEXT)

    def test_read_buffered(self):
        read_size = 128
        offset = 0

        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            read_buf = functools.partial(fp.read, read_size)

            for i, contents in enumerate(iter(read_buf, b'')):
                offset = read_size * i
                self.assertEqual(contents, TEXT[offset:offset + read_size])

    def test_read_one_char(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            for c in TEXT:
                self.assertEqual(fp.read(1), bytes([c]))

    def test_read1(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            blocks = [buf for buf in iter(fp.read1, b'')]
            self.assertEqual(b''.join(blocks), TEXT)
            self.assertEqual(fp.read1(), b'')

    def test_read1_0(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            self.assertEqual(fp.read1(0), b'')

    def test_readinto(self):
        with io.BytesIO() as dst:
            with HeatshrinkFile(dst, mode='wb') as fp:
                fp.write(b'abcde')

            dst.seek(0)  # Reset

            with HeatshrinkFile(dst) as fp:
                a = array.array('b', b'x' * 10)  # Fill with junk
                n = fp.readinto(a)
                self.assertEqual(b'abcde', a.tobytes()[:n])

    def test_readline(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            lines = TEXT.splitlines()

            # Could also use zip
            for i, line in enumerate(iter(fp.readline, b'')):
                self.assertEqual(line, lines[i] + b'\n')

    def test_readline_iterator(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            lines = TEXT.splitlines()

            for file_line, original_line in zip(fp, lines):
                self.assertEqual(file_line, original_line + b'\n')

    def test_readlines(self):
        with HeatshrinkFile(io.BytesIO(COMPRESSED)) as fp:
            lines = fp.readlines()
            self.assertEqual(b''.join(lines), TEXT)

    #################
    # Writing
    #################
    def test_write_buffered(self):
        BUFFER_SIZE = 16
        # BytesIO makes it easy to buffer
        text_buf = io.BytesIO(TEXT)

        with io.BytesIO() as dst:
            with HeatshrinkFile(dst, mode='wb') as fp:
                while True:
                    chunk = text_buf.read(BUFFER_SIZE)

                    if not chunk:
                        break

                    fp.write(chunk)

            self.assertEqual(dst.getvalue(), COMPRESSED)

    def test_remaining_data_flushed_on_close(self):
        with io.BytesIO() as dst:
            fp = HeatshrinkFile(dst, mode='wb')
            fp.write(TEXT)
            # Not flusshed
            self.assertEqual(len(dst.getvalue()), 0)
            # Flush
            fp.close()
            self.assertTrue(len(dst.getvalue()) > 0)

    def test_writelines(self):
        with io.BytesIO(TEXT) as fp:
            lines = fp.readlines()

        with io.BytesIO() as dst:
            with HeatshrinkFile(dst, mode='wb') as fp:
                fp.writelines(lines)

            self.assertEqual(dst.getvalue(), COMPRESSED)
