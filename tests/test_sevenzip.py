"""The stdlib 7z reader returns exact bytes and fails closed on anything it cannot vouch for."""

import lzma
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from election_audit import sevenzip

LZMA_FILTER = {"id": lzma.FILTER_LZMA1, "dict_size": 1 << 20, "lc": 3, "lp": 0, "pb": 2}


def number(value):
    if value < 0x80:
        return bytes([value])
    if value < 0x4000:
        return bytes([0x80 | (value >> 8), value & 0xFF])
    if value < 0x200000:
        return bytes([0xC0 | (value >> 16), value & 0xFF, (value >> 8) & 0xFF])
    return bytes([0xE0 | (value >> 24)]) + (value & 0xFFFFFF).to_bytes(3, "little")


def coder(method):
    if method == "lzma":
        props = bytes([(2 * 5 + 0) * 9 + 3]) + struct.pack("<I", 1 << 20)
        return b"\x23" + sevenzip.LZMA1 + number(len(props)) + props
    if method == "copy":
        return b"\x01" + sevenzip.COPY
    return b"\x04\x03\x03\x01\x03"  # x86 BCJ filter: not supported


def pack(data, method):
    if method == "lzma":
        return lzma.compress(data, format=lzma.FORMAT_RAW, filters=[LZMA_FILTER])
    return data


def make_7z(files, *, method="lzma", encoded_header=False):
    """Write a one-folder 7z archive: enough of the format to exercise the reader."""
    data = b"".join(body for _, body in files)
    packed = pack(data, method)
    sizes = [len(body) for _, body in files]
    streams = (
        b"\x06"
        + number(0)
        + number(1)
        + b"\x09"
        + number(len(packed))
        + b"\x00"
        + b"\x07\x0b"
        + number(1)
        + b"\x00"
        + number(1)
        + coder(method)
        + b"\x0c"
        + number(len(data))
        + b"\x00"
        + b"\x08\x0d"
        + number(len(files))
        + b"\x09"
        + b"".join(number(size) for size in sizes[:-1])
        + b"\x0a\x01"
        + b"".join(struct.pack("<I", zlib.crc32(body)) for _, body in files)
        + b"\x00"
        + b"\x00"
    )
    names = b"\x00" + b"".join(name.encode("utf-16-le") + b"\x00\x00" for name, _ in files)
    header = (
        b"\x01\x04"
        + streams
        + b"\x05"
        + number(len(files))
        + b"\x11"
        + number(len(names))
        + names
        + b"\x00\x00"
    )
    tail = packed
    if encoded_header:
        tail += header
        header = (
            b"\x17\x06"
            + number(len(packed))
            + number(1)
            + b"\x09"
            + number(len(header))
            + b"\x00\x07\x0b"
            + number(1)
            + b"\x00"
            + number(1)
            + coder("copy")
            + b"\x0c"
            + number(len(header))
            + b"\x0a\x01"
            + struct.pack("<I", zlib.crc32(header))
            + b"\x00\x00"
        )
    start = struct.pack("<QQI", len(tail), len(header), zlib.crc32(header))
    return (
        sevenzip.MAGIC + b"\x00\x04" + struct.pack("<I", zlib.crc32(start)) + start + tail + header
    )


class SevenZipTests(unittest.TestCase):
    def test_lzma_archive_with_several_files_round_trips(self):
        files = [("inner.jez", b"PK" + bytes(range(256)) * 40), ("logd.dat", b"line\tA\n" * 999)]
        self.assertEqual([(n, b) for n, b, _ in sevenzip.read(make_7z(files))], files)

    def test_encoded_header_and_copy_coder(self):
        files = [("logd.dat", b"x" * 1000)]
        archive = make_7z(files, method="copy", encoded_header=True)
        self.assertEqual(sevenzip.read(archive), [("logd.dat", b"x" * 1000, False)])

    def test_empty_archive_has_no_entries(self):
        # 2022 SP 71072/0002/0310 round 2 nests a 32-byte empty .jez written by 7-Zip.
        start = struct.pack("<QQI", 0, 0, 0)
        empty = sevenzip.MAGIC + b"\x00\x04" + struct.pack("<I", zlib.crc32(start)) + start
        self.assertEqual(sevenzip.read(empty), [])
        with self.assertRaises(sevenzip.SevenZipError):
            sevenzip.read(empty + b"\x00")

    def test_corruption_and_unsupported_features_fail_closed(self):
        good = make_7z([("logd.dat", b"hello world " * 200)], method="copy")
        corrupt = bytearray(good)
        corrupt[40] ^= 0xFF  # inside the packed data: the file CRC no longer matches
        cases = {
            "file crc": bytes(corrupt),
            "start header crc": good[:8] + b"\x00\x00\x00\x00" + good[12:],
            "truncated": good[:-5],
            "not 7z": b"PK\x03\x04" + good[4:],
            "filter": make_7z([("logd.dat", b"abc")], method="bcj"),
        }
        for name, archive in cases.items():
            with self.subTest(case=name), self.assertRaises(sevenzip.SevenZipError):
                sevenzip.read(archive)
        with self.assertRaisesRegex(sevenzip.SevenZipError, "bound"):
            sevenzip.read(make_7z([("logd.dat", b"y" * 100)]), limit=99)

    @unittest.skipUnless(shutil.which("7z"), "7z binary not installed")
    def test_matches_archives_written_by_7z(self):
        body = "".join(
            f"02/10/2022 08:{i // 60:02d}:{i % 60:02d}\tINFO\t1\tVOTA\tm {i}\tT\n"
            for i in range(3000)
        )
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "logd.dat").write_text(body, encoding="latin-1")
            subprocess.run(
                ["7z", "a", "-m0=LZMA", "out.7z", "logd.dat"],
                cwd=d,
                check=True,
                capture_output=True,
            )
            entries = sevenzip.read((Path(d) / "out.7z").read_bytes())
        self.assertEqual(entries, [("logd.dat", body.encode("latin-1"), False)])


if __name__ == "__main__":
    unittest.main()
