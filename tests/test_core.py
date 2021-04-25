import array
import unittest

import heatshrinkpy as heatshrink
from heatshrinkpy.core import Encoder
from heatshrinkpy.core import Reader
from heatshrinkpy.core import Writer

from .constants import TEXT
from .utils import TestUtilsMixin
from .utils import random_string


class InternalEncodersTest(TestUtilsMixin, unittest.TestCase):
    """Tests for the Writer and Reader classes.

    """

    def test_checks_window_sz2_type(self):
        for cls in (Writer, Reader):
            self.assertRaises(TypeError, cls, window_sz2='a string')
            self.assertRaises(TypeError, cls, window_sz2=lambda x: None)

    def test_checks_window_sz2_within_limits(self):
        for cls in (Writer, Reader):
            self.assertRaises(ValueError, cls, window_sz2=3)
            self.assertRaises(ValueError, cls, window_sz2=16)
            self.assertNotRaises(cls, window_sz2=5)
            self.assertNotRaises(cls, window_sz2=14)

    # TODO: These kind of tests might be redundant
    def test_checks_lookahead_sz2_type(self):
        for cls in (Writer, Reader):
            self.assertRaises(TypeError, cls, lookahead_sz2='a string')
            self.assertRaises(TypeError, cls, lookahead_sz2=lambda x: None)

    def test_checks_lookahead_sz2_within_limits(self):
        for cls in (Writer, Reader):
            self.assertRaises(ValueError, cls, lookahead_sz2=1)
            self.assertRaises(ValueError, cls, lookahead_sz2=16)
            self.assertNotRaises(cls, lookahead_sz2=4)
            self.assertNotRaises(cls, lookahead_sz2=10)


class EncoderTest(TestUtilsMixin, unittest.TestCase):
    """Test encoder state machine.

    """

    def setUp(self):
        self.reader = Reader()
        self.writer = Writer()
        self.encoders = [Encoder(e) for e in [self.reader, self.writer]]

    def test_fill_accepted_types(self):
        for encoder in self.encoders:
            self.assertNotRaises(encoder.fill, b'abcde')
            self.assertNotRaises(encoder.fill, u'abcde'.encode('utf8'))
            self.assertNotRaises(encoder.fill, bytearray([1, 2, 3]))
            self.assertNotRaises(encoder.fill, array.array('B', [1, 2, 3]))
            self.assertNotRaises(encoder.fill, [1, 2, 3])

            self.assertRaises(TypeError, encoder.fill, memoryview(b'abcde'))
            self.assertRaises(TypeError, encoder.fill, u'abcde')
            # Obvious fail cases
            self.assertRaises(TypeError, encoder.fill, lambda x: x)
            self.assertRaises(TypeError, encoder.fill, True)

    def test_finished_true_after_finish(self):
        for encoder in self.encoders:
            self.assertTrue(not encoder.finished)
            encoder.finish()
            self.assertTrue(encoder.finished)

    def test_operation_after_finish_fails(self):
        for encoder in self.encoders:
            encoder.fill(b'abcde')
            encoder.finish()
            self.assertRaises(ValueError, encoder.fill, b'abcde')
            self.assertRaises(ValueError, encoder.finish)

    def test_fill_doesnt_flush_small_values(self):
        encoder = Encoder(self.writer)
        # Pass a small value, this wont cause the encoder
        # to actually do anything
        encoded = encoder.fill(b'abcde')
        self.assertTrue(len(encoded) == 0)
        # This should clear the encoder completely
        encoded = encoder.finish()
        self.assertTrue(len(encoded) > 0)


class CompressFunctionTest(TestUtilsMixin, unittest.TestCase):
    """Tests for the core.compress function.

    """

    def setUp(self):
        self.compressed = heatshrink.compress(b'abcde')

    def test_compressed_size(self):
        self.assertEqual(len(self.compressed), 6)

    def test_compressed_bytes(self):
        self.assertEqual(self.compressed, b'\xb0\xd8\xacvK(')

    def test_compress_with_window_sz2(self):
        compressed = heatshrink.compress(b'abcde', window_sz2=8)
        # FIXME: Prove that this setting changes output
        self.assertEqual(compressed, b'\xb0\xd8\xacvK(')

    def test_compress_with_lookahead_sz2(self):
        compressed = heatshrink.compress(b'abcde', lookahead_sz2=3)
        self.assertEqual(compressed, b'\xb0\xd8\xacvK(')

    def test_different_params_yield_different_output(self):
        string = b'A string with stuff in it'
        self.assertNotEqual(heatshrink.compress(string, window_sz2=8),
                            heatshrink.compress(string, window_sz2=11))
        self.assertNotEqual(heatshrink.compress(string, lookahead_sz2=4),
                            heatshrink.compress(string, lookahead_sz2=8))


class DecompressFunctionTest(TestUtilsMixin, unittest.TestCase):
    """Tests for the core.decompress function.

    """

    def test_returns_string(self):
        self.assertIsInstance(heatshrink.decompress(b'abcde'), bytes)

    def test_decompress_with_window_sz2(self):
        decompressed = heatshrink.decompress(b'\xb0\xd8\xacvK(', window_sz2=11)
        self.assertEqual(decompressed, b'abcde')

    def test_decompress_with_lookahead_sz2(self):
        decompressed = heatshrink.decompress(b'\xb0\xd8\xacvK(', lookahead_sz2=3)
        self.assertEqual(decompressed, b'abcde')


class CompressDecompressTest(TestUtilsMixin, unittest.TestCase):
    """Tests assertion that data passed through the compress and then the
    decompress functions with the same parameters will be equal to the
    original data.

    """

    def test_round_trip(self):
        compressed = heatshrink.compress(b'a string')
        self.assertEqual(heatshrink.decompress(compressed), b'a string')

    def test_with_a_paragraph(self):
        compressed = heatshrink.compress(TEXT)
        self.assertEqual(heatshrink.decompress(compressed), TEXT)

    def test_with_large_strings(self):
        test_sizes = [1000, 10000, 100000]

        for size in test_sizes:
            contents = random_string(size).encode('ascii')
            decompressed = heatshrink.decompress(heatshrink.compress(contents))
            self.assertEqual(decompressed, contents)
