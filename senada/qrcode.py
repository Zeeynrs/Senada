"""Pure-Python QR code SVG encoder (Byte mode, ECC Level M, Versions 1-6).

Used as a zero-dependency fallback when ``segno`` is not installed so Senada's
Phone Remote always displays a scannable QR code on every platform.
"""

from __future__ import annotations

import urllib.parse

# (version, total_data_bytes, (blocks, data_per_block, ecc_per_block), align_coords)
_VERSIONS_M = (
    (1, 16, (1, 16, 10), ()),
    (2, 28, (1, 28, 16), (6, 18)),
    (3, 44, (1, 44, 26), (6, 22)),
    (4, 64, (2, 32, 18), (6, 26)),
    (5, 86, (2, 43, 24), (6, 30)),
    (6, 108, (4, 27, 16), (6, 34)),
)


def _gf_tables():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


_GF_EXP, _GF_LOG = _gf_tables()


def _gf_mul(a: int, b: int) -> int:
    return 0 if (a == 0 or b == 0) else _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        root = _GF_EXP[i]
        nxt = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, root)
        poly = nxt
    return poly


def _rs_remainder(data: list[int], ecc_len: int) -> list[int]:
    gen = _rs_generator(ecc_len)
    rem = list(data) + [0] * ecc_len
    for i in range(len(data)):
        factor = rem[i]
        if factor:
            for j, g in enumerate(gen):
                rem[i + j] ^= _gf_mul(g, factor)
    return rem[len(data):]


def _encode_codewords(payload: bytes) -> tuple[int, tuple[int, int], list[int]]:
    n = len(payload)
    spec = None
    # Byte mode uses 4-bit mode + 8-bit count = 12 bits + 4-bit terminator padding
    for ver, total_data, blk, align in _VERSIONS_M:
        if 12 + 8 * n <= total_data * 8:
            spec = (ver, total_data, blk, align)
            break
    if spec is None:
        raise ValueError(f"QR payload too long ({n} bytes)")

    ver, total_data, (n_blocks, data_len, ecc_len), align = spec
    bits: list[int] = []

    def push(val: int, width: int):
        for shift in range(width - 1, -1, -1):
            bits.append((val >> shift) & 1)

    push(0b0100, 4)  # Byte mode
    push(n, 8)
    for b in payload:
        push(b, 8)
    # Terminator up to 4 bits, pad to byte boundary
    cap_bits = total_data * 8
    push(0, min(4, cap_bits - len(bits)))
    if len(bits) % 8:
        push(0, 8 - (len(bits) % 8))

    data_bytes = []
    for i in range(0, len(bits), 8):
        byte = 0
        for b in bits[i:i + 8]:
            byte = (byte << 1) | b
        data_bytes.append(byte)
    pad = (0xEC, 0x11)
    idx = 0
    while len(data_bytes) < total_data:
        data_bytes.append(pad[idx % 2])
        idx += 1

    blocks = [data_bytes[i * data_len:(i + 1) * data_len] for i in range(n_blocks)]
    ecc_blocks = [_rs_remainder(b, ecc_len) for b in blocks]

    codewords: list[int] = []
    for i in range(data_len):
        for b in blocks:
            codewords.append(b[i])
    for i in range(ecc_len):
        for e in ecc_blocks:
            codewords.append(e[i])
    return ver, align, codewords


def _format_bits(mask: int) -> int:
    # ECC Level M = 0b00, 15-bit BCH + XOR 0x5412
    data = (0b00 << 3) | mask
    rem = data << 10
    for i in range(4, -1, -1):
        if rem & (1 << (i + 10)):
            rem ^= 0x537 << i
    return ((data << 10) | rem) ^ 0x5412


