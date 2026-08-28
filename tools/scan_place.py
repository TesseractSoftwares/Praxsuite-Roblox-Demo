#!/usr/bin/env python3
"""Scan a Roblox binary place/model file for leaked secrets before it goes public.

This repo is mirrored to a PUBLIC GitHub repo, so anything inside the .rbxl reaches
every reader. A plain `grep sk_live_ RobloxSDKDemo.rbxl` proves NOTHING: the string
data in a binary Roblox file lives in LZ4- (or ZSTD-) compressed chunks, so a key
pasted into a Script would not appear in the raw bytes. This walks the chunk table,
decompresses it, and scans what a person would actually see in Studio.

    python3 tools/scan_place.py RobloxSDKDemo.rbxl     # 0 = clean, 1 = leak
    python3 tools/scan_place.py --self-test            # prove the scanner still bites

No third-party packages: the LZ4 block decoder below is ~30 lines and a build agent is
not guaranteed to have python-lz4. ZSTD chunks (newer Studio saves) need Python 3.14's
compression.zstd or the `zstandard` package, and are reported as an unreadable file
rather than quietly skipped - a scanner that cannot read the file must say so, not pass.

The --self-test exists because a gate that has never rejected anything is not known to
work. It builds a place file carrying a real-shaped key and asserts this scanner fails
it, so a regression in the decoder cannot silently turn the gate into a no-op.
"""

import re
import sys

