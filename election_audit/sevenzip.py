"""Minimal, bounded, fail-closed reader for the 7z archives TSE used for 2022 urn logs.

2022 ``.logjez`` files are 7z archives (2026 logs are ZIP). This reader uses only the
standard library and supports the subset those files need: a plain or LZMA-encoded
header, folders with a single LZMA, LZMA2 or copy coder, sub-streams and empty
files. Every CRC the archive declares is checked. Anything else (filters, coder
chains, encryption, external data, additional streams) raises ``SevenZipError``
rather than being guessed at.
"""

from __future__ import annotations

import lzma
import struct
import zlib

MAGIC = b"7z\xbc\xaf\x27\x1c"
LZMA1, LZMA2, COPY = b"\x03\x01\x01", b"\x21", b"\x00"
(
    END,
    HEADER,
    ARCHIVE_PROPERTIES,
    ADDITIONAL_STREAMS,
    MAIN_STREAMS,
    FILES_INFO,
    PACK_INFO,
    UNPACK_INFO,
    SUBSTREAMS_INFO,
    SIZE,
    CRC,
    FOLDER,
    CODERS_UNPACK_SIZE,
    NUM_UNPACK_STREAM,
    EMPTY_STREAM,
    EMPTY_FILE,
) = range(16)
NAME, DUMMY, ENCODED_HEADER = 0x11, 0x19, 0x17


class SevenZipError(ValueError):
    pass


class _Reader:
    def __init__(self, data) -> None:
        self.data, self.pos = data, 0

    def byte(self):
        if self.pos >= len(self.data):
            raise SevenZipError("Truncated 7z header")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise SevenZipError("Truncated 7z header")
        value = self.data[self.pos : self.pos + size]
        self.pos += size
        return value

    def number(self):
        first, mask, value = self.byte(), 0x80, 0
        for index in range(8):
            if not first & mask:
                return value | ((first & (mask - 1)) << (8 * index))
            value |= self.byte() << (8 * index)
            mask >>= 1
        return value

    def bits(self, count):
        values, current, mask = [], 0, 0
        for _ in range(count):
            if not mask:
                current, mask = self.byte(), 0x80
            values.append(bool(current & mask))
            mask >>= 1
        return values

    def digests(self, count):
        defined = [True] * count if self.byte() else self.bits(count)
        return [struct.unpack("<I", self.take(4))[0] if d else None for d in defined]

    def expect(self, value) -> None:
        if self.byte() != value:
            raise SevenZipError("Unexpected 7z header property")


def _streams(r):
    pack_pos, pack_sizes, folders, sub = 0, [], [], None
    while (kind := r.byte()) != END:
        if kind == PACK_INFO:
            pack_pos, count = r.number(), r.number()
            while (prop := r.byte()) != END:
                if prop == SIZE:
                    pack_sizes = [r.number() for _ in range(count)]
                elif prop == CRC:
                    r.digests(count)
                else:
                    raise SevenZipError("Unsupported pack info property")
        elif kind == UNPACK_INFO:
            r.expect(FOLDER)
            count = r.number()
            if r.byte():
                raise SevenZipError("External folders are not supported")
            for _ in range(count):
                if r.number() != 1:
                    raise SevenZipError("Coder chains are not supported")
                flag = r.byte()
                if flag & 0xC0 or flag & 0x10:
                    raise SevenZipError("Complex or alternative coders are not supported")
                method = r.take(flag & 0x0F)
                props = r.take(r.number()) if flag & 0x20 else b""
                folders.append({"method": method, "props": props, "crc": None})
            r.expect(CODERS_UNPACK_SIZE)
            for folder in folders:
                folder["size"] = r.number()
            while (prop := r.byte()) != END:
                if prop != CRC:
                    raise SevenZipError("Unsupported unpack info property")
                for folder, digest in zip(folders, r.digests(len(folders)), strict=True):
                    folder["crc"] = digest
        elif kind == SUBSTREAMS_INFO:
            sub = _substreams(r, folders)
        else:
            raise SevenZipError("Unsupported streams property")
    if len(pack_sizes) != len(folders):
        raise SevenZipError("Pack streams do not match folders")
    if sub is None:
        sub = [[(f["size"], f["crc"])] for f in folders]
    return pack_pos, pack_sizes, folders, sub


def _substreams(r, folders):
    counts = [1] * len(folders)
    sizes = None
    prop = r.byte()
    if prop == NUM_UNPACK_STREAM:
        counts = [r.number() for _ in folders]
        prop = r.byte()
    if prop == SIZE:
        sizes = []
        for folder, count in zip(folders, counts, strict=True):
            if not count:
                sizes.append([])
                continue
            known = [r.number() for _ in range(count - 1)]
            if sum(known) > folder["size"]:
                raise SevenZipError("Sub-stream sizes exceed folder size")
            sizes.append([*known, folder["size"] - sum(known)])
        prop = r.byte()
    if sizes is None:
        sizes = []
        for folder, count in zip(folders, counts, strict=True):
            if count > 1:
                raise SevenZipError("Sub-stream sizes missing")
            sizes.append([folder["size"]] * count)
    crcs = [[None] * c for c in counts]
    unknown = [
        (i, j)
        for i, (folder, count) in enumerate(zip(folders, counts, strict=True))
        for j in range(count)
        if not (count == 1 and folder["crc"] is not None)
    ]
    for i, (folder, count) in enumerate(zip(folders, counts, strict=True)):
        if count == 1 and folder["crc"] is not None:
            crcs[i][0] = folder["crc"]
    if prop == CRC:
        for (i, j), digest in zip(unknown, r.digests(len(unknown)), strict=True):
            crcs[i][j] = digest
        prop = r.byte()
    if prop != END:
        raise SevenZipError("Unsupported sub-streams property")
    return [list(zip(s, c, strict=True)) for s, c in zip(sizes, crcs, strict=True)]


