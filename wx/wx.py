"""
SE Weather - a Macintosh SE optimized weather display, served as a macproxy extension.

Browse to http://wx.com/ from the vintage machine.

The live SE page is MacWeb-friendly HTML (the "C2" almanac layout): a two-column
table using the SE's own Chicago / Geneva / Monaco fonts, ASCII cool->warm range bars,
and an ASCII today-temperature chart. MacWeb 2.0 renders this directly.

We ALSO render a pixel-perfect 1-bit GIF of the same design (render.py). MacWeb can't
show GIFs inline (helper-app only) and the SE's 68000 rules out inline-image browsers,
so the GIF is for an emulator / 68020+ Mac / verification:
    http://wx.com/wx.gif        the rendered 512x342 1-bit GIF
    http://wx.com/gif-test      a page that tries to inline it (to confirm SE behavior)

Note: the domain intentionally uses a real TLD (.com) — MacWeb mangles made-up TLDs.
"""

import datetime
import requests
from flask import Response

DOMAIN = "wx.com"

# --- Configuration -----------------------------------------------------------
LATITUDE = 37.4419
LONGITUDE = -122.1430
LOCATION_NAME = "PALO ALTO, CA"
TIMEZONE = "America/Los_Angeles"

REFRESH_SECONDS = 300         # cosmetic for MacWeb; real cadence is the KeyQuencer Wait.
                              # Bumped so a slow image download isn't interrupted mid-load.
REFRESH_URL = "http://wx.com/"
FORECAST_DAYS = 5

# Inline image format for the live display. XBM confirmed to render inline in MacWeb on
# the SE; PBM is the SAME 1-bit image at ~1/5 the bytes (22KB vs 110KB) IF MacWeb inlines
# it too (test at wx.com/test-pbm). Flip this to "pbm" once confirmed for a big speedup.
DISPLAY_FORMAT = "xbm"

API_URL = "https://api.open-meteo.com/v1/forecast"
DEG = "°"                # U+00B0; encodes to 0xB0 in Latin-1, which MacWeb renders as °
PAGE_W = 474             # fixed page width: 512 screen minus scrollbar + right margin

WMO = {
    0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Cloudy",
    45: "Fog", 48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Drizzle", 57: "Drizzle",
    61: "Rain", 63: "Rain", 65: "Rain", 66: "Rain", 67: "Rain",
    71: "Snow", 73: "Snow", 75: "Snow", 77: "Snow",
    80: "Showers", 81: "Showers", 82: "Showers", 85: "Snow", 86: "Snow",
    95: "Storm", 96: "Storm", 99: "Storm",
}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def wmo_label(code):
    return WMO.get(int(code), "?")


def wmo_icon(code):
    code = int(code)
    if code == 0:
        return "sun"
    if code in (1, 2):
        return "partly"
    if code in (3, 45, 48):
        return "cloud"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "storm"
    return "rain"  # 51-67 drizzle/rain, 80-82 showers


def compass(deg):
    return COMPASS[int((deg % 360) / 45.0 + 0.5) % 8]


# ---- data fetch + normalize -------------------------------------------------
# The page pulls 8 resources per reload (HTML + 7 XBMs). Cache the API result so a
# reload makes ONE Open-Meteo call (not 8) — avoids rate-limiting and guarantees all
# images in one reload use the same data snapshot.
_CACHE_TTL = 120  # seconds
_cache = {"ts": 0.0, "data": None}

# --- status file (read by the Pi touchscreen UI) -----------------------------
# The proxy is the thing the SE talks to, so it's the natural place to record
# "when did the Mac last ping". We also expose a refresh-flag: the UI touches the
# flag file to force the next fetch to bypass the cache.
import os as _os
import time as _time
STATUS_FILE = _os.environ.get("WX_STATUS_FILE", "/tmp/wx-status.json")
REFRESH_FLAG = _os.environ.get("WX_REFRESH_FLAG", "/tmp/wx-refresh.flag")
_status = {"last_seen": 0.0, "count": 0, "temp": None, "cond": None,
           "fetch_ok": None, "last_fetch": 0.0, "started": _time.time()}


