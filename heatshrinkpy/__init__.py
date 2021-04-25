import sys
import argparse
import builtins

from . import core
from .core import encode
from .core import decode
from .core import encode as compress
from .core import decode as decompress
from .streams import open
from .streams import HeatshrinkFile
from .streams import HeatshrinkFile as EncodedFile
from .version import __version__


def _do_compress(args):
    with open(args.outfile,
              'wb',
              window_sz2=args.window_sz2,
              lookahead_sz2=args.lookahead_sz2) as fout:
        with builtins.open(args.infile, 'rb') as fin:
            fout.write(fin.read())


def _do_decompress(args):
    with builtins.open(args.outfile, 'wb') as fout:
        with open(args.infile,
                  'rb',
                  window_sz2=args.window_sz2,
                  lookahead_sz2=args.lookahead_sz2) as fin:
            fout.write(fin.read())


def _main() -> object:
    parser = argparse.ArgumentParser(
        description='Compression using the Heatshrink algorithm.')

    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('--version',
                        action='version',
                        version=__version__,
                        help='Print version information and exit.')

    # Workaround to make the subparser required in Python 3.
    subparsers = parser.add_subparsers(title='subcommands',
                                       dest='subcommand')
    subparsers.required = True

    # Compress subparser.
    subparser = subparsers.add_parser('compress', description='Compression.')
    subparser.add_argument(
        '-w', '--window-sz2',
        type=int,
        default=core.DEFAULT_WINDOW_SZ2,
        help='Base-2 log of LZSS sliding window size (default: %(default)s).')
    subparser.add_argument(
        '-l', '--lookahead-sz2',
        type=int,
        default=core.DEFAULT_LOOKAHEAD_SZ2,
        help=('Number of bits used for back-reference lengths '
              '(default: %(default)s).'))
    subparser.add_argument('infile', help='File to compress.')
    subparser.add_argument('outfile', help='Compressed file.')
    subparser.set_defaults(func=_do_compress)

    # Decompress subparser.
    subparser = subparsers.add_parser('decompress', description='Decompression.')
    subparser.add_argument(
        '-w', '--window-sz2',
        type=int,
        default=core.DEFAULT_WINDOW_SZ2,
        help='Base-2 log of LZSS sliding window size (default: %(default)s).')
    subparser.add_argument(
        '-l', '--lookahead-sz2',
        type=int,
        default=core.DEFAULT_LOOKAHEAD_SZ2,
        help=('Number of bits used for back-reference lengths '
              '(default: %(default)s).'))
    subparser.add_argument('infile', help='File to decompress.')
    subparser.add_argument('outfile', help='Decompressed file.')
    subparser.set_defaults(func=_do_decompress)

    args = parser.parse_args()

    if args.debug:
        args.func(args)
    else:
        try:
            args.func(args)
        except BaseException as e:
            sys.exit('error: ' + str(e))
