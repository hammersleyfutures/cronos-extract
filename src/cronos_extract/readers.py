# ABOUTME: ByteReader: sequential little-endian reader over a bytes buffer.
# ABOUTME: Raises EOFError on reads past the end; used by all structure decoders.
import struct


def decode_cp1251(data: bytes) -> str:
    """
    `data` decoded as CP-1251; the one byte CP-1251 leaves undefined (0x98) becomes U+FFFD, so decoding never fails.
    """
    return data.decode("cp1251", "replace")


class ByteReader:
    """
    The ByteReader object is used when decoding various variable sized structures.
    all functions raise EOFError when attempting to read beyond the end of the buffer.

    functions starting with `read` advance the current position.
    """

    def __init__(self, data):
        self.data = data
        self.o = 0

    def readbyte(self):
        """
        Reads a single byte
        """
        if self.o + 1 > len(self.data):
            raise EOFError()
        self.o += 1
        return struct.unpack_from("<B", self.data, self.o - 1)[0]

    def testbyte(self, bytevalue):
        """
        returns True when the current bytes matches `bytevalue`.
        """
        if self.o + 1 > len(self.data):
            raise EOFError()
        return self.data[self.o] == bytevalue

    def readword(self):
        """
        Reads a 16 bit unsigned little endian value
        """
        if self.o + 2 > len(self.data):
            raise EOFError()
        self.o += 2
        return struct.unpack_from("<H", self.data, self.o - 2)[0]

    def readdword(self):
        """
        Reads a 32 bit unsigned little endian value
        """
        if self.o + 4 > len(self.data):
            raise EOFError()
        self.o += 4
        return struct.unpack_from("<L", self.data, self.o - 4)[0]

    def readbytes(self, n=None):
        """
        Reads the specified number of bytes, or
        when no size was specified, the remaining bytes in the buffer
        """
        if n is None:
            n = len(self.data) - self.o
        if self.o + n > len(self.data):
            raise EOFError()
        self.o += n
        return self.data[self.o - n : self.o]

    def readlongstring(self):
        """
        Reads a cp1251 encoded string prefixed with a dword sized length

        Bytes undefined in CP-1251 become U+FFFD.
        """
        namelen = self.readdword()
        return decode_cp1251(self.readbytes(namelen))

    def readname(self):
        """
        Reads a cp1251 encoded string prefixed with a byte sized length

        Bytes undefined in CP-1251 become U+FFFD.
        """
        namelen = self.readbyte()
        return decode_cp1251(self.readbytes(namelen))

    def readtoseperator(self, sep):
        """
        reads bytes upto a bytes sequence matching `sep`.
        when no `sep` is found, return the remaining bytes in the buffer.
        """
        if self.o > len(self.data):
            raise EOFError()
        oldoff = self.o
        off = self.data.find(sep, self.o)
        if off >= 0:
            self.o = off + len(sep)
            return self.data[oldoff:off]
        else:
            self.o = len(self.data)
            return self.data[oldoff:]

    def eof(self):
        """
        return True when the current position is at or beyond the end of the buffer.
        """
        return self.o >= len(self.data)
