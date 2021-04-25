import errno
import io
import os
import builtins

import heatshrinkpy.core as core

_READ_BUFFER_SIZE = io.DEFAULT_BUFFER_SIZE


class _DecompressReader(io.RawIOBase):
    """Adapts the decompressor API to a RawIOBase reader API.

    This class is similar to the one found in the internal python
    decompression modules. See github for more details:
    https://github.com/python/cpython/blob/3.6/Lib/_compression.py#L33

    """

    def __init__(self, fp, reader_factory, **reader_args):
        self._fp = fp
        self._eof = False
        # Position in file (decompressed)
        self._pos = 0
        # Decompressed data
        self._buf = b''
        self._buf_offset = 0

        # Set to size of decompressed stream once it is known
        self._size = -1

        self._reader_factory = reader_factory
        self._reader_args = reader_args

        self._decoder = self._new_decoder()

    def _new_decoder(self):
        """Create a new decoder using the reader factory and args."""
        reader = self._reader_factory(**self._reader_args)
        
        return core.Encoder(reader)

    def close(self):
        self._decoder = None
        # Don't close self._fp directly because we don't own it.
        return super(_DecompressReader, self).close()

    def readable(self):
        return True

    def seekable(self):
        return self._fp.seekable()

    def readinto(self, b):
        buf = self.read(len(b))
        b[:len(buf)] = buf

        return len(buf)

    def _refill(self):
        """Refill internal decompress buffer with file data.

        Throws a EOFError when all data has been read and the decoder
        has been finalized.

        """

        # Concecutive calls should be ignored
        if self._decoder.finished:
            raise EOFError

        self._buf_offset = 0

        raw_chunk = self._fp.read(_READ_BUFFER_SIZE)

        if raw_chunk:
            self._buf = self._decoder.fill(raw_chunk)
        else:
            # Finalize internal decoder.
            self._buf = self._decoder.finish()

            raise EOFError

    def read(self, size=-1):
        if size < 0:
            return self.readall()

        if not size or self._eof:
            return b''

        if self._buf_offset >= len(self._buf):
            try:
                self._refill()
            except EOFError:
                self._eof = True
                self._size = self._pos

        # TODO: Clean up
        data = self._buf[self._buf_offset:self._buf_offset + size]
        self._buf_offset += size
        self._pos += len(data)

        return data

    def _rewind(self):
        """Rewind the file to the beginning of the data stream.

        """

        self._fp.seek(0)
        self._eof = False
        self._pos = 0
        self._buf = b''
        self._buf_offset = 0
        # Restart the decoder from the beginning
        self._decoder = self._new_decoder()

    def seek(self, offset, whence=io.SEEK_SET):
        # Recalculate offset as an absolute file position.
        if whence == io.SEEK_SET:
            pass
        elif whence == io.SEEK_CUR:
            offset += self._pos
        elif whence == io.SEEK_END:
            if self._size < 0:
                # Finish reading the file
                while self.read(io.DEFAULT_BUFFER_SIZE):
                    pass

            offset += self._size
        else:
            raise ValueError(f'Invalid value for whence: {whence}')

        if offset < 0:
            raise IOError(f'[Error {errno.EINVAL}] {os.strerror(errno.EINVAL)}')

        # Make it so that offset is the number of bytes to skip forward.
        if offset < self._pos:
            self._rewind()
        else:
            offset -= self._pos

        # Read and discard data until we reach the desired position
        while offset > 0:
            data = self.read(min(io.DEFAULT_BUFFER_SIZE, offset))

            if not data:
                break

            offset -= len(data)

        return self._pos

    def tell(self):
        return self._pos


_MODE_CLOSED = 0
_MODE_READ = 1
_MODE_WRITE = 2