def _decode(folder, packed, limit):
    if folder["size"] > limit:
        raise SevenZipError("Unpacked size bound exceeded")
    method, props = folder["method"], folder["props"]
    if method == COPY:
        out = bytes(packed)
    else:
        if method == LZMA1 and len(props) == 5:
            d = props[0]
            if d >= 9 * 5 * 5:
                raise SevenZipError("Invalid LZMA properties")
            spec = {
                "id": lzma.FILTER_LZMA1,
                "lc": d % 9,
                "lp": (d // 9) % 5,
                "pb": d // 45,
                "dict_size": struct.unpack("<I", props[1:5])[0],
            }
        elif method == LZMA2 and len(props) == 1 and props[0] <= 40:
            p = props[0]
            spec = {
                "id": lzma.FILTER_LZMA2,
                "dict_size": 0xFFFFFFFF if p == 40 else (2 | (p & 1)) << (p // 2 + 11),
            }
        else:
            raise SevenZipError(f"Unsupported 7z coder {method.hex()}")
        # 7z LZMA streams usually have no end marker, so a raw decoder runs past the
        # declared size; stop exactly there and let the CRC vouch for the bytes.
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[spec])
        try:
            out = decoder.decompress(bytes(packed), max_length=folder["size"])
        except lzma.LZMAError as error:
            raise SevenZipError(f"Corrupt LZMA stream: {error}") from None
    if len(out) != folder["size"]:
        raise SevenZipError("Unpacked size mismatch")
    if folder["crc"] is not None and zlib.crc32(out) != folder["crc"]:
        raise SevenZipError("Folder CRC mismatch")
    return out


def _unpack(data, base, streams, limit):
    pack_pos, pack_sizes, folders, sub = streams
    offset, outputs = base + pack_pos, []
    for folder, size, parts in zip(folders, pack_sizes, sub, strict=True):
        if offset + size > len(data):
            raise SevenZipError("Packed stream beyond end of archive")
        body = _decode(folder, memoryview(data)[offset : offset + size], limit)
        offset += size
        start = 0
        for length, digest in parts:
            piece = body[start : start + length]
            start += length
            if digest is not None and zlib.crc32(piece) != digest:
                raise SevenZipError("File CRC mismatch")
            outputs.append(piece)
    return outputs


def _files(r, count):
    empty_stream, empty_file, names = [False] * count, None, None
    while (prop := r.byte()) != END:
        payload = _Reader(r.take(r.number()))
        if prop == EMPTY_STREAM:
            empty_stream = payload.bits(count)
        elif prop == EMPTY_FILE:
            empty_file = payload.bits(sum(empty_stream))
        elif prop == NAME:
            if payload.byte():
                raise SevenZipError("External names are not supported")
            raw = payload.data[payload.pos :].decode("utf-16-le")
            names = raw.split("\x00")[:-1]
            if len(names) != count:
                raise SevenZipError("Name count mismatch")
        elif prop not in (DUMMY, *range(0x12, 0x17), 0x18):
            raise SevenZipError("Unsupported file property")
    return empty_stream, empty_file, names or [""] * count


def read(data, *, limit=128 * 1024**2):
    """Return ``[(name, bytes, is_dir)]`` for every entry of a 7z archive held in memory."""
    if len(data) < 32 or data[:6] != MAGIC:
        raise SevenZipError("Not a 7z archive")
    if zlib.crc32(data[12:32]) != struct.unpack("<I", data[8:12])[0]:
        raise SevenZipError("Start header CRC mismatch")
    offset, size, crc = struct.unpack("<QQI", data[12:32])
    if size == 0:
        # An empty archive (7-Zip writes no header at all): a 32-byte signature header only.
        if offset or crc or len(data) != 32:
            raise SevenZipError("Empty 7z header with trailing data")
        return []
    start = 32 + offset
    if start + size > len(data):
        raise SevenZipError("Header beyond end of archive")
    header = data[start : start + size]
    if zlib.crc32(header) != crc:
        raise SevenZipError("Header CRC mismatch")
    r = _Reader(header)
    if r.byte() == ENCODED_HEADER:
        decoded = _unpack(data, 32, _streams(r), limit)
        if len(decoded) != 1:
            raise SevenZipError("Encoded header must be one stream")
        r = _Reader(decoded[0])
        r.expect(HEADER)
    elif r.data[:1] != bytes([HEADER]):
        raise SevenZipError("Missing 7z header")
    streams, entries = None, []
    while (kind := r.byte()) != END:
        if kind == ARCHIVE_PROPERTIES:
            while r.byte() != END:
                r.take(r.number())
        elif kind == MAIN_STREAMS:
            streams = _streams(r)
        elif kind == FILES_INFO:
            count = r.number()
            empty_stream, empty_file, names = _files(r, count)
            contents = iter(_unpack(data, 32, streams, limit) if streams else [])
            empty_index = 0
            for index in range(count):
                if empty_stream[index]:
                    is_file = empty_file[empty_index] if empty_file else False
                    empty_index += 1
                    entries.append((names[index], b"", not is_file))
                else:
                    body = next(contents, None)
                    if body is None:
                        raise SevenZipError("Fewer streams than files")
                    entries.append((names[index], body, False))
            if next(contents, None) is not None:
                raise SevenZipError("More streams than files")
        else:
            raise SevenZipError("Unsupported 7z header property")
    return entries
