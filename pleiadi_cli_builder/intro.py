"""The intro: full screen on solid black (the same in every terminal, even with a light background): rises from
black, a flight through stars, a constellation, two 3D shapes that turn (and morph into each other while it
stays), the title in pixel letters with a glint, the tagline and the lines under it. Pixels = half cells
(▀/▄), or quarter cells (▘▝▖▗) with PCB_PIXEL=4; truecolor or 256 colors; a key speeds it to the end (never a jump)."""
import math, os, platform, random, re, shutil, sys, time

from .term import MAC, WIN

# the real Pleiades: (name, right ascension in minutes, declination in degrees, magnitude)
PLEIADES = [("Alcyone", 227.48, 24.100, 2.9), ("Atlas", 229.15, 24.050, 3.6), ("Electra", 224.87, 24.100, 3.7),
            ("Maia", 225.82, 24.367, 3.9), ("Merope", 226.32, 23.950, 4.2), ("Taygeta", 225.20, 24.467, 4.3),
            ("Celaeno", 224.80, 24.283, 5.4)]
# 3×5 letters: 15 digits per letter, left to right and top to bottom
PIXEL_FONT = {"A": "010101111101101", "B": "110101110101110", "C": "011100100100011", "D": "110101101101110",
              "E": "111100110100111", "F": "111100110100100", "G": "011100101101011", "H": "101101111101101",
              "I": "111010010010111", "J": "001001001101010", "K": "101101110101101", "L": "100100100100111",
              "M": "101111111101101", "N": "110101101101101", "O": "010101101101010", "P": "111101111100100",
              "Q": "010101101110011", "R": "110101110101101", "S": "011100010001110", "T": "111010010010010",
              "U": "101101101101111", "V": "101101101101010", "W": "101101111111101", "X": "101101010101101",
              "Y": "101101010010010", "Z": "111001010100111", "0": "111101101101111", "1": "010110010010111",
              "2": "110001010100111", "3": "110001010001110", "4": "101101111001001", "5": "111100110001110",
              "6": "011100111101111", "7": "111001010010010", "8": "111101111101111", "9": "111101111001110",
              "-": "000000111000000", ".": "000000000000010", "!": "010010010000010", "&": "010101010101011",
              "'": "010010000000000", " ": "000000000000000"}
ACCENTS = str.maketrans("ÀÁÈÉÌÍÒÓÙÚ", "AAEEIIOOUU")
# (base, light, glint) per tint
TINTS = {"red": ("#e8253f", "#ff8a96", "#fff4f0"), "blue": ("#4a6cf7", "#a9c4ff", "#f0f4ff"),
         "violet": ("#8a5cf0", "#c9b8ff", "#f6f0ff"), "green": ("#1fae6a", "#8af0bf", "#effff6"),
         "gold": ("#e09a1a", "#ffd98a", "#fffaf0"), "cyan": ("#16a9c2", "#94eef8", "#f0feff")}
SHAPES = ("star", "sphere", "torus", "cube", "cone", "octahedron", "heart", "cylinder", "merkaba")


class Scene:
    """What the intro shows. colors = a TINTS name or three "#rrggbb" (base, light, glint); shapes = two SHAPES;
    stars = [(name, ra_minutes, dec_degrees, magnitude)] (default the Pleiades) or [] for none; lines = up to two
    short lines under the tagline (e.g. a greeting, the main commands)."""
    def __init__(self, title, tagline="", lines=(), colors="red", shapes=("star", "sphere"), stars=None):
        hexes = TINTS.get(colors, TINTS["red"]) if isinstance(colors, str) else colors
        if not (len(hexes) == 3 and all(re.match(r"^#[0-9a-fA-F]{6}$", x) for x in hexes)):
            hexes = TINTS["red"]
        self.colors = [tuple(int(x[i:i + 2], 16) for i in (1, 3, 5)) for x in hexes]
        good = [s for s in shapes if s in SHAPES][:2]
        self.shapes = (good + ["star", "sphere"])[:2] if len(good) < 2 else good
        t = "".join(ch for ch in str(title).upper().translate(ACCENTS) if ch in PIXEL_FONT)[:24].strip()
        self.title, self.tagline, self.lines = t or "HELLO", str(tagline)[:80], [str(x) for x in lines][:2]
        self.stars = PLEIADES if stars is None else stars


