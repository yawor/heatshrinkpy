import os
import time

import heatshrink2

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
PLAIN_FILE_PATH = os.path.join(DATA_DIR, 'plain_file.txt')
COMPRESSED_FILE_PATH = os.path.join(DATA_DIR, 'compressed_file.txt')


def print_block(msg, size=50):
    sep = '=' * size
    print(sep)
    print(msg)
    print(sep)


def timed(func):
    """Wraps function func and prints timing information.

    Timing is from when the function from function beginning to end in
    seconds.

    """

    def wrap(*args):
        start_time = time.time()
        func(*args)
        elapsed = time.time() - start_time
        print('==> {} seconds elapsed'.format(elapsed))

    return wrap


def run_benchmarks():
    print_block('Encode benchmarks')

    with open(PLAIN_FILE_PATH, 'rb') as plain_file:
        with heatshrink2.open(COMPRESSED_FILE_PATH, 'wb') as compressed_file:
            timed_write = timed(compressed_file.write)

            print('*** Writing 10,000 bytes ***')
            timed_write(plain_file.read(10000))
            print('*** Writing 100,000 bytes ***')
            timed_write(plain_file.read(100000))
            print('*** Writing 1,000,000 bytes ***')
            timed_write(plain_file.read(1000000))
            print('*** Writing rest of the file ***')
            timed_write(plain_file.read())
            print('==> Wrote {} bytes'.format(plain_file.tell()))

    print_block('Decode benchmarks')

    with heatshrink2.open(COMPRESSED_FILE_PATH, 'rb') as compressed_file:
        timed_read = timed(compressed_file.read)
        print('*** Reading 10,000 bytes ***')
        timed_read(10000)
        print('*** Reading 100,000 bytes ***')
        timed_read(100000)
        print('*** Reading 1,000,000 bytes ***')
        timed_read(1000000)
        print('*** Reading rest of the file ***')
        timed_read()
        print('<== Read {} bytes'.format(compressed_file.tell()))


if __name__ == '__main__':
    run_benchmarks()