def _build_matrix(ver: int, align: tuple[int, ...], codewords: list[int]) -> list[list[bool]]:
    size = ver * 4 + 17
    modules: list[list[bool | None]] = [[None] * size for _ in range(size)]
    func: list[list[bool]] = [[False] * size for _ in range(size)]

    def set_fn(r: int, c: int, dark: bool):
        modules[r][c] = dark
        func[r][c] = True

    def place_finder(top: int, left: int):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = top + dr, left + dc
                if not (0 <= r < size and 0 <= c < size):
                    continue
                if 0 <= dr <= 6 and 0 <= dc <= 6:
                    dark = dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)
                else:
                    dark = False
                set_fn(r, c, dark)

    place_finder(0, 0)
    place_finder(0, size - 7)
    place_finder(size - 7, 0)

    # Alignment patterns (skip corners occupied by finder patterns)
    if align:
        for r in align:
            for c in align:
                if modules[r][c] is not None:
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        set_fn(r + dr, c + dc, abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0))

    # Timing patterns
    for i in range(8, size - 8):
        dark = (i % 2) == 0
        if not func[6][i]:
            set_fn(6, i, dark)
        if not func[i][6]:
            set_fn(i, 6, dark)

    # Dark module & reserve format info areas
    set_fn(size - 8, 8, True)
    for i in range(9):
        if not func[8][i]:
            func[8][i] = True
            modules[8][i] = False
        if not func[i][8]:
            func[i][8] = True
            modules[i][8] = False
    for i in range(8):
        if not func[8][size - 1 - i]:
            func[8][size - 1 - i] = True
            modules[8][size - 1 - i] = False
        if not func[size - 1 - i][8]:
            func[size - 1 - i][8] = True
            modules[size - 1 - i][8] = False

    # Place data bits in upward/downward zigzag
    all_bits = [(cw >> s) & 1 for cw in codewords for s in range(7, -1, -1)]
    bit_idx = 0
    col = size - 1
    up = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if up else range(size)
        for r in rows:
            for dc in (0, -1):
                c = col + dc
                if not func[r][c]:
                    dark = bool(all_bits[bit_idx]) if bit_idx < len(all_bits) else False
                    modules[r][c] = dark
                    bit_idx += 1
        up = not up
        col -= 2

    # Try all 8 standard masks and pick lowest penalty score
    mask_fns = (
        lambda r, c: (r + c) % 2 == 0,
        lambda r, c: r % 2 == 0,
        lambda r, c: c % 3 == 0,
        lambda r, c: (r + c) % 3 == 0,
        lambda r, c: (r // 2 + c // 3) % 2 == 0,
        lambda r, c: ((r * c) % 2 + (r * c) % 3) == 0,
        lambda r, c: (((r * c) % 2 + (r * c) % 3) % 2) == 0,
        lambda r, c: (((r + c) % 2 + (r * c) % 3) % 2) == 0,
    )

    best_score = None
    best_mat = None
    for mask_id, fn in enumerate(mask_fns):
        grid = [[bool(modules[r][c]) ^ (not func[r][c] and fn(r, c)) for c in range(size)] for r in range(size)]
        fmt = _format_bits(mask_id)
        for i in range(15):
            bit = bool((fmt >> i) & 1)
            # Horizontal: MSB (14) at col 0 -> LSB (0) at col size-1
            if i < 8:
                grid[8][size - 1 - i] = bit
            elif i == 8:
                grid[8][7] = bit
            else:
                grid[8][14 - i] = bit
            # Vertical: MSB (14) at row size-1 -> LSB (0) at row 0
            if i < 6:
                grid[i][8] = bit
            elif i < 8:
                grid[i + 1][8] = bit
            else:
                grid[size - 15 + i][8] = bit
        grid[size - 8][8] = True
        score = _penalty(grid)
        if best_score is None or score < best_score:
            best_score = score
            best_mat = grid
    return best_mat  # type: ignore[return-value]


def _penalty(grid: list[list[bool]]) -> int:
    n = len(grid)
    score = 0
    # N1: runs of >=5 in row/col
    for line in grid + [[grid[r][c] for r in range(n)] for c in range(n)]:
        run = 1
        for i in range(1, n):
            if line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    # N2: 2x2 blocks
    for r in range(n - 1):
        for c in range(n - 1):
            v = grid[r][c]
            if grid[r][c + 1] == v and grid[r + 1][c] == v and grid[r + 1][c + 1] == v:
                score += 3
    # N3: finder-like 1:1:3:1:1 patterns
    p1 = (True, False, True, True, True, False, True, False, False, False, False)
    p2 = (False, False, False, False, True, False, True, True, True, False, True)
    for line in grid + [[grid[r][c] for r in range(n)] for c in range(n)]:
        t = tuple(line)
        for i in range(n - 10):
            seg = t[i:i + 11]
            if seg == p1 or seg == p2:
                score += 40
    # N4: dark ratio balance
    dark = sum(1 for row in grid for v in row if v)
    pct = abs((dark * 100) // (n * n) - 50) // 5
    score += pct * 10
    return score


def encode_matrix(text: str) -> list[list[bool]]:
    """Encode ``text`` into a QR boolean matrix (True = dark module)."""
    ver, align, cw = _encode_codewords(text.encode("utf-8"))
    return _build_matrix(ver, align, cw)


def svg_data_uri(text: str, scale: int = 6, border: int = 2,
                 dark: str = "#000000", light: str = "#ffffff") -> str:
    """Return an ``image/svg+xml`` data URI encoding ``text`` as a crisp QR code."""
    mat = encode_matrix(text)
    n = len(mat)
    total = (n + border * 2) * scale
    paths = []
    for r, row in enumerate(mat):
        c = 0
        while c < n:
            if not row[c]:
                c += 1
                continue
            start = c
            while c < n and row[c]:
                c += 1
            x = (start + border) * scale
            y = (r + border) * scale
            w = (c - start) * scale
            paths.append(f"M{x} {y}h{w}v{scale}h-{w}z")
    d = "".join(paths)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="{total}" '
        f'viewBox="0 0 {total} {total}" shape-rendering="crispEdges">'
        f'<rect width="100%" height="100%" fill="{light}"/>'
        f'<path fill="{dark}" d="{d}"/></svg>'
    )
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg, safe="!$&'()*+,;=:/?@-._~")