def _write_status():
    try:
        import json
        tmp = STATUS_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(_status, fh)
        _os.replace(tmp, STATUS_FILE)
    except Exception:
        pass  # status is best-effort; never let it break request handling


def _note_request():
    _status["last_seen"] = _time.time()
    _status["count"] += 1
    _write_status()


def fetch_weather():
    now = _time.time()
    # UI-triggered force refresh: bypass the cache if the flag is newer than it
    forced = False
    try:
        if _os.path.exists(REFRESH_FLAG) and _os.path.getmtime(REFRESH_FLAG) > _cache["ts"]:
            forced = True
    except OSError:
        pass
    if not forced and _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]
    try:
        data = _fetch_weather_uncached()
        _status["fetch_ok"] = True
    except Exception:
        _status["fetch_ok"] = False
        _write_status()
        raise
    _status["last_fetch"] = now
    _cache["data"] = data
    _cache["ts"] = now
    return data


def _fetch_weather_uncached():
    params = {
        "latitude": LATITUDE, "longitude": LONGITUDE,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,wind_speed_10m,wind_direction_10m,surface_pressure",
        "hourly": "temperature_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,uv_index_max,sunrise,sunset",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "precipitation_unit": "inch", "timezone": TIMEZONE,
        "forecast_days": FORECAST_DAYS,
    }
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _hm(iso):
    """'2026-06-19T05:48' -> ('5:48a', 5.8) ."""
    t = datetime.datetime.strptime(iso[:16], "%Y-%m-%dT%H:%M")
    h12 = t.hour % 12 or 12
    ampm = "a" if t.hour < 12 else "p"
    return "%d:%02d%s" % (h12, t.minute, ampm), t.hour + t.minute / 60.0


def normalize(data):
    """Open-Meteo JSON -> the single data dict used by both HTML and GIF renderers."""
    cur, daily = data["current"], data["daily"]
    now = datetime.datetime.now()

    # today's 24 hourly temps
    today = data["current"]["time"][:10]
    htimes, htemps = data["hourly"]["time"], data["hourly"]["temperature_2m"]
    hourly = [round(t) for t, ts in zip(htemps, htimes) if ts[:10] == today][:24]
    if len(hourly) < 24:  # pad defensively
        hourly = (hourly + [hourly[-1]] * 24)[:24] if hourly else [round(cur["temperature_2m"])] * 24
    hi_t, lo_t = max(hourly), min(hourly)

    rise_s, rise_h = _hm(daily["sunrise"][0])
    set_s, set_h = _hm(daily["sunset"][0])

    days = []
    for i in range(len(daily["time"])):
        d = "TODAY" if i == 0 else datetime.datetime.strptime(daily["time"][i], "%Y-%m-%d").strftime("%a").upper()
        days.append({
            "d": d, "icon": wmo_icon(daily["weather_code"][i]),
            "lo": round(daily["temperature_2m_min"][i]),
            "hi": round(daily["temperature_2m_max"][i]),
            "pop": daily["precipitation_probability_max"][i] or 0,
            "cur": round(cur["temperature_2m"]) if i == 0 else None,
        })
    wk_min = min(d["lo"] for d in days)
    wk_max = max(d["hi"] for d in days)

    out = {
        "loc": LOCATION_NAME,
        "dateline": now.strftime("%a %b %-d  %-I:%M %p").upper(),
        "temp": round(cur["temperature_2m"]),
        "feels": round(cur["apparent_temperature"]),
        "cond": wmo_label(cur["weather_code"]).upper(),
        "icon": wmo_icon(cur["weather_code"]),
        "hum": round(cur["relative_humidity_2m"]),
        "wind": round(cur["wind_speed_10m"]),
        "wdir": compass(cur["wind_direction_10m"]),
        "uv": round(daily["uv_index_max"][0]) if daily.get("uv_index_max") else 0,
        "nowHour": now.hour, "nowMin": now.minute,
        "sun": {"riseHour": rise_h, "setHour": set_h, "rise": rise_s, "set": set_s},
        "hiTemp": hi_t, "hiHour": hourly.index(hi_t),
        "loTemp": lo_t, "loHour": hourly.index(lo_t),
        "hourly": hourly, "days": days, "wkMin": wk_min, "wkMax": wk_max,
    }
    _status["temp"] = out["temp"]
    _status["cond"] = out["cond"]
    _write_status()
    return out


