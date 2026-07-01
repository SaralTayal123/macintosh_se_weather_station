"""
render.py — server-side 1-bit renderer for the SE weather display (the "C2" design).

Produces a 512x342, 1-bit GIF that reproduces the canvas/JS preview exactly: pixel
weather icons, cool->warm dithered 5-day range bars, and a day/night dithered
temperature graph, laid out with authentic Chicago / Geneva / Monaco fonts.

We draw everything onto an 8-bit "L" image (graphics as pure 0/255, text anti-aliased),
then threshold to mode "1" so the result is honestly 1 bit-per-pixel. This is the
"custom dithering module" the project roadmap called for.

NOTE on display: MacWeb 2.0 cannot show GIFs inline (helper-app only), and the SE's
68000 rules out inline-image browsers (Netscape/Mosaic need 68020+). So this GIF is
for an emulator / 68020+ Mac / verification — the live SE page is HTML (see wx.py).
"""

import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

W, H = 512, 342
WHITE, BLACK = 255, 0
_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def _font(name, size):
    return ImageFont.truetype(os.path.join(_FONTS, name + ".ttf"), size)


# Fonts: Chicago = titles/big numbers, Geneva = labels, Monaco = tabular numerals.
def fonts():
    return {
        "loc": _font("Chicago", 15),
        "dt": _font("Chicago", 14),
        "temp": _font("Chicago", 46),
        "cond": _font("Chicago", 15),
        "hd": _font("Chicago", 13),
        "day": _font("Chicago", 13),
        "today": _font("Chicago", 12),
        "label": _font("Geneva", 12),
        "mono": _font("Monaco", 12),
        "monosm": _font("Monaco", 11),
    }


# ---- ordered dither (4x4 Bayer) -------------------------------------------
BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def ink(x, y, density):
    return density > (BAYER4[y & 3][x & 3] + 0.5) / 16.0


# ---- low-level pixel helpers (operate on PIL PixelAccess) -------------------
def pset(px, x, y, v=BLACK):
    if 0 <= x < W and 0 <= y < H:
        px[x, y] = v


def pline(px, x0, y0, x1, y1, v=BLACK):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        pset(px, x0, y0, v)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def pcircle(px, cx, cy, r, v=BLACK):
    x, y, err = r, 0, 1 - r
    while x >= y:
        for a, b in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
            pset(px, cx + a, cy + b, v)
        y += 1
        if err < 0:
            err += 2 * y + 1
        else:
            x -= 1
            err += 2 * (y - x) + 1


def fillrect(px, x0, y0, w, h, v=BLACK):
    for yy in range(int(y0), int(y0 + h)):
        for xx in range(int(x0), int(x0 + w)):
            pset(px, xx, yy, v)


# ---- weather icon grids (24x24) --------------------------------------------
def _grid():
    return [[0] * 24 for _ in range(24)]


def _disk(g, cx, cy, r):
    for y in range(24):
        for x in range(24):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                g[y][x] = 1


def _set(g, x, y):
    if 0 <= x < 24 and 0 <= y < 24:
        g[y][x] = 1


def _seg(g, x0, y0, x1, y1):
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        _set(g, x0, y0)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def _outline(g):
    o = _grid()
    for y in range(24):
        for x in range(24):
            if not g[y][x]:
                continue
            inside = 0 < y < 23 and 0 < x < 23 and g[y - 1][x] and g[y + 1][x] and g[y][x - 1] and g[y][x + 1]
            o[y][x] = 0 if inside else 1
    return o


def _sun():
    g = _grid()
    c = 11
    _disk(g, c, c, 5)
    for k in (8, 9, 10):
        _set(g, c, c - k); _set(g, c, c + k); _set(g, c - k, c); _set(g, c + k, c)
        d = round(k * 0.72)
        _set(g, c - d, c - d); _set(g, c + d, c - d); _set(g, c - d, c + d); _set(g, c + d, c + d)
    return g


def _blob(up):
    g = _grid()
    oy = -3 if up else 0
    _disk(g, 8, 15 + oy, 5); _disk(g, 16, 14 + oy, 6); _disk(g, 12, 12 + oy, 5)
    for x in range(6, 20):
        for y in range(15 + oy, 19 + oy):
            _set(g, x, y)
    return g


def _cloud():
    return _outline(_blob(False))


def _rain():
    g = _outline(_blob(True))
    for x in (8, 13, 18):
        _seg(g, x, 16, x - 2, 22)
    return g


def _storm():
    g = _outline(_blob(True))
    b = [(13, 14), (11, 18), (13, 18), (10, 23)]
    for i in range(len(b) - 1):
        _seg(g, b[i][0], b[i][1], b[i + 1][0], b[i + 1][1])
    return g


