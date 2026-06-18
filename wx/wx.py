"""
SE Weather - a Macintosh SE optimized weather display, served as a macproxy extension.

Browse to http://wx.com/ from the vintage machine.

Note: the domain intentionally uses a real TLD (.com). MacWeb 2.0 refuses to
treat made-up TLDs (e.g. .box) as valid URLs and mangles them, so we shadow a
real-TLD domain that the SE will never need to visit for real.

This module is intentionally self-contained (its own config below) so it can later be
lifted out into a standalone repo with minimal changes.
"""

import random
import datetime
import requests
from flask import Response

DOMAIN = "wx.com"

# --- Configuration (will move to config.example.py when extracted to its own repo) ---
LATITUDE = 37.4419
LONGITUDE = -122.1430
LOCATION_NAME = "PALO ALTO, CA"
TIMEZONE = "America/Los_Angeles"

REFRESH_SECONDS = 60          # meta-refresh interval; 60 for bring-up, raise later
REFRESH_URL = "http://wx.com/"  # explicit reload target (some old browsers need it)
FORECAST_DAYS = 5

JITTER_ENABLED = True         # anti-burn-in: nudge layout a few chars each refresh
SLEEP_ENABLED = False         # keep OFF during bring-up so the screen never blacks out
# Sleep windows: list of (start_hour, end_hour, weekdays_only)
SLEEP_WINDOWS = [
    (23, 6, False),   # 11pm - 6am, every day
    (10, 16, True),   # 10am - 4pm, weekdays only
]

API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather code -> short label that fits the ASCII layout
WMO = {
    0: "Clear", 1: "PtCloud", 2: "PtCloud", 3: "Cloudy",
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


def compass(deg):
    return COMPASS[int((deg % 360) / 45.0 + 0.5) % 8]


def fetch_weather():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,wind_speed_10m,wind_direction_10m,surface_pressure",
        "hourly": "visibility",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,sunrise,sunset",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": TIMEZONE,
        "forecast_days": FORECAST_DAYS,
    }
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def current_visibility_miles(data):
    """Visibility is an hourly var; grab the value for the current hour."""
    try:
        cur_hour = data["current"]["time"][:13]  # YYYY-MM-DDTHH
        times = data["hourly"]["time"]
        vis = data["hourly"]["visibility"]
        for i, t in enumerate(times):
            if t[:13] == cur_hour:
                return vis[i] / 1609.34
        return vis[0] / 1609.34
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        return None


def build_range_bar(low, high, week_min, week_max, current=None, width=14):
    span = week_max - week_min

    def col(t):
        if span <= 0:
            return 0
        c = int(round((t - week_min) / span * (width - 1)))
        return max(0, min(width - 1, c))

    lo, hi = col(low), col(high)
    cells = ["-"] * width
    for i in range(lo, hi + 1):
        cells[i] = "="
    if current is not None:
        cc = max(lo, min(hi, col(current)))
        cells[cc] = "O"
    return "".join(cells)


def render_weather_page(data):
    cur = data["current"]
    daily = data["daily"]

    temp = round(cur["temperature_2m"])
    feels = round(cur["apparent_temperature"])
    hum = round(cur["relative_humidity_2m"])
    cond = wmo_label(cur["weather_code"])
    wind = round(cur["wind_speed_10m"])
    wdir = compass(cur["wind_direction_10m"])
    pres_inhg = cur["surface_pressure"] * 0.02953
    vis_mi = current_visibility_miles(data)

    lows = [round(t) for t in daily["temperature_2m_min"]]
    highs = [round(t) for t in daily["temperature_2m_max"]]
    week_min, week_max = min(lows), max(highs)

    # forecast rows
    rows = []
    for i in range(len(daily["time"])):
        if i == 0:
            day = "Today"
        else:
            day = datetime.datetime.strptime(daily["time"][i], "%Y-%m-%d").strftime("%a")
        cond_i = wmo_label(daily["weather_code"][i])
        pop = daily["precipitation_probability_max"][i]
        pop_s = ("%d%%" % pop) if pop else ""
        cur_marker = temp if i == 0 else None
        bar = build_range_bar(lows[i], highs[i], week_min, week_max, cur_marker)
        rows.append(
            "  %-6s%-8s%4s  %3d %s %3d" % (day, cond_i, pop_s, lows[i], bar, highs[i])
        )

    now = datetime.datetime.now().strftime("%a %b %-d  %-I:%M %p")
    vis_s = ("%.0fmi" % vis_mi) if vis_mi is not None else "n/a"

    lines = []
    lines.append("        %s" % LOCATION_NAME)
    lines.append("        %s" % now)
    lines.append("")
    lines.append("   %dF  %s   feels %dF" % (temp, cond, feels))
    lines.append("   Hum %d%%   Wind %dmph %s" % (hum, wind, wdir))
    lines.append("   Vis %s   Pres %.2fin" % (vis_s, pres_inhg))
    lines.append("")
    lines.append("   5-DAY FORECAST      cooler   warmer")
    lines.extend(rows)
    body = "\n".join(lines)

    if JITTER_ENABLED:
        # Shift the whole block by a consistent amount so columns stay aligned.
        pad = " " * random.randint(0, 3)
        body = "\n" * random.randint(0, 2) + pad + body.replace("\n", "\n" + pad)

    return page_html("Palo Alto Weather", "<pre>\n%s\n</pre>" % body)


def render_sleep_page():
    now = datetime.datetime.now().strftime("%-I:%M %p")
    jab = " " * random.randint(0, 30) + "\n" * random.randint(0, 8)
    inner = (
        '<body bgcolor="#000000" text="#FFFFFF">'
        "<pre>%s   %s</pre></body>" % (jab, now)
    )
    return page_html("zzz", inner, full_body=True)


def page_html(title, inner, full_body=False):
    head = (
        "<html><head><title>%s</title>"
        '<meta http-equiv="refresh" content="%d; URL=%s"></head>'
        % (title, REFRESH_SECONDS, REFRESH_URL)
    )
    if full_body:
        return head + inner + "</html>"
    return head + "<body>" + inner + "</body></html>"


def is_sleep_time():
    if not SLEEP_ENABLED:
        return False
    now = datetime.datetime.now()
    hour = now.hour
    weekday = now.weekday() < 5  # Mon-Fri
    for start, end, wd_only in SLEEP_WINDOWS:
        if wd_only and not weekday:
            continue
        if start <= end:
            in_window = start <= hour < end
        else:  # wraps midnight, e.g. 23 -> 6
            in_window = hour >= start or hour < end
        if in_window:
            return True
    return False


def handle_request(req):
    try:
        if is_sleep_time():
            html = render_sleep_page()
        else:
            html = render_weather_page(fetch_weather())
    except Exception as e:
        html = page_html(
            "Weather Error",
            "<pre>\n  Weather unavailable.\n  %s\n</pre>" % str(e)[:200],
        )
    return Response(
        html,
        status=200,
        mimetype="text/html",
        headers={"Refresh": "%d; url=%s" % (REFRESH_SECONDS, REFRESH_URL)},
    )