def shape_distance(name, x, y, z):
    """Signed distance from the surface of a shape about 1 unit big, y up: negative inside."""
    if name == "sphere":
        return math.sqrt(x * x + y * y + z * z) - 0.8
    if name == "torus":
        return math.hypot(math.hypot(x, z) - 0.56, y) - 0.26
    if name == "cube":
        dx, dy, dz = abs(x) - 0.5, abs(y) - 0.5, abs(z) - 0.5
        return math.sqrt(max(dx, 0) ** 2 + max(dy, 0) ** 2 + max(dz, 0) ** 2) + min(max(dx, dy, dz), 0) - 0.08
    if name == "octahedron":
        return (abs(x) + abs(y) + abs(z) - 0.95) * 0.577
    if name == "cylinder":
        dx, dy = math.hypot(x, z) - 0.55, abs(y) - 0.5
        return min(max(dx, dy), 0) + math.hypot(max(dx, 0), max(dy, 0)) - 0.04
    if name == "cone":  # tip up
        y -= 0.55
        qx, qy = 1.15 * 0.62, -1.15
        wx, wy = math.hypot(x, z), y
        k = max(0.0, min(1.0, (wx * qx + wy * qy) / (qx * qx + qy * qy)))
        ax, ay = wx - qx * k, wy - qy * k
        k2 = max(0.0, min(1.0, wx / qx))
        bx, by = wx - qx * k2, wy - qy
        s = max(-(wx * qy - wy * qx), -(wy - qy))
        return math.sqrt(min(ax * ax + ay * ay, bx * bx + by * by)) * (1 if s > 0 else -1)
    if name == "merkaba":  # two crossed tetrahedra
        t1 = (max(abs(x + y) - z, abs(x - y) + z) - 0.62) / 3 ** 0.5
        t2 = (max(abs(x + y) + z, abs(x - y) - z) - 0.62) / 3 ** 0.5
        return min(t1, t2)

    def extrude(d, h):
        wx, wy = d, abs(z) - h
        return min(max(wx, wy), 0) + math.hypot(max(wx, 0), max(wy, 0))
    if name == "heart":
        px, py = abs(x) * 1.05, (y + 0.55) * 1.05
        if px + py > 1:
            d = math.hypot(px - 0.25, py - 0.75) - 2 ** 0.5 / 4
        else:
            m = 0.5 * max(px + py, 0)
            d = math.sqrt(min(px * px + (py - 1) ** 2, (px - m) ** 2 + (py - m) ** 2)) * (1 if px > py else -1)
        return extrude(d, 0.1) - 0.2
    # thick five-pointed star (iq's star: the points by reflection)
    k1x, k1y, k2x = 0.809016994375, -0.587785252292, -0.809016994375
    px, py, rr, rf = abs(x), y, 0.95, 0.45
    d = max(k1x * px + k1y * py, 0); px, py = px - 2 * d * k1x, py - 2 * d * k1y
    d = max(k2x * px + k1y * py, 0); px, py = px - 2 * d * k2x, py - 2 * d * k1y
    px, py = abs(px), py - rr
    bax, bay = rf * -k1y, rf * k1x - 1
    h = max(0.0, min(rr, (px * bax + py * bay) / (bax * bax + bay * bay)))
    d = math.hypot(px - bax * h, py - bay * h) * (1 if py * bax - px * bay > 0 else -1)
    return extrude(d, 0.16) - 0.06


CLOUDS = {}