def _snow():
    g = _outline(_blob(True))
    for fx, fy in ((8, 19), (14, 21), (18, 18)):
        _set(g, fx, fy); _set(g, fx - 1, fy); _set(g, fx + 1, fy); _set(g, fx, fy - 1); _set(g, fx, fy + 1)
    return g


def _partly():
    g = _grid()
    c = 8
    _disk(g, c, c, 3)
    for k in (5, 6):
        _set(g, c, c - k); _set(g, c - k, c); _set(g, c + k, c - k)
    cl = _outline(_blob(False))
    for y in range(24):
        for x in range(24):
            if cl[y][x]:
                g[y][x] = 1
    return g


ICONS = {"sun": _sun, "cloud": _cloud, "rain": _rain, "storm": _storm, "snow": _snow, "partly": _partly}


def draw_icon(px, name, x, y, scale):
    g = ICONS.get(name, _sun)()
    for gy in range(24):
        for gx in range(24):
            if g[gy][gx]:
                fillrect(px, x + gx * scale, y + gy * scale, scale, scale)


# ---- cool->warm dithered 5-day range bar -----------------------------------
def range_bar(px, x, y, day, wk_min, wk_max, width=132, height=13):
    span = (wk_max - wk_min) or 1

    def col(t):
        c = round((t - wk_min) / span * (width - 1))
        return max(0, min(width - 1, c))

    lo, hi = col(day["lo"]), col(day["hi"])
    for cx in range(width):
        for cy in range(height):
            v = WHITE
            if cy == height - 1:
                if cx % 3 == 0:
                    v = BLACK
            elif lo <= cx <= hi and 1 <= cy <= height - 3:
                if ink(cx, cy, 0.12 + (cx / (width - 1)) * 0.86):
                    v = BLACK
            if v == BLACK:
                pset(px, x + cx, y + cy, BLACK)
    if day.get("cur") is not None:
        cc = max(lo, min(hi, col(day["cur"])))
        for cy in range(height - 1):
            for dx in (-1, 0, 1):
                pset(px, x + cc + dx, y + cy, BLACK)


