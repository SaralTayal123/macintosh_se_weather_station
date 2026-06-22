# Production notes — C2 "Almanac" went live (server-side render)

This captures the productionization of the **C2** design and the **key constraint we hit**.

## TL;DR
- **The live SE page is HTML** (MacWeb-friendly), served at `http://wx.com/`. It reproduces
  the C2 layout using the SE's own **Chicago / Geneva / Monaco** fonts, ASCII cool→warm range
  bars, and an ASCII today-temperature chart. This is what your SE actually shows.
- **A pixel-perfect 1-bit GIF** of the same design is rendered by `wx/render.py` and served at
  `http://wx.com/wx.gif`. It is **not** the live SE display — see why below.

## Why the GIF can't be the live SE display (researched 2026-06-19)
- **MacWeb 2.0 (and the enhanced 2.0c+) cannot show GIFs inline** — only via an external
  helper app (GIFWatcher) that opens images in a *separate* window. No good for an unattended,
  auto-refreshing page.
- On the SE's **Motorola 68000**, no graphical browser does inline images: Netscape 2/3 and
  NCSA Mosaic all need a **68020+** (and Netscape crashes on the 68000).
- So the full-screen-GIF idea is viable only on an **emulator** (Mini vMac/Basilisk II), a
  **68020+ Mac** (e.g. an SE/30 running Netscape/Mosaic), or a different display path.

## What's where
- `wx/wx.py` — the extension. Dispatches on request path:
  - `/` → live HTML page (C2 layout). Mac Roman encoded (`charset=macintosh`) so `°` renders.
  - `/wx.gif` → the 512×342 1-bit GIF (Pillow). Returns a Flask `Response`, so macproxy passes
    it through **untouched** (no re-dithering).
  - `/gif-test` → a tiny page that tries to inline `wx.gif`, so you can confirm on the SE exactly
    what MacWeb does with it (expected: broken-image icon or a helper-app handoff).
- `wx/render.py` — the 1-bit renderer (Bayer dither, icons, range bars, day/night temp graph,
  fonts). `python wx/render.py` writes `preview/wx_c2.gif`. This is the project's "dithering module".
- `wx/fonts/` — bundled Chicago.ttf (free recreation) + Geneva/Monaco/NewYork (copied from macOS),
  used by the GIF renderer.
- `normalize()` in wx.py maps Open-Meteo JSON → one data dict used by **both** the HTML and GIF
  renderers (single source of truth).

## ⭐ FIRST when you're back: the inline-image test
The docs conflict on whether MacWeb inlines ANY image format, so test it empirically:
- On the SE, load **`http://wx.com/img-test`**. It shows the same picture as **XBM, GIF,
  PBM, BMP** (each box is self-labeled). Whichever boxes actually render = the format MacWeb
  can inline. **XBM is the prime suspect** (1-bit, the historical inline format).
- If XBM (or any) renders → the **full pixel-perfect C2 GIF design can go on the SE** after all,
  served as that format (`/wx.xbm` already serves the full 512×342 weather image; ~110KB so a
  bit slow over DaynaPORT, but it's the real thing). We'd then switch the live page to embed it.
- If none render inline → stick with the HTML page (below).
- Image endpoints: `/wx.{gif,xbm,pbm,bmp}` (full weather), `/test.{gif,xbm,pbm,bmp}` (small probe).

## When you're back — quick checks (minimal tweaks expected)
1. macproxy is running (I left a `--debug` instance on :5001; restart with
   `./start_macproxy.sh` if needed). The `wx` symlink + `ENABLED_EXTENSIONS` are already set.
2. On the SE, load **`wx.com`** → you should see the new HTML C2 layout (big Chicago temp,
   sunrise/sunset, 5-day ASCII bars, ASCII today chart). The KeyQuencer reload loop is unchanged.
3. Likely tweak spots once you see it on the real screen:
   - Font sizes (`<font size>` 1–7) / column widths in `build_html()` — MacWeb's metrics differ.
   - The ASCII today-chart density/width in `ascii_today_chart()`.
   - If `°` looks wrong, drop `DEG` to `"F"` or empty.
4. To see the *pretty* version: open `preview/wx_c2.gif` / `preview/wx_live.gif` on this Mac, or
   load `wx.com/wx.gif` in an emulator/68020+ browser.

## Open question for you
The dithered C2 you loved can't render on the 68000 SE's browser. Options to discuss:
- Keep the **HTML** version on the SE (works now), treat the GIF as a bonus/emulator view.
- Pursue the **GIF** for real via an emulator or a 68020+ machine.
- A hybrid we haven't tried (e.g., KeyQuencer driving GIFWatcher fullscreen — hacky).