def point_cloud(name, n):
    """A shape's surface as n points with their normal: point i lies in the same direction from the center in
    every shape (Fibonacci spiral), so one shape morphs into another by moving each point."""
    if (name, n) in CLOUDS:
        return CLOUDS[(name, n)]
    f = lambda x, y, z: shape_distance(name, x, y, z)
    pts, golden = [], math.pi * (3 - 5 ** 0.5)
    for i in range(n):
        uy = 1 - 2 * (i + 0.5) / n
        ur = math.sqrt(max(0.0, 1 - uy * uy))
        ux, uz = math.cos(i * golden) * ur, math.sin(i * golden) * ur
        if name == "torus":  # it has a hole: the direction gives the ring's two angles
            th, ph = math.atan2(uz, ux), math.asin(max(-1.0, min(1.0, uy))) * 2
            rr = 0.56 + 0.26 * math.cos(ph)
            pts.append((rr * math.cos(th), 0.26 * math.sin(ph), rr * math.sin(th),
                        math.cos(ph) * math.cos(th), math.sin(ph), math.cos(ph) * math.sin(th)))
            continue
        lo, hi = 0.0, 1.8  # from the center (inside) outwards: where the distance changes sign
        for _ in range(22):
            mid = (lo + hi) / 2
            if f(ux * mid, uy * mid, uz * mid) < 0:
                lo = mid
            else:
                hi = mid
        x, y, z = ux * lo, uy * lo, uz * lo
        e = 0.003
        gx = f(x + e, y, z) - f(x - e, y, z)
        gy = f(x, y + e, z) - f(x, y - e, z)
        gz = f(x, y, z + e) - f(x, y, z - e)
        m = math.sqrt(gx * gx + gy * gy + gz * gz) or 1
        pts.append((x, y, z, gx / m, gy / m, gz / m))
    CLOUDS[(name, n)] = pts
    return pts


SYNC_ON, SYNC_OFF = "\033[?2026h", "\033[?2026l"  # synchronized output: a frame appears whole (ignored where unknown)


def truecolor():
    force = os.environ.get("PCB_COLORS", "")
    if force in ("24", "256"):
        return force == "24"
    if WIN and not os.environ.get("WT_SESSION"):
        return False  # the classic Windows console: 256 colors are the safe choice
    tp = os.environ.get("TERM_PROGRAM", "")
    return (os.environ.get("COLORTERM", "") in ("truecolor", "24bit") or bool(os.environ.get("WT_SESSION"))
            or tp in ("iTerm.app", "WezTerm", "ghostty", "vscode")
            or (MAC and tp == "Apple_Terminal" and int((platform.mac_ver()[0] or "0").split(".")[0]) >= 26))


