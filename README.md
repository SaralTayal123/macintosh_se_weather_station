# se-weather

A weather display for a **Macintosh SE** (System 6/7), rendered as a
[macproxy](https://github.com/rdmark/macproxy_classic) extension and optimized for a
512×342, 1-bit screen. The vintage machine browses to `http://wx.com/` and gets a
glanceable current-conditions + 5-day forecast page built to be readable on a
35-year-old browser.

![screenshot placeholder](docs/screenshots/.gitkeep)

## How it works

```
Open-Meteo API ──> wx extension (this repo) ──> SE-optimized 1-bit HTML
                   running inside macproxy            │
                                                      ▼  HTTP over WiFi
                                         Mac SE / Netscape 2.02
```

- **Data:** [Open-Meteo](https://open-meteo.com) — free, no API key, lat/long based.
- **Render:** a single non-scrolling page: current temp/conditions/wind/visibility/
  pressure, plus a 5-day forecast with ASCII temperature-range bars drawn on a shared
  min→max scale (so days are visually comparable, à la Apple Weather). A current-temp
  marker (`O`) sits on Today's bar.
- **Anti-burn-in:** the layout is nudged a few characters each refresh, and an optional
  overnight/daytime "sleep" page blanks the screen on a schedule.

## Install

1. Get [macproxy_classic](https://github.com/rdmark/macproxy_classic) running on a
   machine on your LAN.
2. Drop this extension into macproxy's `extensions/` folder (symlink recommended so
   edits stay live):
   ```
   ln -s /path/to/se-weather/wx  /path/to/macproxy_classic/extensions/wx
   ```
3. Enable it in macproxy's `config.py`:
   ```python
   ENABLED_EXTENSIONS = [ ..., "wx" ]
   ```
4. Set your location and preferences at the top of `wx/wx.py` (`LATITUDE`,
   `LONGITUDE`, `LOCATION_NAME`, units, `REFRESH_SECONDS`, sleep windows).
5. On the vintage machine, point the browser's HTTP proxy at the macproxy host
   (e.g. `192.168.0.159` port `5001`) and visit **`http://wx.com/`**.

## Hard-won compatibility notes (Mac SE + MacWeb/Netscape)

- **Use a real TLD for the domain.** MacWeb 2.0 mangles made-up TLDs (e.g. `.box`) into
  a broken doubled URL. We shadow `wx.com` (a real TLD the SE never needs to visit for
  real) so the browser accepts it as a valid address.
- **MacWeb 2.0 does not auto-refresh.** It ignores both `<meta http-equiv="refresh">`
  and the HTTP `Refresh:` header. For an unattended, self-updating display use
  **Netscape 2.02**, which honors meta-refresh. (Both are fine for manual viewing.)
- **No CSS in MacWeb.** Styling is faked with `<font face>` on headings; layout uses
  `<pre>`, tables, and `<center>`. Stick to ASCII (Mac Roman charset — no Unicode block
  glyphs).
- MacWeb's proxy setting lives in an unusual spot: Edit → Preferences → **Firewall** →
  Proxies → HTTP row (Host + Port as separate fields).

## Roadmap

- Generated 1-bit GIF range bars with a cool→warm dither gradient (replacing the ASCII
  bars), plus tiny dithered weather icons — via a custom dithering module.

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for any noncommercial use.
Built to run with macproxy_classic (GPLv3); this extension is a separate work.
Weather data © Open-Meteo (CC BY 4.0).
