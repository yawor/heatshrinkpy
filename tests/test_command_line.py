import os
import unittest
from unittest.mock import patch
from io import StringIO

import heatshrinkpy


def read_file(filename):
    with open(filename, 'rb') as fin:
        return fin.read()


class HeatshrinkCommandLineTest(unittest.TestCase):

    def test_command_line_compress(self):
        argv = [
            'heatshrinkpy',
            'compress',
            'tests/files/foo.txt',
            'foo.hs'
        ]

        if os.path.exists('foo.hs'):
            os.remove('foo.hs')

        with patch('sys.argv', argv):
            heatshrinkpy._main()

        self.assertEqual(read_file('foo.hs'),
                         read_file('tests/files/foo.hs'))

    def test_command_line_decompress(self):
        argv = [
            'heatshrinkpy',
            'decompress',
            'tests/files/foo.hs',
            'foo.txt'
        ]

        if os.path.exists('foo.txt'):
            os.remove('foo.txt')

        with patch('sys.argv', argv):
            heatshrinkpy._main()

        self.assertEqual(read_file('foo.txt'),
                         read_file('tests/files/foo.txt'))

    def test_command_line_compress_parameters(self):
        argv = [
            'heatshrinkpy',
            'compress',
            '-w', '8',
            '-l', '5',
            'tests/files/foo.txt',
            'foo-8-5.hs'
        ]

        if os.path.exists('foo-8-5.hs'):
            os.remove('foo-8-5.hs')

        with patch('sys.argv', argv):
            heatshrinkpy._main()

        self.assertEqual(read_file('foo-8-5.hs'),
                         read_file('tests/files/foo-8-5.hs'))

    def test_command_line_decompress_parameters(self):
        argv = [
            'heatshrinkpy',
            'decompress',
            '-w', '8',
            '-l', '5',
            'tests/files/foo-8-5.hs',
            'foo-8-5.txt'
        ]

        if os.path.exists('foo-8-5.txt'):
            os.remove('foo-8-5.txt')

        with patch('sys.argv', argv):
            heatshrinkpy._main()

        self.assertEqual(read_file('foo-8-5.txt'),
                         read_file('tests/files/foo.txt'))


if __name__ == '__main__':
    unittest.main()
