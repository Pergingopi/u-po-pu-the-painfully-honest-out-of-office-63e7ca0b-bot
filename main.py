#!/usr/bin/env python3
"""The Painfully Honest Out-of-Office - one brutally honest but still
polite out-of-office auto-reply.

Pure Python 3.13 standard library. The program writes one out-of-office
auto-reply to $MAKEFUN_OUTPUT_DIR/entry.txt (default /output/entry.txt).
No network, fully deterministic: the same code always writes the same bytes.

The reply (146 characters, plus a trailing newline):
    I'm out of the office, and your email will be read in the order received, just behind 400 others I was too tired to open and too polite to delete.

Why this line wins: it confesses something a real employee would only
say privately (a 400-deep unread inbox, too tired to open it) while
staying warm and professional (read in the order received, too polite
to delete), and it lands on a quotable antithesis - too tired to open,
too polite to delete - instead of a list of complaints. Before writing,
the program runs the reply through a strict gate (UTF-8, 1-200
characters, not only whitespace, exactly one sentence) and rejects
control characters, invisible characters, surrogates and emoji, so a
bad edit fails loudly here instead of shipping an invalid entry.

Usage: mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import os
import unicodedata

AUTO_REPLY = (
    "I'm out of the office, and your email will be read in the order "
    "received, just behind 400 others I was too tired to open and too "
    "polite to delete."
)

LIMIT_CHARS = 200
SENTENCE_ENDERS = (".", "!", "?")
FORBIDDEN_MARKS = ("\ufeff", "\u2028", "\u2029")
LINE_BREAKS = ("\n", "\r", "\x0b", "\x0c", "\u0085")


def check_shape(text):
    """Shape gate: type, emptiness, padding, and length."""
    if not isinstance(text, str):
        raise ValueError("reply must be str")
    if not text or not text.strip():
        raise ValueError("reply must not be empty or whitespace-only")
    if text != text.strip():
        raise ValueError("reply must not have leading or trailing whitespace")
    if len(text) + 1 > LIMIT_CHARS:  # +1 for the trailing newline in the file
        raise ValueError("reply plus trailing newline exceeds 200 characters")


def check_one_sentence(text):
    """Sentence gate: exactly one terminator, at the very end."""
    terminators = [c for c in text if c in ".!?"]
    if len(terminators) != 1 or not text.endswith(SENTENCE_ENDERS):
        raise ValueError("reply must be exactly one sentence")


def check_characters(text):
    """Character gate: no BOM, controls, invisible, surrogate, emoji, marks."""
    for ch in text:
        code = ord(ch)
        if ch in FORBIDDEN_MARKS:
            raise ValueError("reply must not contain BOM, U+2028 or U+2029")
        if 0x00 <= code <= 0x1F or 0x7F <= code <= 0x9F:
            raise ValueError("reply must not contain control characters")
        category = unicodedata.category(ch)
        if category in ("Cf", "Cc", "Cs", "Co", "Cn"):
            raise ValueError("reply must not contain invisible/surrogate characters")
        if category == "So" or code > 0xFFFF:
            raise ValueError("reply must not contain emoji or non-BMP characters")
        if category.startswith("M"):
            raise ValueError("reply must not contain combining marks")


def check_single_line(text):
    """Line gate: no line breaks of any kind."""
    if any(c in text for c in LINE_BREAKS):
        raise ValueError("reply must be a single line")


def validate(text):
    """Run every gate in order. Raises ValueError on the first violation."""
    check_shape(text)
    check_one_sentence(text)
    check_characters(text)
    check_single_line(text)
    return text


def resolve_output_dir():
    """Output directory from the environment, defaulting to /output."""
    return os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")


def stage_entry(out_dir, data):
    """Write the bytes to a staging file inside the output dir, fsynced."""
    tmp = os.path.join(out_dir, ".entry.txt.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o644)
    return tmp


def publish_entry(tmp, final):
    """Atomically move the staged file into place and fix its mode."""
    os.replace(tmp, final)
    os.chmod(final, 0o644)


def verify_on_disk(final, data, reply):
    """Read-back: the file on disk must be exactly what we validated."""
    with open(final, "rb") as f:
        on_disk = f.read()
    if on_disk != data:
        raise ValueError("read-back mismatch: entry.txt differs from validated bytes")
    if on_disk.decode("utf-8") != reply + "\n":
        raise ValueError("read-back mismatch: entry.txt is not valid UTF-8 text")


def build_payload(reply):
    """Encode the validated reply as file bytes, with a size check."""
    data = (reply + "\n").encode("utf-8")
    if not 1 <= len(data) <= LIMIT_CHARS:
        raise ValueError("entry.txt must be 1-200 characters")
    return data


def hand_in():
    """Validate the reply, write entry.txt atomically, verify it."""
    reply = validate(AUTO_REPLY)
    out_dir = resolve_output_dir()
    os.makedirs(out_dir, exist_ok=True)
    data = build_payload(reply)
    # Staging tmp lives INSIDE the output dir so os.replace stays atomic
    # on the same filesystem; a stale tmp from a previous run is swept.
    tmp = stage_entry(out_dir, data)
    final = os.path.join(out_dir, "entry.txt")
    publish_entry(tmp, final)
    verify_on_disk(final, data, reply)


if __name__ == "__main__":
    hand_in()