class HeatshrinkFile(io.BufferedIOBase):

    def __init__(self, filename, mode='rb', **compress_options):
        """Open a heatshrink LZSS encoded file.

        If filename is a str or bytes object, it gives the name of the
        file to be opened. Otherwise, it should be a file-like object,
        which will be used to read or write the compressed data.

        mode can be 'rb for reading (default) or 'wb' for
        (over)writing.  'r' and 'w' will be converted to to 'rb' and
        'wb' respectively.

        """

        self._fp = None
        # Should the file be closed by us?
        self._close_fp = False
        self._mode = _MODE_CLOSED

        if mode in ('', 'r', 'rb'):
            self._mode_str = 'rb'
            self._mode = _MODE_READ
        elif mode in ('w', 'wb'):
            self._mode_str = 'wb'
            self._mode = _MODE_WRITE
        else:
            raise ValueError("Invalid mode: '{!r}'".format(mode))

        if isinstance(filename, (str, bytes)):
            self._fp = builtins.open(filename, self._mode_str)
            # We opened the file, we need to close it
            self._close_fp = True
        elif hasattr(filename, 'read') or hasattr(filename, 'write'):
            # Implements the file protocol
            self._fp = filename
        else:
            raise TypeError('filename must be an str, bytes or a file-like object')

        if self._mode == _MODE_READ:
            raw = _DecompressReader(self._fp, core.Reader, **compress_options)
            self._buffer = io.BufferedReader(raw)
        else:
            writer = core.Writer(**compress_options)
            self._encoder = core.Encoder(writer)
            # File seek position
            self._pos = 0

        # The file name. Defaults to None
        self.name = getattr(self._fp, 'name', None)

    @property
    def mode(self):
        return self._mode_str

    def seekable(self):
        """Return whether the file supports seeking.

        """

        return self.readable() and self._buffer.seekable()

    def readable(self):
        """Return whether the file was opened for reading.

        """

        return self._mode == _MODE_READ

    def writable(self):
        """Return whether the file was opened for writing.

        """

        return self._mode == _MODE_WRITE

    def _check_not_closed(self):
        """Throws a ValueError if the file has been closed.

        """

        if self.closed:
            raise ValueError('I/O operation on closed file')

    def _check_can_read(self):
        """Throws an io.UnsupportedOperation if the file can not be read.

        """

        if not self.readable():
            raise io.UnsupportedOperation('File not open for reading')

    def _check_can_write(self):
        """Throws an io.UnsupportedOperation if the file can not be written.

        """

        if not self.writable():
            raise io.UnsupportedOperation('File not open for writing')

    def _check_can_seek(self):
        """Throws an io.UnsupportedOperation if the file can not be seeeked.

        """

        if not self.readable():
            raise io.UnsupportedOperation(
                'Seeking is only supported on files open for reading')

        if not self.seekable():
            raise io.UnsupportedOperation(
                'The underlying file object does not support seeking.')

    def close(self):
        """Flush and close the file.

        May be called more than once without error. Once the file is
        closed, any other operation on it will raise a ValueError.

        """

        # Flush and finish the decoder.
        if self._mode == _MODE_READ:
            self._buffer.close()
        elif self._mode == _MODE_WRITE:
            self._fp.write(self._encoder.finish())
            self._encoder = None

        try:
            # Actually close the internal file pointer.
            if self._close_fp:
                self._fp.close()
        finally:
            self._fp = None
            self._close_fp = False
            self._mode = _MODE_CLOSED

    @property
    def closed(self):
        """True if this file is closed.

        """

        return self._mode == _MODE_CLOSED

    def fileno(self):
        """Return the file descriptor for tthe underlying file.

        """

        self._check_not_closed()

        return self._fp.fileno()

    def peek(self, n=0):
        """Return buffered data without advancing the file position.

        Always returns at least one byte of data, unless at EOF.
        The exact number of bytes returned is unspecified.

        """

        self._check_can_read()

        return self._buffer.peek(n)

    def read(self, size=-1):
        """Read up to size uncompressed bytes from the file.

        If size is negative or omitted, read until EOF is reached.
        Returns b'' if the file is already at EOF.

        """

        self._check_can_read()

        return self._buffer.read(size)

    def read1(self, size=-1):
        """Read up to size uncompressed bytes, while trying to avoid making
        multiple reads from the underlying stream. Reads up to a
        buffers worth of data if size is negative.

        Returns b'' if the file is at EOF.

        """

        self._check_can_read()

        if size < 0:
            size = io.DEFAULT_BUFFER_SIZE

        return self._buffer.read1(size)

    def readinto(self, b):
        """Read bytes into b.

        Returns the number of bytes read (0 for EOF).

        """

        self._check_can_read()

        return self._buffer.readinto(b)

    def readline(self, size=-1):
        """Read a line of uncompressed bytes from the file.

        The terminating newline (if present) is retained. If size is
        non-negative, no more than size bytes will be read (in which
        case the line may be incomplete). Returns b'' if already at
        EOF.

        """

        self._check_can_read()

        return self._buffer.readline(size)

    def readlines(self, size=-1):
        """Read a list of lines of uncompressed bytes from the file.

        size can be specified to control the number of lines read; no
        further lines will be read once the total size of the lines
        read so far equals or exceeds size.

        """

        if not isinstance(size, int):
            if not hasattr(size, '__index__'):
                raise TypeError('Integer argument expected')

            size = size.__index__

        self._check_can_read()

        return self._buffer.readlines(size)

    def write(self, data):
        """Write a byte string to the file.

        Returns the number of uncompressed bytes written, which is
        always len(data). Note that due to buffering, the file on disk
        may not reflect the data written until close() is called.

        """

        self._check_can_write()
        compressed = self._encoder.fill(data)
        self._fp.write(compressed)
        self._pos += len(data)

        return len(data)

    def writelines(self, seq):
        """Write a sequence of byte strings to the file.

        Returns the number of uncompressed bytes written.  seq can be
        any iterable yielding byte strings.

        Line separators are not added between the written byte strings.

        """

        self._check_can_write()

        return super(HeatshrinkFile, self).writelines(seq)

    def seek(self, offset, whence=io.SEEK_SET):
        """Change the file position.

        The new position is specified by offset, relative to the
        position indicated by whence. Values for whence are:

            0: start of stream (default); offset must not be negative
            1: current stream position
            2: end of stream; offset must not be positive

        Returns the new file position.

        Note that seeking is emulated, so depending on the parameters,
        this operation may be extremely slow.

        """

        self._check_can_seek()

        return self._buffer.seek(offset, whence)

    def tell(self):
        """Return the current file position."""

        if self._mode == _MODE_READ:
            return self._buffer.tell()

        return self._pos


def open(filename, mode='rb', **kwargs):
    """Open LZSS compressed file in binary mode.

    The filename argument can be an actual filename (a str, bytes or
    file-like object), or an existing file object to read from or
    write to.

    The mode argument can be "rb", "wb". "r" and "w" are converted to
    "rb" and "rb" respectively.

    This function is equivalent to the HeatshrinkFile constructor:
    HeatshrinkFile(filename, mode, **compress_options).

    """

    return HeatshrinkFile(filename, mode, **kwargs)
