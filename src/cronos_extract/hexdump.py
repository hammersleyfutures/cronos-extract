# ABOUTME: Helpers that convert bytes to hex, CP-1251 text and C-style escaped strings.
# ABOUTME: Also prints offset-prefixed hex and text dumps for the inspection commands.
"""
Several functions for converting bytes to readable text or hex bytes.
"""

import struct
from binascii import a2b_hex, b2a_hex


def unhex(data):
    """
    convert a possibly space separated list of 2-digit hex values to a byte-array
    """
    if isinstance(data, bytes):
        data = data.decode("ascii")
    data = data.replace(" ", "")
    data = data.strip()
    return a2b_hex(data)


def ashex(line):
    """
    convert a byte-array to a space separated list of 2-digit hex values.
    """
    return " ".join(f"{_:02x}" for _ in line)


def asambigoushex(line, confidence):
    """
    convert an array to a list of 2-digit hex values with potentially unset values of -1
    """
    return "".join(f"{_:02x}" if confidence[o] > 0 else "??" for o, _ in enumerate(line))


def as1251(b):
    """
    convert unicode text to CP-1251 bytes
    This will help parse cyrillic user entries from command line.
    Raises ValueError naming the text when it contains characters CP-1251 can't encode.
    """
    try:
        return str(b).encode("cp1251")
    except UnicodeEncodeError as e:
        raise ValueError(f"{b!r} can't be encoded as CP-1251: {e.reason} at position {e.start}") from e


def aschr(b):
    """
    convert a CP-1251 byte to a unicode character.
    This will make both cyrillic and latin text readable.
    """
    if 32 <= b < 0x7F:
        return chr(b)
    elif 0x80 <= b <= 0xFF:
        try:
            c = struct.pack("<B", b).decode("cp1251")
            if c:
                return c
        except UnicodeDecodeError:
            # 0x98 is the only invalid cp1251 character.
            pass
    return "."


def asasc(line, confidence=None):
    """
    convert a CP-1251 encoded byte-array to a line of unicode characters.
    """
    if confidence is None:
        return "".join(aschr(_) for _ in line)
    else:
        return "".join(aschr(_) if confidence[o] > 0 else "?" for o, _ in enumerate(line))


def hexdump(ofs, data, args):
    """
    Output offset prefixed lines of hex + ascii characters.
    """
    w = args.width
    for o in range(0, len(data), w):
        chunk = data[o : o + w]
        if args.ascdump:
            print(f"{o + ofs:08x}: {asasc(chunk)}")
        else:
            print(f"{o + ofs:08x}: {ashex(chunk):<{3 * w - 1}}  {asasc(chunk)}")


def tohex(data):
    """
    Convert a byte-array to a sequence of 2-digit hex values without separators.
    """
    return b2a_hex(data).decode("ascii")


def toout(args, data):
    """
    Return either ascdump or hexdump, depending on the `args.ascdump` flag.
    """
    if args.ascdump:
        return asasc(data)
    else:
        return tohex(data)


def strescape(txt):
    """
    Convert bytes or text to a c-style escaped string.

    Only receives values Database.dump_db_definition's regex has let through, which cannot hold 0x98, so this
    strict decode cannot fail.
    """
    if isinstance(txt, bytes):
        txt = txt.decode("cp1251")
    txt = txt.replace("\\", "\\\\")
    txt = txt.replace("\n", "\\n")
    txt = txt.replace("\r", "\\r")
    txt = txt.replace("\t", "\\t")
    txt = txt.replace('"', '\\"')
    return txt
