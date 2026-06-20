# se-weather

A self-updating **weather display for a Macintosh SE** (System 7.1), built as a
[macproxy](https://github.com/rdmark/macproxy_classic) extension and optimized for the
SE's 512×342, 1-bit screen. The vintage Mac browses to `http://wx.com/` and shows a
glanceable current-conditions + 5-day forecast page, and it **reloads itself every 60
seconds with no keyboard or mouse attached** — boot it and it just runs.

![A Macintosh SE running se-weather (KeyQuencer reload macro shown)](docs/screenshots/keyquencer-macro.jpg)

```
Open-Meteo API ──> wx extension (this repo, runs inside macproxy on a modern Mac)
                       │  renders SE-optimized 1-bit HTML
                       ▼  HTTP over Wi-Fi (DaynaPORT)
                  Macintosh SE / MacWeb 2.0  ──reloads every 60s via KeyQuencer
```

This README is the full, reproducible build. It has three parts:
1. **[Server side](#part-1--server-side-the-prox--weather-extension)** — the proxy + weather extension (≈15 min).
2. **[Vintage Mac networking & browser](#part-2--vintage-mac-networking--browser)** — get the SE online and pointed at the proxy.
3. **[Hands-off auto-reload](#part-3--hands-off-auto-reload-keyquencer)** — make it a true unattended display.

> Most of Parts 2–3 are hard-won, undocumented vintage-Mac details. Read the
> **Gotchas** call-outs; they're the things that cost the most time to discover.

---

## Hardware / software used

- **Macintosh SE** — Motorola **68000** @ 8 MHz, **4 MB RAM**, 512×342 1-bit screen, System **7.1**.
- **ZuluSCSI Pico W** (must be the **W** / RP2040W variant) emulating a **DaynaPORT SCSI/Link** Wi-Fi Ethernet adapter. *(BlueSCSI v2 with a Pico W works the same way.)*
- A **2.4 GHz Wi-Fi** network (the Pico W has no 5 GHz radio).
- A **modern Mac/Linux machine** on the same LAN to run the proxy (kept on whenever you want the display live).
- Software the SE needs (all free; sources in Part 2): **MacTCP**, the **DaynaPORT 7.5.3** driver, **MacWeb 2.0**, **KeyQuencer**.

---

## Part 1 — Server side: the proxy + weather extension

1. Install and run [macproxy_classic](https://github.com/rdmark/macproxy_classic) on the LAN machine (it's a Flask app; `./start_macproxy.sh` sets up a venv and runs it on port **5001**).

2. Drop this extension into macproxy's `extensions/` folder. A **symlink** keeps it editable from this repo:
   ```sh
   ln -s /path/to/se-weather/wx  /path/to/macproxy_classic/extensions/wx
   ```

3. Enable it in macproxy's `config.py`:
   ```python
   ENABLED_EXTENSIONS = [ ..., "wx" ]
   ```

4. Set your location and preferences at the top of [`wx/wx.py`](wx/wx.py):
   ```python
   LATITUDE      = 37.4419
   LONGITUDE     = -122.1430
   LOCATION_NAME = "PALO ALTO, CA"
   TIMEZONE      = "America/Los_Angeles"
   REFRESH_SECONDS = 60        # also bump the KeyQuencer Wait to match (Part 3)
   SLEEP_ENABLED   = False     # optional overnight/daytime blank-screen windows
   ```
   Data comes from [Open-Meteo](https://open-meteo.com) — free, no API key, includes
   temperature, humidity, wind, **visibility**, pressure, and a 5-day forecast.

5. Restart macproxy and sanity-check from the LAN machine:
   ```sh
   curl -x http://localhost:5001 http://wx.com/
   ```
   You should get the weather HTML back.

> **Gotcha — the domain must use a real TLD.** The extension's `DOMAIN` is **`wx.com`**,
> not something like `wx.box`. MacWeb 2.0 refuses to treat made-up TLDs as valid URLs and
> mangles them into a broken `http://<proxy-ip>/http://wx.box/` request. `wx.com` is a real
> TLD the SE never needs to visit for real, so the extension safely shadows it.

The page is a Flask `Response` returned straight from the extension, so macproxy passes it
through **without** its usual tag-stripping — the hand-built 1-bit layout stays intact.

---

## Part 2 — Vintage Mac networking & browser

### 2a. ZuluSCSI DaynaPORT Wi-Fi

On the SD card root, alongside your disk images:

- Create an **empty file named `NE4.img`** — this assigns SCSI ID 4 as the DaynaPORT network device.
- In `zuluscsi.ini`, put your Wi-Fi credentials in the `[SCSI]` section:
  ```ini
  [SCSI]
  WiFiSSID = "YourNetwork"
  WiFiPassword = "YourPassword"
  ```
- Boot the SE; check `zululog.txt` on the card afterward — it should say
  `Successfully connected to Wi-Fi`.

### 2b. DaynaPORT driver

Install the **DaynaPORT 7.5.3** driver on the SE.

> **Gotcha — use Custom install.** Run the Dayna Installer and choose **Customize →
> "DaynaPORT SCSI/Link"** (install *only* that). The default "Easy Install" picks the wrong
> components and MacTCP will then show only **LocalTalk**. After the Custom install + restart,
> MacTCP shows an **"Ethernet Built-in"** option — that's the DaynaPORT link.

### 2c. MacTCP (System 7.1 has no DHCP — set a static IP)

Apple menu → Control Panels → **MacTCP**:
- Select **Ethernet Built-in**, click **More…**
- **Obtain Address: Manually**
- **IP Address:** e.g. `192.168.0.234`
- **Router/Gateway:** your router, e.g. `192.168.0.1`
- **Subnet Mask:** `255.255.255.0`
- **Domain Name Server:** domain `.`, IP `1.1.1.1`, set as Default
- Close MacTCP (it saves) and **restart**.

Verify with **MacTCP Ping** to your proxy machine's IP.

### 2d. MacWeb 2.0 + proxy setting

Install MacWeb 2.0, then point it at the proxy.

> **Gotcha — MacWeb's proxy lives under "Firewall."** It's at
> **Edit → Preferences → (category popup) → Firewall → Proxies**. In the **HTTP** row put the
> **Host** and **Port** in *separate* fields (`192.168.0.159` and `5001`) — no `http://`, no
> `:5001` mashed into the host. Quit and relaunch MacWeb so the prefs persist.

Then in the address bar just type **`wx.com`** — *not* the proxy IP. The proxy setting routes
it automatically; typing the proxy IP yourself produces a doubled, broken URL.

> **Gotcha — give the proxy machine a static/reserved IP.** MacWeb hard-codes the proxy
> address; if DHCP moves it, the SE silently stops loading. A router DHCP reservation avoids this.

At this point `wx.com` loads on the SE — but **only when you reload it manually.**

---

## Part 3 — Hands-off auto-reload (KeyQuencer)

> **Why this is needed:** MacWeb 2.0 **ignores `<meta http-equiv="refresh">` *and* the HTTP
> `Refresh:` header** — it cannot auto-reload. Netscape supports meta-refresh but **requires a
> 68020** and crashes on the SE's 68000. MacLynx runs but is unusably slow. So we automate the
> reload externally with **[KeyQuencer](https://macintoshgarden.org/apps/keyquencer)**, a macro
> utility that *does* run on a 68000.

### 3a. Install KeyQuencer

Expand the KeyQuencer archive on the SE and drag **`KeyQuencer Engine`**, **`KeyQuencer
Panel`**, and the **`KeyQuencer Extensions`** folder onto the closed System Folder (let System 7
file them). **Restart.** You'll see the KeyQuencer icon at startup and a KeyQuencer control panel.

### 3b. The macro

This is the exact macro running on the SE, pasted into the Batcher's **Handle Item** (Part 3c)
and named `weather`:

```
Wait seconds 30
SwitchApp "MacWeb"
Key enter
Menu "Navigate" "Load Url..."
Wait seconds 1
Type "wx.com
Wait seconds 1
Key enter
Repeat 99999 "Menu \qView\q \qReload\q\rWait 60 seconds"
```

Line by line:
- **`Wait seconds 30`** — let MacWeb finish launching (slow on a 68000, slower if it's loading its dead default home page).
- **`SwitchApp "MacWeb"`** — bring MacWeb to the front.
- **`Key enter`** — dismiss any modal error dialog MacWeb popped while launching (e.g. failing to reach its dead `galaxy.einet.net` home page). **This is the fix for the "menu is restricted" error**: a modal dialog blocks the menu bar, so we clear it before touching menus.
- **`Menu "Navigate" "Load Url..."`** — open MacWeb's Load-URL dialog.
- **`Wait seconds 1` / `Type "wx.com` / `Wait seconds 1` / `Key enter`** — type the URL and submit it. (`wx.com` with no `http://` is fine; the 1-second waits give the dialog time to appear and accept input.)
- **`Repeat 99999 "..."`** — the forever loop: every 60s, `Menu "View" "Reload"` reloads the page. No `SwitchApp` inside the loop is needed since MacWeb stays frontmost.

KeyQuencer macro-language notes (these are **not** documented online — extracted from the command modules' resource forks):
- **`Repeat #iterations "literal macro"`** — inside the literal, use **`\r`** for a return (command separator), **`\q`** for a `"`, **`\s`** for a `'`. **No real line breaks** inside the literal.
- **`Wait #n seconds`** — a number with a unit (`ticks`/`seconds`/`minutes`/`hours`); both `Wait seconds 30` and `Wait 60 seconds` parse.
- **`Type "text"`** types text; **`Key enter`** presses Enter — used here both to dismiss dialogs and to submit the Load-URL field.
- **`Menu "Menu" "Item"`** — exact item text works (`"Load Url..."` with three dots); an optional `partial` flag matches without the `…`. Add `enforce quiet continue` to keep the macro from halting if a menu is briefly dimmed.
- **`SwitchApp "App"`** brings an already-open app to the front. MacWeb's Reload lives under its **View** menu.
- We navigate via **Load URL** (not the home page) because this MacWeb's home-page field is read-only.

You can test the macro by assigning it a trigger key in the KeyQuencer control panel and pressing it.

### 3c. Run the macro automatically at boot (the Batcher)

The auto-run mechanism is the **`KeyQuencer Batcher`** (the Launcher only *shows* a macro list,
it can't auto-run). The Batcher's **"Start Batch List When Launched"** runs a macro on launch.

1. Open **`KeyQuencer Batcher`**.
2. **Macros menu → "Handle Item…"** → paste the macro above into **Macro Text**, name it `Weather`.
   *(Handle Item runs the macro once per item in the batch list; our macro then loops forever and
   never returns, which is exactly what we want.)*
3. Give the batch one valid item: **Batch → Show Batch List**, click inside the list window, then
   **Edit → Insert Pathname…** and pick any real file (e.g. `System Folder:Finder`).
   > **Gotcha — the item must be a real file added via the picker.** A hand-typed path fails
   > validation silently and the batch then does nothing. Use **Insert Pathname…** (a file dialog)
   > or drag a file onto the window.
4. **Batch menu → "Start Batch List When Launched"** (check it on).
5. Test: quit the Batcher and relaunch it — after ~15 s, MacWeb should load `wx.com` and start reloading.

### 3d. Make it fully unattended at boot

Put aliases of both apps in the **Startup Items** folder so a cold boot needs no input:

1. Select **MacWeb** → **File → Make Alias** → drag the alias into **System Folder → Startup Items**.
2. Select **KeyQuencer Batcher** → **File → Make Alias** → drag that alias into **Startup Items** too.
3. **Restart.**

Boot sequence with nothing attached:
**power on → MacWeb auto-launches → Batcher auto-launches → its macro loads `wx.com` → reloads every 60 s, forever.**

---

## Configuration reference (`wx/wx.py`)

| Setting | Meaning |
|---|---|
| `LATITUDE` / `LONGITUDE` / `LOCATION_NAME` / `TIMEZONE` | Your location (Open-Meteo). |
| `REFRESH_SECONDS` | Page meta-refresh hint (cosmetic for MacWeb; real cadence is the KeyQuencer `Wait`). |
| `JITTER_ENABLED` | Nudge the layout a few chars each reload to reduce CRT burn-in. |
| `SLEEP_ENABLED` + `SLEEP_WINDOWS` | Serve a near-black "sleep" page during set hours (off by default). |

Units are Fahrenheit / mph / inHg in `fetch_weather()`; change the `*_unit` params there for metric.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| MacTCP shows only **LocalTalk** | DaynaPORT installed via Easy Install. Re-run installer → **Custom → DaynaPORT SCSI/Link**. |
| `wx.box`/made-up domain gives a doubled URL + 502 | MacWeb mangles non-real TLDs. Use a real TLD (`wx.com`). |
| MacWeb error **1003** / "can't access" | Connection failed — proxy `Port` field empty (defaults to 80), proxy IP changed, or weak Wi-Fi. Check the **Port 5001** field and the proxy machine's IP. |
| Page loads but **never auto-refreshes** | Expected for MacWeb — that's what Part 3 (KeyQuencer) is for. |
| KeyQuencer `Repeat: too many parameters` / `unknown keyword` | Use `\q` (not doubled quotes) for quotes and `\r` (not real newlines) inside a `Repeat` literal. `Wait` is *number then unit*. |
| Batcher "does nothing" | The batch list item is invalid. Add a real file via **Edit → Insert Pathname…**, not a typed path. |
| KeyQuencer **"menu is restricted"** | A modal dialog (often MacWeb's failed home-page load) is blocking the menu bar. Add **`Key enter`** before the menu commands to dismiss it, and/or increase the initial `Wait`. |
| Reloads are slow / time out | Weak DaynaPORT Wi-Fi link (high jitter). Move the SE/Pico W closer to the router; pick 2.4 GHz channel 1/6/11. |

---

## Roadmap

- Generated 1-bit GIF temperature-range bars with a cool→warm dither gradient (replacing the
  ASCII bars), plus tiny dithered weather icons — via a custom dithering module.

## License & credits

[PolyForm Noncommercial 1.0.0](LICENSE) — free for any noncommercial use.
Runs with [macproxy_classic](https://github.com/rdmark/macproxy_classic) (GPLv3; this extension
is a separate work). Weather data © [Open-Meteo](https://open-meteo.com) (CC BY 4.0).
Auto-reload uses [KeyQuencer](https://macintoshgarden.org/apps/keyquencer) by Alessandro Levi Montalcini.