HEADER = b"<roblox!\x89\xff\x0d\x0a\x1a\x0a\x00\x00"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# sk_ is the hard failure: it is the key that can write to a workspace.
FATAL = [
    ("Praxsuite secret key", re.compile(rb"sk_live_[A-Za-z0-9]{16,}")),
    ("Praxsuite test secret key", re.compile(rb"sk_test_[A-Za-z0-9]{16,}")),
    ("Roblox session cookie", re.compile(rb"_\|WARNING:-DO-NOT-SHARE-THIS")),
    ("private key block", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Reported, not fatal: a publishable key is meant to ship and the demo is allowed to
# carry one. A human still gets told it is there.
#
# Deliberately NOT matching a bare RBX-prefixed token: Roblox stamps internal tags such
# as RBX_LightingTechnologyUnifiedMigration into every place, and a gate that cries wolf
# on every run is a gate people stop reading.
WARN = [
    ("Praxsuite publishable key", re.compile(rb"pk_live_[A-Za-z0-9]{16,}")),
    ("bearer token", re.compile(rb"Bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("Roblox Open Cloud key", re.compile(rb"x-api-key[\s:='\"]+[A-Za-z0-9+/=._\-]{30,}", re.I)),
]


def lz4_block_decompress(src, expected):
    """Decode one LZ4 block. Raises ValueError on a malformed stream."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise ValueError("LZ4 match offset of 0")
        match = token & 0x0F
        if match == 15:
            while True:
                b = src[i]
                i += 1
                match += b
                if b != 255:
                    break
        match += 4
        start = len(out) - offset
        if start < 0:
            raise ValueError("LZ4 match points before the start of the output")
        for k in range(match):
            out.append(out[start + k])
    if len(out) != expected:
        raise ValueError("decompressed %d bytes, chunk header said %d" % (len(out), expected))
    return bytes(out)


def zstd_decompress(src, expected):
    try:
        from compression import zstd  # Python 3.14+
        return zstd.decompress(src)
    except ImportError:
        pass
    try:
        import zstandard
        return zstandard.ZstdDecompressor().decompress(src, max_output_size=expected)
    except ImportError:
        raise ValueError(
            "a chunk is ZSTD-compressed and no decompressor is available "
            "(needs Python 3.14+ or `pip install zstandard`). Refusing to report this "
            "file clean when most of it was never read."
        )


def read_chunks(data):
    """Yield (name, payload) for every chunk, decompressed."""
    if not data.startswith(HEADER):
        raise ValueError(
            "not a binary Roblox file (no <roblox!> header). "
            "If this is the XML format, grep it directly instead."
        )
    pos = 32  # 16 header + classCount(4) + instanceCount(4) + 8 reserved
    while pos + 16 <= len(data):
        name = data[pos:pos + 4]
        comp = int.from_bytes(data[pos + 4:pos + 8], "little")
        uncomp = int.from_bytes(data[pos + 8:pos + 12], "little")
        pos += 16
        size = comp if comp else uncomp
        payload = data[pos:pos + size]
        pos += size
        if comp == 0:
            yield name, payload
        elif payload.startswith(ZSTD_MAGIC):
            yield name, zstd_decompress(payload, uncomp)
        else:
            yield name, lz4_block_decompress(payload, uncomp)
        if name == b"END\x00":
            return
    raise ValueError("ran off the end of the file without finding the END chunk")


def scan_bytes(data, path, quiet=False):
    try:
        chunks = list(read_chunks(data))
    except ValueError as exc:
        print("##vso[task.logissue type=error]%s: %s" % (path, exc))
        return False

    blob = b"".join(payload for _, payload in chunks)
    if not quiet:
        kinds = {}
        for name, payload in chunks:
            key = name.decode("ascii", "replace").rstrip("\x00")
            kinds[key] = kinds.get(key, 0) + len(payload)
        summary = ", ".join("%s %dB" % (k, v) for k, v in sorted(kinds.items()))
        print("%s: %d bytes on disk, %d decompressed across %d chunks (%s)"
              % (path, len(data), len(blob), len(chunks), summary))

    clean = True
    for label, pattern in FATAL:
        for hit in pattern.findall(blob):
            shown = hit[:14].decode("ascii", "replace")
            print("##vso[task.logissue type=error]%s: %s found (%s...). Revoke it now - "
                  "this repo is mirrored publicly." % (path, label, shown))
            clean = False
    if not quiet:
        for label, pattern in WARN:
            found = pattern.findall(blob)
            if found:
                print("##vso[task.logissue type=warning]%s: %d %s(s) present. A publishable "
                      "key is fine to ship - confirm that is what it is."
                      % (path, len(found), label))
        if clean:
            print("%s: no secrets." % path)
    return clean


def scan(path, quiet=False):
    with open(path, "rb") as fh:
        return scan_bytes(fh.read(), path, quiet)


# --- self-test ---------------------------------------------------------------

def _lz4_literal_block(payload):
    """Encode payload as a valid LZ4 block of pure literals (no matches)."""
    out = bytearray()
    n = len(payload)
    if n < 15:
        out.append(n << 4)
    else:
        out.append(0xF0)
        rest = n - 15
        while rest >= 255:
            out.append(255)
            rest -= 255
        out.append(rest)
    out += payload
    return bytes(out)


def _synthetic_place(secret, compress):
    """A minimal but structurally real .rbxl carrying `secret` in a PROP chunk."""
    body = b'local KEY = "' + secret + b'"\n'
    out = bytearray(HEADER)
    out += (1).to_bytes(4, "little")  # classCount
    out += (1).to_bytes(4, "little")  # instanceCount
    out += b"\x00" * 8                # reserved
    for name, payload in ((b"PROP", body), (b"END\x00", b"</roblox>")):
        if compress and name != b"END\x00":
            blob = _lz4_literal_block(payload)
            out += name + len(blob).to_bytes(4, "little") + len(payload).to_bytes(4, "little")
            out += b"\x00" * 4 + blob
        else:
            out += name + (0).to_bytes(4, "little") + len(payload).to_bytes(4, "little")
            out += b"\x00" * 4 + payload
    return bytes(out)


def self_test():
    # Assembled from pieces on purpose. Written as one literal it would be a real-shaped
    # secret key sitting in a public repo, and the pipeline's own text-file scan would have
    # to be told to skip this file - which is exactly the kind of exception that later hides
    # a genuine leak.
    key = b"sk_" + b"live_" + b"A1b2C3d4E5f6G7h8I9j0K1l2"
    failures = []
    for compress in (False, True):
        label = "lz4" if compress else "stored"
        if scan_bytes(_synthetic_place(key, compress), "<self-test %s bad>" % label, quiet=True):
            failures.append("%s: a planted secret key was NOT detected" % label)
        else:
            print("self-test %s: planted key rejected, as it must be." % label)
        clean = _synthetic_place(b"pk_live_A1b2C3d4E5f6G7h8I9j0K1l2", compress)
        if not scan_bytes(clean, "<self-test %s good>" % label, quiet=True):
            failures.append("%s: a clean file was reported as leaking" % label)
        else:
            print("self-test %s: clean file accepted." % label)
    for msg in failures:
        print("##vso[task.logissue type=error]scan_place self-test: %s" % msg)
    if failures:
        print("##vso[task.logissue type=error]The secret scanner does not work. Do not "
              "publish until it does - a gate that cannot fail is not a gate.")
        return 1
    print("self-test passed: the scanner detects a planted key in stored and LZ4 chunks.")
    return 0


def main(argv):
    args = argv[1:]
    if args == ["--self-test"]:
        return self_test()
    if not args:
        sys.stderr.write(__doc__)
        return 2
    return 0 if all([scan(p) for p in args]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