# ---- ASCII pieces for the HTML page ----------------------------------------
def ascii_range_bar(day, wk_min, wk_max, width=14):
    span = (wk_max - wk_min) or 1

    def col(t):
        return max(0, min(width - 1, int(round((t - wk_min) / span * (width - 1)))))

    lo, hi = col(day["lo"]), col(day["hi"])
    cells = ["-"] * width
    for i in range(lo, hi + 1):
        cells[i] = "="
    if day.get("cur") is not None:
        cells[max(lo, min(hi, col(day["cur"])))] = "O"
    return "".join(cells)


def ascii_today_chart(wx, cols=24, rows=6):
    h = wx["hourly"]
    tmin, tmax = min(h), max(h)
    span = (tmax - tmin) or 1
    rise, sset = wx["sun"]["riseHour"], wx["sun"]["setHour"]
    grid = [[" "] * cols for _ in range(rows)]
    for x in range(cols):
        lvl = int(round((h[x] - tmin) / span * (rows - 1)))
        rc = (rows - 1) - lvl
        night = x < rise or x > sset
        for r in range(rows):
            if r == rc:
                grid[r][x] = "O" if x in (wx["hiHour"], wx["loHour"]) else "*"
            elif r > rc:
                grid[r][x] = ":" if night else "."
    nx = wx["nowHour"]
    for r in range(rows):
        if grid[r][nx] == " ":
            grid[r][nx] = "|"
    lines = ["".join(row) for row in grid]
    lines.append("-" * cols)
    axis = [" "] * cols
    for pos, lab in ((0, "12a"), (6, "6a"), (12, "12p"), (18, "6p")):
        for k, ch in enumerate(lab):
            if pos + k < cols:
                axis[pos + k] = ch
    lines.append("".join(axis))
    return "\n".join(lines)


# ---- HTML page (MacWeb-friendly) -------------------------------------------
def page_head(title):
    return (
        "<html><head><title>%s</title>"
        '<meta http-equiv="refresh" content="%d; URL=%s"></head>'
        % (title, REFRESH_SECONDS, REFRESH_URL)
    )


def build_html(wx):
    stats = [
        ("Feels like", "%d%s" % (wx["feels"], DEG)),
        ("UV index", str(wx["uv"])),
        ("Humidity", "%d%%" % wx["hum"]),
        ("Wind", "%d %s" % (wx["wind"], wx["wdir"])),
        ("Sunrise", wx["sun"]["rise"]),
        ("Sunset", wx["sun"]["set"]),
    ]
    stat_lines = "\n".join("%-12s%s" % (lab, val) for lab, val in stats)

    fc_lines = []
    for d in wx["days"]:
        fc_lines.append("%-6s%3d %s %3d" % (d["d"], d["lo"],
                                            ascii_range_bar(d, wx["wkMin"], wx["wkMax"]), d["hi"]))
    fc_block = "\n".join(fc_lines)

    left = (
        '<center>'
        '<font face="Chicago" size="7">%d%s</font><br>'
        '<font face="Chicago" size="4">%s</font>'
        '</center>'
        '<hr>'
        '<font face="Monaco" size="2"><pre>%s</pre></font>'
        % (wx["temp"], DEG, wx["cond"], stat_lines)
    )
    right = (
        '<font face="Chicago" size="3">FIVE-DAY OUTLOOK</font><hr>'
        '<font face="Monaco" size="2"><pre>%s</pre></font>'
        '<font face="Chicago" size="2">TODAY  %d%s%s%d%s</font>'
        '<font face="Monaco" size="1"><pre>%s</pre></font>'
        % (fc_block, wx["loTemp"], DEG, "/", wx["hiTemp"], DEG, ascii_today_chart(wx))
    )

    body = (
        '<body>'
        '<table width="100%%"><tr>'
        '<td><font face="Chicago" size="4">%s</font></td>'
        '<td align="right"><font face="Chicago" size="4">%s</font></td>'
        '</tr></table><hr>'
        '<table width="100%%" cellpadding="3"><tr>'
        '<td valign="top" width="40%%">%s</td>'
        '<td valign="top">%s</td>'
        '</tr></table>'
        '</body>'
        % (wx["loc"], wx["dateline"], left, right)
    )
    return page_head("Palo Alto Weather") + body + "</html>"


