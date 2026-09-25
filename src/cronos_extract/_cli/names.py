# ABOUTME: Safe, unique names for what an export writes: file and directory names, and PostgreSQL identifiers.
# ABOUTME: Names are compared case-insensitively and shortened at a character boundary to fit a byte limit.
import re
from itertools import chain, count

# The longest file name, in bytes, that Linux, macOS and Windows file systems accept.
MAX_FILE_NAME_BYTES = 255
# The longest file name extension kept in full, in bytes, dot included.
MAX_EXTENSION_BYTES = 64
# The longest identifier, in bytes, that PostgreSQL keeps without truncating it.
POSTGRES_IDENTIFIER_BYTES = 63


def safepathname(name: str) -> str:
    """Replace the characters that can't appear in a file name on Linux, macOS or Windows with underscores."""
    return re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name)


def truncate_utf8(text: str, max_bytes: int) -> str:
    """Return the longest start of `text` that is at most `max_bytes` long in UTF-8, cut at a character boundary."""
    return text.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")


def unique_name(stem: str, extension: str, number: int, used_names: dict[str, int], max_bytes: int) -> str | None:
    """
    Return `stem` followed by `extension` when no other output uses that name, or None when the thing
    numbered `number` already has it. A name already used by something else gets "-<number>" appended
    to its stem, and a counter after that if needed. The stem is shortened so that the whole name fits
    in `max_bytes` UTF-8 bytes.
    `used_names` maps each name given so far, compared case-insensitively, to its number.
    """
    suffixes = chain(["", f"-{number}"], (f"-{number}-{n}" for n in count(2)))
    while True:
        suffix = next(suffixes)
        room = max_bytes - len(suffix.encode("utf-8")) - len(extension.encode("utf-8"))
        name = truncate_utf8(stem, room) + suffix + extension
        key = name.casefold()
        if key not in used_names:
            used_names[key] = number
            return name
        if used_names[key] == number:
            return None


def unique_file_name(stem: str, extension: str, number: int, used_names: dict[str, int]) -> str | None:
    """
    Return a file name made from `stem` and `extension` that no other output file uses, or None when
    the thing numbered `number` already has a file.

    `stem` and `extension` are made safe with safepathname, and a stem that is empty or only dots is
    replaced by `number`. The extension is cut to MAX_EXTENSION_BYTES and the stem is shortened so that
    the name fits in MAX_FILE_NAME_BYTES. See unique_name for how names are kept unique.
    """
    stem = safepathname(stem)
    if not stem.strip("."):
        stem = str(number)
    extension = truncate_utf8("." + safepathname(extension), MAX_EXTENSION_BYTES) if extension else ""
    return unique_name(stem, extension, number, used_names, MAX_FILE_NAME_BYTES)