# ---- day/night dithered temperature graph (C2) -----------------------------
def temp_graph(px, x, y, w, h, wx):
    series = wx["hourly"]
    n = len(series)
    sun = wx["sun"]
    pad_l, pad_r, pad_top, axis_h = 2, 2, 3, 11
    tmin = (min(series) - 3) // 5 * 5
    tmax = -(-(max(series) + 3) // 5) * 5  # ceil to 5
    if tmax <= tmin:                       # guard a flat series
        tmax = tmin + 5
    inner_w = w - pad_l - pad_r
    plot_bot = h - axis_h
    fill_day, fill_night = 0.12, 0.42
    span_h = max(1, n - 1)                 # guard a single hourly point
    span_x = max(1, inner_w - 1)

    def X(hf):
        return pad_l + round((hf / span_h) * (inner_w - 1))

    def Y(t):
        return plot_bot - round(((t - tmin) / (tmax - tmin)) * (plot_bot - pad_top))

    def hour_at(cx):
        return ((cx - pad_l) / span_x) * (n - 1)

    def y_at(cx):
        hf = hour_at(cx)
        a = max(0, min(n - 1, int(hf)))
        b = min(n - 1, a + 1)
        return series[a] + (series[b] - series[a]) * (hf - a)

    # area fill (lighter by day, denser after sunset)
    for cx in range(pad_l, w - pad_r):
        hf = hour_at(cx)
        night = hf < sun["riseHour"] or hf > sun["setHour"]
        cy_curve = Y(y_at(cx))
        for cy in range(cy_curve, plot_bot):
            if ink(cx, cy, fill_night if night else fill_day):
                pset(px, x + cx, y + cy, BLACK)
    # baseline + sunrise/sunset ticks
    pline(px, x + pad_l, y + plot_bot, x + w - pad_r, y + plot_bot)
    for hh in (sun["riseHour"], sun["setHour"]):
        sx = X(hh)
        for cy in range(pad_top, plot_bot, 2):
            pset(px, x + sx, y + cy)
    # the curve (2px)
    for cx in range(pad_l, w - pad_r - 1):
        pline(px, x + cx, y + Y(y_at(cx)), x + cx + 1, y + Y(y_at(cx + 1)))
        pset(px, x + cx, y + Y(y_at(cx)) - 1)
    # hi / lo = hollow rings
    for hh, tt in ((wx["hiHour"], wx["hiTemp"]), (wx["loHour"], wx["loTemp"])):
        dx, dy = X(hh), Y(tt)
        fillrect(px, x + dx - 3, y + dy - 3, 7, 7, WHITE)
        pcircle(px, x + dx, y + dy, 3)
    # now = time cursor + solid square
    now_hf = wx["nowHour"] + wx["nowMin"] / 60.0
    nx = X(now_hf)
    for cy in range(pad_top, plot_bot):
        if cy % 2 == 0:
            pset(px, x + nx, y + cy)
    ny = Y(y_at(nx))
    fillrect(px, x + nx - 2, y + ny - 3, 5, 6)


# ---- full layout (the C2 design) -------------------------------------------
def render_image(wx):
    img = Image.new("L", (W, H), WHITE)
    px = img.load()
    draw = ImageDraw.Draw(img)
    F = fonts()

    def text(xy, s, font, anchor="la"):
        draw.text(xy, s, font=font, fill=BLACK, anchor=anchor)

    # --- top bar ---
    text((12, 6), wx["loc"], F["loc"])
    text((W - 12, 7), wx["dateline"], F["dt"], anchor="ra")
    pline(px, 0, 26, W, 26)

    # --- left column (centered): icon, big temp, condition, stats ---
    LX, LW = 0, 190
    cxl = LX + LW // 2
    draw_icon(px, wx["icon"], cxl - 36, 34, 3)             # 24*3 = 72px, centered
    text((cxl, 110), "%d°" % wx["temp"], F["temp"], anchor="ma")
    text((cxl, 162), wx["cond"], F["cond"], anchor="ma")
    pline(px, 14, 190, 176, 190)
    stats = [
        ("Feels like", "%d°" % wx["feels"]),
        ("UV index", str(wx["uv"])),
        ("Humidity", "%d%%" % wx["hum"]),
        ("Wind", "%d %s" % (wx["wind"], wx["wdir"])),
        ("Sunrise", wx["sun"]["rise"]),
        ("Sunset", wx["sun"]["set"]),
    ]
    sy = 198
    for label, val in stats:
        text((14, sy), label, F["label"])
        text((176, sy), val, F["mono"], anchor="ra")
        sy += 19
    pline(px, LW, 27, LW, H)                               # column divider

    # --- right column: 5-day outlook + today graph ---
    RX = 202
    text((RX, 34), "FIVE-DAY OUTLOOK", F["hd"])
    pline(px, RX, 51, 500, 51)
    pline(px, RX, 52, 500, 52)
    ry = 58
    for d in wx["days"]:
        text((RX + 2, ry + 3), d["d"], F["day"])
        draw_icon(px, d["icon"], RX + 48, ry, 1)
        text((RX + 96, ry + 4), str(d["lo"]), F["mono"], anchor="ra")
        range_bar(px, RX + 102, ry + 2, d, wx["wkMin"], wx["wkMax"])
        text((RX + 250, ry + 4), str(d["hi"]), F["mono"], anchor="ra")
        ry += 27

    # today header + graph, tucked under the table
    ty = ry + 6
    text((RX, ty), "TODAY", F["today"])
    text((500, ty + 1), "%d–%d°" % (wx["loTemp"], wx["hiTemp"]), F["monosm"], anchor="ra")
    pline(px, RX, ty - 4, 500, ty - 4)
    gx, gy = RX, ty + 16
    temp_graph(px, gx, gy, 500 - RX, H - gy - 4, wx)

    return img.convert("1", dither=Image.NONE)


def render_gif_bytes(wx):
    buf = BytesIO()
    render_image(wx).save(buf, format="GIF")
    return buf.getvalue()


# ---- small standalone component images (for the hybrid HTML+XBM page) -------
# Each returns a mode-"1" image of just that graphic, so the page can be mostly
# fast HTML text with only the dithered bits as tiny inline XBMs.
#
# The pixel helpers bounds-check against the full screen (W,H), so we draw each
# component at the origin of a full-size canvas and crop it out.

def _canvas():
    img = Image.new("L", (W, H), WHITE)
    return img, img.load()


def comp_icon(name, scale=3):
    s = 24 * scale
    img, px = _canvas()
    draw_icon(px, name, 0, 0, scale)
    return img.crop((0, 0, s, s)).convert("1", dither=Image.NONE)


def comp_bar(day, wk_min, wk_max, bar_w=144, bar_h=13):
    img, px = _canvas()
    range_bar(px, 0, 0, day, wk_min, wk_max, width=bar_w, height=bar_h)
    return img.crop((0, 0, bar_w, bar_h)).convert("1", dither=Image.NONE)


# lpad = built-in blank left margin so these images sit off the vertical divider
LPAD = 16


def comp_graph(wx, w=300, h=58, lpad=LPAD):
    img, px = _canvas()
    temp_graph(px, lpad, 0, w - lpad, h, wx)
    return img.crop((0, 0, w, h)).convert("1", dither=Image.NONE)


def comp_forecast(wx, w=300, rowh=24, lpad=LPAD):
    """The ENTIRE 5-day block as ONE image: day name + condition icon + low + cool->warm
    dithered range bar + high, per row. Collapsing ~11 little images into one keeps the
    page under MacWeb's inline-image limit (the cause of the dropped graph)."""
    rows = wx["days"]
    h = len(rows) * rowh
    img, px = _canvas()
    draw = ImageDraw.Draw(img)
    f_day = _font("Chicago", 12)
    f_num = _font("Monaco", 13)
    bar_w, bar_h = 144, 13
    x_day = 2 + lpad
    x_icon, x_lo_r, x_bar = 52 + lpad, 100 + lpad, 104 + lpad
    x_hi = x_bar + bar_w + 6
    for i, d in enumerate(rows):
        y = i * rowh
        cy = y + rowh // 2
        draw.text((x_day, cy), d["d"], font=f_day, fill=BLACK, anchor="lm")
        draw_icon(px, d["icon"], x_icon, y + (rowh - 24) // 2, 1)
        draw.text((x_lo_r, cy), "%d°" % d["lo"], font=f_num, fill=BLACK, anchor="rm")
        range_bar(px, x_bar, y + (rowh - bar_h) // 2, d, wx["wkMin"], wx["wkMax"],
                  width=bar_w, height=bar_h)
        draw.text((x_hi, cy), "%d°" % d["hi"], font=f_num, fill=BLACK, anchor="lm")
    return img.crop((0, 0, w, h)).convert("1", dither=Image.NONE)


def comp_rule(w=504, h=2, loff=0):
    """A solid black bar — a tight replacement for MacWeb's spacious <hr>, which forces
    large uncontrollable vertical margins. `loff` leaves that many blank pixels on the
    left (used to nudge a divider right / align it with padded content)."""
    img = Image.new("1", (w, h), 1)    # white
    if loff < w:
        ImageDraw.Draw(img).rectangle([loff, 0, w - 1, h - 1], fill=0)  # black bar
    return img


def comp_vrule(h=232, w=2):
    """A solid black vertical bar — the divider between the left and right columns."""
    return Image.new("1", (w, h), 0)


# Pillow save-format per file extension (mode "1" images).
SAVE_FORMAT = {"gif": "GIF", "xbm": "XBM", "pbm": "PPM", "bmp": "BMP"}


def image_bytes(img, ext):
    # XBM convention: a SET bit = black (foreground), the opposite of PIL mode "1"
    # (0=black). Without this flip, every XBM renders inverted on the SE.
    if ext == "xbm":
        from PIL import ImageChops
        img = ImageChops.invert(img.convert("L")).convert("1", dither=Image.NONE)
    buf = BytesIO()
    img.save(buf, format=SAVE_FORMAT[ext])
    return buf.getvalue()


def test_pattern(label, w=128, h=44):
    """A small, self-labeling 1-bit image for the inline-format probe page.
    Whatever renders on the SE literally tells you which format it is."""
    img = Image.new("L", (w, h), WHITE)
    px = img.load()
    for x in range(w):
        pset(px, x, 0); pset(px, x, h - 1)
    for y in range(h):
        pset(px, 0, y); pset(px, w - 1, y)
    for x in range(w):  # diagonal hatch so it's unmistakably an image
        if x % 6 == 0:
            pline(px, x, 1, x - 30, h - 2, WHITE if x % 12 == 0 else BLACK)
    ImageDraw.Draw(img).text((w // 2, h // 2), label, font=_font("Chicago", 20),
                             fill=BLACK, anchor="mm")
    return img.convert("1", dither=Image.NONE)


# ---- demo data (matches the preview's "clear" scenario) --------------------
DEMO = {
    "loc": "PALO ALTO, CA", "dateline": "FRI JUN 19  6:13 PM",
    "temp": 71, "feels": 67, "cond": "CLEAR", "icon": "sun",
    "hum": 59, "wind": 14, "wdir": "SW", "uv": 6,
    "nowHour": 18, "nowMin": 13,
    "sun": {"riseHour": 5.8, "setHour": 20.57, "rise": "5:48a", "set": "8:34p"},
    "hiTemp": 76, "hiHour": 14, "loTemp": 56, "loHour": 4,
    "hourly": [58, 57, 56, 56, 56, 56, 58, 61, 64, 67, 70, 72, 74, 75, 76, 76, 75, 73, 71, 68, 66, 64, 62, 60],
    "days": [
        {"d": "TODAY", "icon": "cloud", "lo": 58, "hi": 76, "cur": 71},
        {"d": "SAT", "icon": "cloud", "lo": 58, "hi": 74},
        {"d": "SUN", "icon": "cloud", "lo": 53, "hi": 84},
        {"d": "MON", "icon": "sun", "lo": 56, "hi": 84},
        {"d": "TUE", "icon": "sun", "lo": 58, "hi": 87},
    ],
    "wkMin": 53, "wkMax": 87,
}


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "preview", "wx_c2.gif")
    render_image(DEMO).save(out, format="GIF")
    print("wrote", os.path.abspath(out))