IMG_MIME = {
    "gif": "image/gif", "xbm": "image/x-xbitmap",
    "pbm": "image/x-portable-bitmap", "bmp": "image/bmp",
}


def img_test_html():
    """Index of ISOLATED single-format probes. Each format gets its own page so a
    helper-app handoff (e.g. GIF -> JPEGView) on one format can't block the others.
    Test XBM first — it's the only one likely to render inline on MacWeb."""
    links = "".join(
        '<font face="Chicago" size="3">'
        '<a href="http://wx.com/test-%s">Test %s</a></font><br>'
        '<font face="Geneva" size="2">%s</font><br><br>' % (ext, ext.upper(), note)
        for ext, note in (
            ("xbm", "X BitMap &mdash; 1-bit, the historical inline format. Best hope."),
            ("pbm", "Portable BitMap &mdash; 1-bit binary."),
            ("bmp", "Windows BMP &mdash; probably too new for MacWeb."),
            ("gif", "GIF &mdash; expected to try a helper app (JPEGView), NOT inline."),
        )
    )
    return (
        page_head("Image format test")
        + '<body><font face="Chicago" size="3">INLINE IMAGE TEST</font><hr>'
        '<font face="Geneva" size="2">Open each link below by itself. If you see the '
        'picture (a box with a diagonal hatch and the format name), MacWeb renders that '
        'format INLINE. If you get a broken icon or a &ldquo;helper application&rdquo; '
        'error, it does not.</font><br><br>' + links + '</body></html>'
    )


def one_img_test_html(ext):
    """A page containing exactly ONE image, in one format, plus the full weather image
    if that format is the 1-bit winner."""
    big = ""
    if ext in ("xbm", "pbm"):
        big = ('<hr><font face="Geneva" size="2">If the small box worked, here is the '
               'FULL weather display (512x342, slower to load):</font><br>'
               '<img src="http://wx.com/wx.%s" width="512" height="342" alt="weather">' % ext)
    return (
        page_head("Test %s" % ext.upper())
        + '<body><font face="Chicago" size="3">FORMAT: %s</font><hr>'
        '<font face="Geneva" size="2">Small probe (should show a hatched box reading '
        '&ldquo;%s&rdquo;):</font><br>'
        '<img src="http://wx.com/test.%s" width="128" height="44" alt="%s?">'
        '%s'
        '<hr><font face="Geneva" size="2"><a href="http://wx.com/img-test">'
        '&larr; back to all tests</a></font></body></html>'
        % (ext.upper(), ext.upper(), ext, ext, big)
    )


def image_page_html():
    """The LIVE display: a bare page whose only content is the full 512x342 weather
    image as inline XBM (confirmed to render inline in MacWeb on the SE). No chrome,
    no margins, so it fills the screen. Cache-busted so each KeyQuencer reload refetches."""
    bust = int(datetime.datetime.now().timestamp())
    return (
        page_head("Palo Alto Weather")
        + '<body bgcolor="#FFFFFF">'
        '<img src="http://wx.com/wx.%s?t=%d" width="512" height="342" '
        'alt="Palo Alto Weather" border="0">'
        '</body></html>' % (DISPLAY_FORMAT, bust)
    )