class Renderer:
    """Builds the frames for a C×A cell area; `frame(t, spin)` → pixel buffer, `cells(buf, t, light)` → ANSI.
    Separate from `play` so it can be rendered without a terminal (tests, previews)."""
    def __init__(self, scene, cols, rows, quarter=True, true_color=True, duration=3.2):
        self.sc, self.C, self.A = scene, cols, rows - 4  # under the scene: tagline, two lines, then the prompt
        self.Q = 2 if quarter else 1
        self.W, self.PH = self.C * self.Q, self.A * 2 * self.Q
        self.true, self.steps = true_color, int(duration * 20)
        self.prev, self.memo, self.flight_t = {}, {}, 0.0
        BASE, LIGHT, GLINT = scene.colors
        W, PH = self.W, self.PH
        rnd = self.rnd = random.Random(7)
        cx, cy = self.cx, self.cy = W / 2, PH * 0.4
        s = min(W * 0.46, PH * 0.42 / 0.52)  # pixels per degree: the cluster takes half the width or ~a third of the height
        g = self.g = s / 34  # 1 = the size stars and solids are designed for
        stars = [(-(ra - 227.48) * 0.25 * 0.9135 * s, -(de - 24.1) * s, m) for _, ra, de, m in scene.stars]
        if stars:
            mx = (max(x for x, _, _ in stars) + min(x for x, _, _ in stars)) / 2
            my = (max(y for _, y, _ in stars) + min(y for _, y, _ in stars)) / 2
            stars = [(cx + x - mx, cy + y - my, m) for x, y, m in stars]
        self.stars = stars
        self.flight = [[rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0.1, 1)] for _ in range(int(60 + W * PH / 40))]
        self.field = [(rnd.uniform(0, W), rnd.uniform(0, PH), rnd.uniform(0.15, 0.6), rnd.uniform(0, 6.3))
                      for _ in range(int(W * PH / 55))]
        # the nebula is computed once: each frame only scales it
        tones = [tuple(v * k + d for v, d in zip(BASE, sp)) for k, sp in ((0.3, (0, 0, 4)), (0.24, (0, 0, 32)), (0.38, (0, 0, 0)))]
        blobs = [(sx + rnd.uniform(-5, 5) * g, sy + rnd.uniform(-3, 3) * g, rnd.uniform(7, 13) * g, rnd.uniform(4, 7) * g,
                  rnd.choice(tones)) for sx, sy, _ in stars for _ in range(2)]
        self.nebula = neb = [[[0.0, 0.0, 0.0] for _ in range(W)] for _ in range(PH)]
        for bx, by, rx, ry, c in blobs:
            for y in range(max(0, int(by - 2.5 * ry)), min(PH, int(by + 2.5 * ry) + 1)):
                for x in range(max(0, int(bx - 2.5 * rx)), min(W, int(bx + 2.5 * rx) + 1)):
                    d = ((x - bx) / rx) ** 2 + ((y - by) / ry) ** 2
                    if d < 6:
                        a = 0.42 * math.exp(-d) * rnd.uniform(0.55, 1.0)
                        p = neb[y][x]
                        p[0] += c[0] * a; p[1] += c[1] * a; p[2] += c[2] * a
        r3 = 7 * g
        side = 0.5 * s + 2.2 * r3
        pose = lambda f, k: (0.0, 0.0) if f in ("star", "heart") else (0.6 * k, 0.45)  # star and heart end facing you
        self.npts = int(max(1500, min(9000, 4 * math.pi * r3 * r3 / 1.4)))  # enough points to cover the surface
        a, b = scene.shapes
        self.solids = [(a, b, max(r3 + 1, cx - side), cy - 0.12 * s, r3, 1, *pose(a, -1)),
                       (b, a, min(W - r3 * 1.15 - 2, cx + side), cy + 0.18 * s, r3, -1, *pose(b, 1))]
        for f_ in scene.shapes:
            point_cloud(f_, self.npts)
        # the screen: 5 tones of the tint (black, dark, base, light, glint), picked by luminance with Bayer dithering
        self.TONES = [(0, 0, 0), tuple(v * 0.42 for v in BASE), BASE, LIGHT, GLINT]
        self.YT = [0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2] for c in self.TONES]
        LX, LY, LZ = -0.5 / 0.987, 0.62 / 0.987, -0.6 / 0.987  # light from top left, in front
        HX, HY, HZ = LX, LY, LZ - 1
        hm = math.sqrt(HX * HX + HY * HY + HZ * HZ)
        self.L, self.H = (LX, LY, LZ), (HX / hm, HY / hm, HZ / hm)
        name = scene.title
        if len(name) * 4 - 1 > W * 0.9:  # doesn't fit even at one pixel per cell: the first word
            name = name.split()[0][:max(1, int(W * 0.9 + 1) // 4)]
        self.name = name
        f = max(1, min(int(W * 0.8 / (len(name) * 4 - 1)), int(PH * 0.16 / 5)))  # size of a title pixel
        if self.Q == 2:
            f = max(2, f - f % 2)  # even: each title pixel covers whole rows of quadrants (no half rows)
        self.f = f
        self.tx0 = int(cx - (len(name) * 4 - 1) * f / 2)
        ty0 = int(PH * 0.8) - 5 * f // 2
        self.ty0 = ty0 + ((ty0 % 2 == 0) if f == 1 else (ty0 % 2))  # f=1: odd row (▀/▄); f even: whole cells
        self.black = self.col((0, 0, 0), True)

    BAYER4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]
    LEVELS = (0, 95, 135, 175, 215, 255)  # the real levels of the 256-color cube (not equal steps)
    QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"  # index = lit pixels: 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right

    def col(self, c, background):
        r, g, b = (min(255, max(0, int(v))) for v in c)
        if self.true:
            return f"\033[{48 if background else 38};2;{r};{g};{b}m"
        LV = self.LEVELS

        def level(v):
            i = next(k for k in range(5) if v <= LV[k + 1])
            return i + ((v - LV[i]) / (LV[i + 1] - LV[i]) > 0.5)  # the nearest (dithering here would checker)
        ir, ig, ib = level(r), level(g), level(b)
        cube = 16 + 36 * ir + 6 * ig + ib
        grey = (r + g + b) / 3
        gi = min(23, max(0, round((grey - 8) / 10)))
        if max(r, g, b) - min(r, g, b) < 14 and abs(8 + 10 * gi - grey) < abs(LV[ir] - r) + 6:
            cube = 232 + gi if grey > 4 else 16  # almost grey: the grey ramp is finer than the cube
        return f"\033[{48 if background else 38};5;{cube}m"

    def dither(self, c, bx, by):
        T, YT = self.TONES, self.YT
        y_ = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
        if y_ <= 1:
            return T[0]
        for i in range(4):
            if y_ < YT[i + 1] or i == 3:
                fr = min(1.0, (y_ - YT[i]) / ((YT[i + 1] - YT[i]) or 1))
                # the darkest tones (the nebula) as scattered dots: regular dithering makes stripes there
                th = ((bx * 92837111) ^ (by * 689287499)) % 16 if i == 0 else self.BAYER4[(by & 3) * 4 + (bx & 3)]
                return T[i + 1] if fr * 16 > th + 0.5 else T[i]

    def tone(self, lum):
        """A luminance 0..1 as a palette color (then the dithering turns it into dots)."""
        T, YT = self.TONES, self.YT
        y_ = max(0.0, min(1.0, lum)) * YT[4]
        for i in range(4):
            if y_ <= YT[i + 1]:
                fr = (y_ - YT[i]) / ((YT[i + 1] - YT[i]) or 1)
                return tuple(T[i][q] + (T[i + 1][q] - T[i][q]) * fr for q in range(3))
        return T[4]

    @staticmethod
    def morph(spin):
        """0 → 1 → 0: every ~12 s the two shapes swap, morphing (only while the scene stays)."""
        k = spin % 12.4
        if k < 5:
            return 0.0
        if k < 6.4:
            return 0.5 - 0.5 * math.cos(math.pi * (k - 5) / 1.4)
        if k < 11:
            return 1.0
        return 0.5 + 0.5 * math.cos(math.pi * (k - 11) / 1.4)

    def frame(self, t, spin=0.0):
        W, PH, Q, g, rnd = self.W, self.PH, self.Q, self.g, self.rnd
        BASE, LIGHT, GLINT = self.sc.colors

        def put(x, y, c, a):
            x, y = int(round(x)), int(round(y))
            if 0 <= x < W and 0 <= y < PH and a > 0:
                p = buf[y][x]
                p[0] += c[0] * a; p[1] += c[1] * a; p[2] += c[2] * a
        nb = max(0.0, min(1.0, (t - 0.35) / 0.4)) if self.true else 0.0  # at 256 colors the darkest red is already lit
        buf = [[[p[0] * nb, p[1] * nb, p[2] * nb] for p in row] for row in self.nebula]
        step = max(0.0, t - self.flight_t) * self.steps  # how many "right" frames since the last one (slow computers: >1)
        self.flight_t = t
        v = max(0.0, 1 - t / 0.5) ** 2 * step  # flight through the stars: fast at first, stops halfway
        cx, cy = self.cx, self.cy
        for st in self.flight:
            z0 = st[2]
            st[2] -= v * 0.13
            if st[2] < 0.06:
                st[0], st[1], st[2] = rnd.uniform(-1, 1), rnd.uniform(-1, 1), 1.0
                continue
            a = min(1.0, (1 - st[2]) * 1.7 + 0.15) * max(0.0, 1 - t / 0.55) * min(1.0, t / 0.1)  # rises from black
            k = W * 0.24
            x1, y1, x0, y0 = cx + st[0] / st[2] * k, cy + st[1] / st[2] * k * 0.5, cx + st[0] / z0 * k, cy + st[1] / z0 * k * 0.5
            n = max(1, int(abs(x1 - x0) + abs(y1 - y0)))
            for q in range(n + 1):
                fr = q / n
                put(x0 + (x1 - x0) * fr, y0 + (y1 - y0) * fr, GLINT if fr > 0.8 else LIGHT, a * (0.25 + 0.75 * fr))
        fa = max(0.0, min(1.0, (t - 0.3) / 0.3))
        for x, y, b, ph in self.field:
            for dx in range(Q):  # with quadrants one pixel is twice as tall as wide: the dot is 2 wide
                put(x + dx, y, GLINT, fa * b * (0.6 + 0.4 * math.sin((t + spin / 3) * 9 + ph)))
        sa = max(0.0, min(1.0, (t - 0.25) / 0.25))
        mf = self.morph(spin) if spin else 0.0
        mf = mf * mf * (3 - 2 * mf)
        (LX, LY, LZ), (HX, HY, HZ), npts = self.L, self.H, self.npts
        for name_a, name_b, ox, oy, r, sense, fy, fx in self.solids if sa else []:
            ay, ax = sense * (t * 2 * math.pi + spin * 0.9) + fy, (1 - t) * 3.5 + fx + 0.25 * math.sin(spin * 0.5)
            cy_, sy_, cx_, sx_ = math.cos(ay), math.sin(ay), math.cos(ax), math.sin(ax)
            oy2 = oy + math.sin(spin * 0.7 + ox) * r * 0.08  # floats gently
            ra = r * (1 - 0.2 * math.sin(math.pi * mf))  # breathes while it changes shape
            pa, pb = CLOUDS[(name_a, npts)], CLOUDS[(name_b, npts)]
            zb = {}
            for i in range(npts):
                x, y, z, nx, ny, nz = pa[i]
                if mf:
                    b_ = pb[i]
                    x, y, z = x + (b_[0] - x) * mf, y + (b_[1] - y) * mf, z + (b_[2] - z) * mf
                    nx, ny, nz = nx + (b_[3] - nx) * mf, ny + (b_[4] - ny) * mf, nz + (b_[5] - nz) * mf
                    m_ = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
                    nx, ny, nz = nx / m_, ny / m_, nz / m_
                x, z = x * cy_ + z * sy_, -x * sy_ + z * cy_
                y, z = y * cx_ - z * sx_, y * sx_ + z * cx_
                nx, nz = nx * cy_ + nz * sy_, -nx * sy_ + nz * cy_
                ny, nz = ny * cx_ - nz * sx_, ny * sx_ + nz * cx_
                if nz > 0.2:  # facing away: not visible
                    continue
                ix, iy = int(ox + x * ra), int(oy2 - y * ra)
                dif = max(0.0, nx * LX + ny * LY + nz * LZ)
                spe = max(0.0, nx * HX + ny * HY + nz * HZ) ** 26
                lum = 0.07 + 0.58 * dif + 0.62 * spe + 0.1 * (1 - abs(nz)) ** 3
                for px_, py_ in ((ix, iy), (ix + 1, iy), (ix, iy + 1), (ix + 1, iy + 1)):
                    v = zb.get((px_, py_))
                    if v is None or z < v[0]:
                        zb[(px_, py_)] = (z, lum)
            for (px_, py_), (_, lum) in zb.items():
                if 0 <= px_ < W and 0 <= py_ < PH:
                    c = self.tone(lum)
                    q = buf[py_][px_]
                    q[0] += (c[0] - q[0]) * sa; q[1] += (c[1] - q[1]) * sa; q[2] += (c[2] - q[2]) * sa
        for i, (x, y, m) in enumerate(sorted(self.stars, key=lambda st: st[2])):  # brightest first
            a = max(0.0, min(1.0, (t - 0.42 - i * 0.045) / 0.12))
            if not a:
                continue
            r = (6.2 - m) * g
            e = int(4 * g) + 1
            for dy in range(-e, e + 1):
                for dx in range(-e, e + 1):
                    put(x + dx, y + dy, BASE, a * 0.5 * math.exp(-(dx * dx + dy * dy) / (r * 0.9 * g)))
            for k in range(1, int(r) + 2):
                for dx, dy in ((k, 0), (-k, 0), (0, k), (0, -k)):
                    put(x + dx, y + dy, LIGHT, a * 0.9 / (k / g))
            put(x, y, GLINT, a * 1.2)
        na = max(0.0, min(1.0, (t - 0.72) / 0.15))  # the title, with a glint passing over it
        f, name = self.f, self.name
        glint = self.tx0 + (t - 0.8) / 0.2 * (len(name) * 4 + 8) * f
        for j, ch in enumerate(name):
            for k, b in enumerate(PIXEL_FONT.get(ch, PIXEL_FONT[" "])):
                if b == "1":
                    for qy in range(f):
                        for qx in range(f):
                            x, y = self.tx0 + (j * 4 + k % 3) * f + qx, self.ty0 + (k // 3) * f + qy
                            lt = max(0.0, 1 - abs(x - glint) / (4 * f))  # solid tint: dithered letters look striped
                            put(x, y, tuple(BASE[q] + (GLINT[q] - BASE[q]) * lt for q in range(3)), na)
        return buf

    def quad_cell(self, px):
        """4 pixels (top-left, top-right, bottom-left, bottom-right) → (fg, bg, char): the two groups of pixels
        with the least error, since a character has only two colors. Cells already seen come from memory."""
        memo = self.memo
        key = tuple(int(v) >> 2 for p in px for v in p)
        if key in memo:
            return memo[key]
        if max(sum(p) for p in px) <= 9:
            memo[key] = None, None, " "
            return memo[key]
        if max(px[i][q] for i in range(4) for q in range(3)) - min(px[i][q] for i in range(4) for q in range(3)) < 6:
            memo[key] = None, px[0], " "
            return memo[key]
        best = None
        for m in range(1, 8):  # bottom-right always in the "back" group: each split once
            a = [px[i] for i in range(4) if m >> i & 1]
            b = [px[i] for i in range(4) if not m >> i & 1]
            ma = [sum(p[q] for p in a) / len(a) for q in range(3)]
            mb = [sum(p[q] for p in b) / len(b) for q in range(3)]
            err = sum((p[q] - ma[q]) ** 2 for p in a for q in range(3)) + sum((p[q] - mb[q]) ** 2 for p in b for q in range(3))
            if best is None or err < best[0]:
                best = (err, m, ma, mb)
        _, m, ma, mb = best
        memo[key] = (None, ma, " ") if max(abs(ma[q] - mb[q]) for q in range(3)) < 6 else (ma, mb, self.QUADRANTS[m])
        if len(memo) > 200000:
            memo.clear()
        return memo[key]

    def cells(self, buf, t, light=1.0):
        """The ANSI for one frame: only the cells that changed since the previous one (fewer bytes on slow
        terminals), then the text lines."""
        out, black, C, A = [], self.black, self.C, self.A
        for r in range(A):
            s_, last, jump = [], None, True
            for x in range(C):
                if self.Q == 2:  # 2×4 square pixels → 2×2 (row pairs averaged)
                    y = 4 * r
                    px = [self.dither([(buf[y + dy][2 * x + dx][q] + buf[y + dy + 1][2 * x + dx][q]) / 2 for q in range(3)],
                                      2 * x + dx, 2 * r + dy // 2)
                          for dy, dx in ((0, 0), (0, 1), (2, 0), (2, 1))]
                    fg, bg, ch = self.quad_cell(px)
                    if ch == " ":
                        code = (self.col(bg, True) if bg and sum(bg) > 9 else black, " ")
                    else:
                        code = (self.col(fg, False) + (self.col(bg, True) if sum(bg) > 9 else black), ch)
                else:
                    a, b = self.dither(buf[2 * r][x], x, 2 * r), self.dither(buf[2 * r + 1][x], x, 2 * r + 1)
                    la, lb = sum(a) > 9, sum(b) > 9
                    if la and lb and max(abs(a[q] - b[q]) for q in range(3)) < 6:
                        code = (self.col(a, True), " ")  # whole cell from the background: no glyph edge
                    elif la and lb:
                        code = (self.col(a, False) + self.col(b, True), "▀")
                    elif la:
                        code = (self.col(a, False) + black, "▀")
                    elif lb:
                        code = (self.col(b, False) + black, "▄")
                    else:
                        code = (black, " ")
                if self.prev.get((r, x)) == code:
                    jump = True
                    continue
                self.prev[(r, x)] = code
                if jump:
                    s_.append(f"\033[{r + 1};{x + 1}H")
                    jump, last = False, None
                s_.append(("" if code[0] == last else code[0]) + code[1])
                last = code[0]
            out.append("".join(s_))
        tag = self.sc.tagline
        n = int(max(0.0, min(1.0, (t - 0.85) / 0.15)) * len(tag) + 0.999) if t > 0.85 else 0
        lines = self.sc.lines + [""] * (2 - len(self.sc.lines))
        texts = [(tag[:n], self.sc.colors[1], "\033[3m"), (lines[0] if t >= 1 else "", (150, 150, 160), ""),
                 (lines[1] if t >= 1 else "", (110, 110, 120), "")]
        for i, (text, c, style) in enumerate(texts):
            text, c = text[:C], tuple(v * light for v in c)
            full = len(tag) if i == 0 else len(text)
            out.append(f"\033[{A + 1 + i};1H" + black + " " * C + f"\033[{A + 1 + i};{max(1, (C - full) // 2 + 1)}H"
                       + black + self.col(c, False) + style + text + "\033[0m")
        return "".join(out)


def play(scene, duration=3.2, hold=False, fade=False, screensaver=False):
    """Plays the intro. hold: the shapes keep turning until a key; fade: dissolve to black before leaving (when
    something else comes on screen next); screensaver: on the alternate screen, fades in, floats until a key,
    then the previous screen comes back as it was. Outside a terminal: prints the tagline only."""
    if screensaver:
        hold, fade = True, True
    if not sys.stdout.isatty():
        return 0
    cols, rows = shutil.get_terminal_size((80, 24))
    if cols < 40 or rows < 14:
        print(scene.tagline)
        return 0
    if WIN:
        os.system("")  # ANSI sequences in the Windows console
    # half blocks (▀▄) by default: square pixels and in every font; quadrants (▘▝▖▗) only when asked — many
    # terminal fonts lack them or leave gaps between rows, and they show vertical stripes (owner 29/10: «tutta rotta»)
    rd = Renderer(scene, cols, rows, quarter=os.environ.get("PCB_PIXEL") == "4", true_color=truecolor(),
                  duration=duration)
    pressed, saved = (lambda: False), None
    if WIN:
        import msvcrt
        pressed = msvcrt.kbhit
    else:
        import select, termios, tty
        try:
            saved = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            pressed = lambda: bool(select.select([sys.stdin], [], [], 0)[0])
        except Exception:
            saved = None
    black = rd.black
    sys.stdout.write(("\033[?1049h" if screensaver else "") + "\033[?25l" + black + "\033[2J")
    try:
        t0, fast = time.time(), None
        while not screensaver:  # t from real time: a slow computer gets fewer frames, same duration
            start = time.time()
            if fast is None and pressed():
                fast = (min(1.0, (start - t0) / duration), start)  # a key: to the end in 0.35 s, no jump
            t = (min(1.0, (start - t0) / duration) if fast is None else
                 min(1.0, fast[0] + (1 - fast[0]) * (start - fast[1]) / 0.35))
            sys.stdout.write(SYNC_ON + rd.cells(rd.frame(t), t) + SYNC_OFF)
            sys.stdout.flush()
            if t >= 1.0:
                break
            time.sleep(max(0.0, duration / rd.steps - (time.time() - start)))
        since = time.time()
        while hold and not pressed():  # the shapes keep turning, slowly (the screensaver fades in)
            spin = time.time() - since
            light = min(1.0, spin / 0.8) ** 2 if screensaver else 1.0
            buf = rd.frame(1.0, spin)
            if light < 1:
                buf = [[[v * light for v in p] for p in row] for row in buf]
            sys.stdout.write(SYNC_ON + rd.cells(buf, 1.0, light) + SYNC_OFF)
            sys.stdout.flush()
            time.sleep(0.06)
        if fade:  # dissolves to black (0.4 s), then a clean screen for what comes next
            spin, start = time.time() - since, time.time()
            while (k := (time.time() - start) / 0.4) < 1:
                light = (1 - k) ** 2
                buf = [[[v * light for v in p] for p in row] for row in rd.frame(1.0, spin + k * 0.4)]
                sys.stdout.write(SYNC_ON + rd.cells(buf, 1.0, light) + SYNC_OFF)
                sys.stdout.flush()
                time.sleep(0.03)
            sys.stdout.write(black + "\033[2J\033[H")
    finally:
        sys.stdout.write("\033[0m\033[?25h\033[?1049l" if screensaver else f"\033[0m\033[{rd.A + 4};1H\033[?25h")
        sys.stdout.flush()
        if saved is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)
            while select.select([sys.stdin], [], [], 0)[0]:
                os.read(sys.stdin.fileno(), 64)  # the key that skipped doesn't end up in the prompt
    return 0