def build_hybrid(wx):
    """The recommended live display: fast HTML TEXT (the SE renders Chicago/Geneva
    itself) + small inline XBM images ONLY for the dithered graphics (weather icon,
    cool->warm 5-day bars, today temp graph). ~15-25KB total vs 110KB for a full image."""
    b = "?t=%d" % int(datetime.datetime.now().timestamp())   # cache-bust each reload

    # tight dividers: wrap rule img in size=1 so its line box adds minimal height.
    # Each width gets a DISTINCT url (&w=) rendered natively — MacWeb won't re-draw
    # the same cached image at a different size, so reusing one url drops the extras.
    def rule(w, loff=0):
        return ('<font size="1"><img src="http://wx.com/comp-rule.xbm%s&w=%d&l=%d" width="%d" '
                'height="2" border="0"></font>' % (b, w, loff, w))

    # Centering uses align="center" attributes (NOT <center> wrapping tables, which
    # can make MacWeb render the whole page blank). Tables carry align="center".
    left = (
        '<center>'
        '<img src="http://wx.com/comp-icon.xbm%s" width="48" height="48" border="0"><br>'
        '<font face="Chicago" size="7">%d%s</font><br>'
        '<font face="Chicago" size="4">%s</font><br>'
        '%s'   # divider (centered, nudged right a few px to sit over the metrics)
        '<font size="2"><br></font>'   # a smidge of space before the metrics
        '</center>'
        # 86%% + align=center insets the metrics so labels clear the screen edge and
        # values clear the vertical divider. (align attr, NOT <center> around a table.)
        '<table width="86%%" align="center" border="0" cellspacing="0" cellpadding="0">%s</table>'
        % (b, wx["temp"], DEG, wx["cond"], rule(114, loff=8), _stats_rows(wx))
    )
    # the entire 5-day block is ONE image (comp-forecast) — keeps the page well under
    # MacWeb's inline-image limit so the graph stops getting dropped.
    # forecast image and graph are adjacent (no divider between them, no label after)
    # so the graph fills the bottom without triggering the scrollbar.
    right = (
        '<b><font face="Chicago" size="3">FIVE-DAY OUTLOOK</font></b><br>%s'
        '<img src="http://wx.com/comp-forecast.xbm%s" width="300" height="120" border="0">'
        '<img src="http://wx.com/comp-graph.xbm%s" width="300" height="58" border="0">'
        % (rule(300, loff=16), b, b)
    )
    vrule = ('<font size="1"><img src="http://wx.com/comp-vrule.xbm%s" width="2" '
             'height="200" border="0"></font>' % b)
    # Two simple tables (this structure renders reliably in MacWeb): a header table,
    # then a 3-column content table (left / vline / right). Right cell align=center.
    # NOTE: no bgcolor on <body> — stock MacWeb 2.0 has a "blackout" bug where a page
    # background color intermittently paints the whole screen black. Default bg is fine.
    body = (
        '<body>'
        '<table width="%d" border="0" cellspacing="0" cellpadding="0"><tr>'
        '<td><b><font face="Chicago" size="3">%s</font></b></td>'
        '<td align="right"><b><font face="Chicago" size="3">%s</font></b></td>'
        '</tr></table>%s'
        '<table width="%d" border="0" cellspacing="0" cellpadding="0"><tr>'
        '<td valign="top" width="28%%">%s</td>'
        '<td valign="top" width="14" align="center">%s</td>'
        '<td valign="top" align="center">%s</td>'
        '</tr></table></body>'
        % (PAGE_W, wx["loc"], wx["dateline"], rule(PAGE_W), PAGE_W, left, vrule, right)
    )
    return page_head("Palo Alto Weather") + body + "</html>"


def _stats_rows(wx):
    """Full-width rows: label hard-left, value hard-right (spread across the column)."""
    stats = [
        ("Feels like", "%d%s" % (wx["feels"], DEG)),
        ("UV index", str(wx["uv"])),
        ("Humidity", "%d%%" % wx["hum"]),
        ("Wind", "%d %s" % (wx["wind"], wx["wdir"])),
        ("Sunrise", wx["sun"]["rise"]),
        ("Sunset", wx["sun"]["set"]),
    ]
    return "".join(
        '<tr><td align="left"><font face="Geneva" size="3">%s</font></td>'
        '<td align="right"><font face="Geneva" size="3">%s</font></td></tr>'
        % (lab, val) for lab, val in stats
    )


def render_html():
    return build_html(normalize(fetch_weather()))


# ---- request dispatch -------------------------------------------------------
def _html_response(body):
    # MacWeb interprets bytes as Latin-1 (ISO-8859-1) regardless of charset claims:
    # the Mac Roman degree byte 0xA1 showed up as "¡". So encode Latin-1, where the
    # degree sign is 0xB0 (DEG below) and renders correctly.
    return Response(body.encode("latin-1", "replace"), status=200,
                    content_type="text/html; charset=iso-8859-1",
                    headers={"Refresh": "%d; url=%s" % (REFRESH_SECONDS, REFRESH_URL)})


def _load_render():
    try:
        from . import render  # under macproxy: extensions.wx.render
    except (ImportError, ValueError):  # standalone (not under a package)
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import render
    return render


def handle_request(req):
    import re
    path = (req.path or "/").rstrip("/") or "/"
    _note_request()   # the SE just talked to us — record it for the Pi status UI
    try:
        # component XBMs for the hybrid page: current icon, whole 5-day forecast, graph
        mc = re.match(r"^/comp-(icon|graph|forecast|rule|vrule)\.xbm$", path)
        if mc:
            render = _load_render()
            which = mc.group(1)
            if which == "rule":
                try:
                    w = max(1, min(512, int(req.args.get("w", 504))))
                    loff = max(0, min(w, int(req.args.get("l", 0))))
                except (TypeError, ValueError):
                    w, loff = 504, 0
                img = render.comp_rule(w, loff=loff)   # native width so MacWeb won't rescale
            elif which == "vrule":
                img = render.comp_vrule()      # static vertical divider
            else:
                wx = normalize(fetch_weather())
                if which == "icon":
                    img = render.comp_icon(wx["icon"], 2)   # 24*2 = 48px native
                elif which == "graph":
                    img = render.comp_graph(wx)
                else:  # forecast
                    img = render.comp_forecast(wx)
            return Response(render.image_bytes(img, "xbm"), status=200, mimetype=IMG_MIME["xbm"])

        # /wx.<ext> = full weather image; /test.<ext> = small self-labeling probe
        m = re.match(r"^/(wx|weather|test)\.(gif|xbm|pbm|bmp)$", path)
        if m:
            kind, ext = m.groups()
            render = _load_render()
            img = (render.test_pattern(ext.upper()) if kind == "test"
                   else render.render_image(normalize(fetch_weather())))
            return Response(render.image_bytes(img, ext), status=200, mimetype=IMG_MIME[ext])
        mt = re.match(r"^/test-(gif|xbm|pbm|bmp)$", path)
        if mt:
            return _html_response(one_img_test_html(mt.group(1)))
        if path in ("/img-test", "/gif-test", "/image-test"):
            return _html_response(img_test_html())
        if path in ("/pixel", "/img", "/image"):   # the full-screen pixel display (heavy)
            return _html_response(image_page_html())
        if path in ("/text", "/ascii"):            # pure ASCII, no images (fastest)
            return _html_response(render_html())
        # default = hybrid: fast HTML text + small XBM graphics
        return _html_response(build_hybrid(normalize(fetch_weather())))
    except Exception as e:  # never leave the SE with a blank screen
        return _html_response(
            page_head("Weather Error")
            + "<body><pre>\n  Weather unavailable.\n  %s\n</pre></body></html>" % str(e)[:200]
        )
