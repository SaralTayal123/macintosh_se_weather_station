#!/usr/bin/env python3
"""
status_app.py — a small touchscreen status panel for the Raspberry Pi that hosts the
se-weather macproxy. Designed for a ~4.3" display; fills whatever resolution it finds.

Shows:
  * how long since the Macintosh SE last talked to the proxy (the "ping")
  * proxy service state, internet connectivity, the Pi's IP:port, request count, temp
  * touch buttons: Restart Proxy · Refresh Weather · Test Network

State comes from the status file the wx extension writes (WX_STATUS_FILE). This app never
imports the proxy — it just reads that file and shells out to systemctl for actions.

Run:  python3 status_app.py         (uses pygame; on Pi OS Desktop it opens fullscreen)
Env:  WX_STATUS_FILE, WX_REFRESH_FLAG, WX_SERVICE (default macproxy-wx), WX_PORT (5001)
"""

import json
import os
import socket
import subprocess
import threading
import time

import pygame

STATUS_FILE = os.environ.get("WX_STATUS_FILE", "/tmp/wx-status.json")
REFRESH_FLAG = os.environ.get("WX_REFRESH_FLAG", "/tmp/wx-refresh.flag")
SERVICE = os.environ.get("WX_SERVICE", "macproxy-wx")
PORT = os.environ.get("WX_PORT", "5001")

# thresholds (seconds) for the "last seen" color (reload is ~3 min)
SEEN_OK, SEEN_WARN = 300, 900

# 1-bit-ish palette to echo the SE aesthetic
BLACK, WHITE, GRAY = (20, 20, 20), (240, 240, 240), (120, 120, 120)
GOOD, WARN, BAD = (90, 200, 90), (230, 180, 60), (220, 80, 80)


# ---- data sources -----------------------------------------------------------
def read_status():
    try:
        with open(STATUS_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def service_active():
    try:
        r = subprocess.run(["systemctl", "is-active", SERVICE],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "active"
    except Exception:
        return None


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 80))  # no packets sent; just picks the egress iface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "?"


def internet_up(timeout=2.5):
    """True if we can open a TCP connection to a public DNS resolver."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("1.1.1.1", 53))
        return True
    except OSError:
        return False


# ---- actions ----------------------------------------------------------------
def act_restart():
    subprocess.Popen(["sudo", "systemctl", "restart", SERVICE])
    return "restarting proxy…"


def act_refresh():
    try:
        with open(REFRESH_FLAG, "w") as fh:
            fh.write(str(time.time()))
        os.utime(REFRESH_FLAG, None)
        return "weather refresh queued"
    except OSError:
        return "refresh failed"


def act_testnet():
    return "internet OK" if internet_up() else "no internet"


# ---- little UI helpers ------------------------------------------------------
def fmt_mins(delta):
    """Last-seen as whole minutes, clipped at 9999. 'never' if no data yet."""
    if delta < 0:
        return "never"
    m = int(delta // 60)
    return "9999+m" if m > 9999 else "%dm" % m


class Button:
    def __init__(self, label, action):
        self.label, self.action = label, action
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.flash = 0.0

    def draw(self, surf, font):
        down = time.time() - self.flash < 0.15
        pygame.draw.rect(surf, WHITE if down else BLACK, self.rect)
        pygame.draw.rect(surf, BLACK, self.rect, 2)
        t = font.render(self.label, True, BLACK if down else WHITE)
        surf.blit(t, t.get_rect(center=self.rect.center))


def main():
    print("se-weather status panel starting (pygame %s)" % pygame.version.ver, flush=True)
    try:
        pygame.init()
        info = pygame.display.Info()
        size = (info.current_w, info.current_h) if info.current_w > 0 else (800, 480)
        screen = pygame.display.set_mode(size, pygame.FULLSCREEN)
    except pygame.error as e:
        print("ERROR: could not open the display: %s\n"
              "  This app needs a graphical session. Run it from the Pi's desktop\n"
              "  (a terminal ON the touchscreen), not over plain SSH. Under Wayland try\n"
              "  SDL_VIDEODRIVER=wayland; under X11, DISPLAY=:0." % e, flush=True)
        raise SystemExit(1)
    pygame.mouse.set_visible(False)
    W, H = screen.get_size()
    print("display opened: %dx%d" % (W, H), flush=True)
    pygame.display.set_caption("SE Weather Proxy")

    def font(px, bold=True):
        return pygame.font.SysFont("dejavusansmono,menlo,monospace", max(8, px), bold=bold)

    TITLE_H = int(H * 0.13)
    f_title = font(int(H * 0.065))
    f_lbl = font(int(H * 0.05), bold=False)
    f_stat = font(int(H * 0.052))
    f_btn = font(int(H * 0.05))
    f_x = font(int(H * 0.065))

    buttons = [Button("Restart Proxy", act_restart),
               Button("Refresh Weather", act_refresh),
               Button("Test Network", act_testnet)]
    bh = int(H * 0.15)
    bw = (W - 40 - 20 * (len(buttons) - 1)) // len(buttons)
    for i, b in enumerate(buttons):
        b.rect = pygame.Rect(20 + i * (bw + 20), H - bh - 16, bw, bh)
    quit_rect = pygame.Rect(W - TITLE_H, 0, TITLE_H, TITLE_H)   # the X in the corner

    def right_row(yy, text, dot=None, color=BLACK):
        t = f_stat.render(text, True, color)
        tx = W - 24 - t.get_width()
        screen.blit(t, (tx, yy))
        if dot is not None:
            c = GOOD if dot is True else (BAD if dot is False else GRAY)
            pygame.draw.circle(screen, c, (tx - 22, yy + t.get_height() // 2), int(H * 0.02))

    toast, toast_t = "", 0.0
    net_ok, net_checked = None, 0.0
    svc_ok, svc_checked = None, 0.0
    clock = pygame.time.Clock()
    running = True
    while running:
        now = time.time()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                running = False
            elif e.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                pos = (int(e.x * W), int(e.y * H)) if e.type == pygame.FINGERDOWN else e.pos
                if quit_rect.collidepoint(pos):
                    running = False
                for b in buttons:
                    if b.rect.collidepoint(pos):
                        b.flash = now
                        toast, toast_t = b.action(), now
                        if b.action is act_testnet:
                            net_ok, net_checked = internet_up(), now

        # periodic background checks (cheap, throttled)
        if now - net_checked > 20:
            net_checked = now
            threading.Thread(target=lambda: globals().__setitem__("_net", internet_up()),
                             daemon=True).start()
        if now - svc_checked > 5:
            svc_ok, svc_checked = service_active(), now
        net_ok = globals().get("_net", net_ok)

        st = read_status()
        last_seen = st.get("last_seen", 0)
        ago = (now - last_seen) if last_seen else -1
        seen_color = BAD if ago < 0 or ago > SEEN_WARN else (WARN if ago > SEEN_OK else GOOD)

        # ---- paint ----
        screen.fill(WHITE)
        pygame.draw.rect(screen, BLACK, (0, 0, W, TITLE_H))
        screen.blit(f_title.render("SE WEATHER PROXY", True, WHITE),
                    (16, (TITLE_H - f_title.get_height()) // 2))
        xg = f_x.render("X", True, WHITE)
        screen.blit(xg, xg.get_rect(center=quit_rect.center))
        clk = time.strftime("%-I:%M %p")
        ct = f_title.render(clk, True, WHITE)
        screen.blit(ct, (quit_rect.left - 16 - ct.get_width(), (TITLE_H - ct.get_height()) // 2))

        # left, left-justified: MAC LAST SEEN (big, minutes)
        ly = TITLE_H + int(H * 0.06)
        screen.blit(f_lbl.render("MAC LAST SEEN", True, GRAY), (24, ly))
        hv = fmt_mins(ago)
        f_huge = font(int(H * (0.30 if len(hv) <= 3 else 0.20)))
        screen.blit(f_huge.render(hv, True, seen_color), (20, ly + int(H * 0.055)))

        # right, right-justified: the status block
        ry = TITLE_H + int(H * 0.07)
        dh = int(H * 0.085)
        right_row(ry, "Proxy", svc_ok)
        right_row(ry + dh, "Internet", net_ok)
        temp = st.get("temp")
        wtxt = ("%s°  %s" % (temp, st.get("cond") or "")) if temp is not None else "no data yet"
        right_row(ry + 2 * dh, wtxt)
        right_row(ry + 3 * dh, "%s:%s" % (local_ip(), PORT))
        right_row(ry + 4 * dh, "%d requests" % st.get("count", 0), color=GRAY)

        for b in buttons:
            b.draw(screen, f_btn)
        if toast and now - toast_t < 2.5:
            ts = f_lbl.render(toast, True, BLACK)
            screen.blit(ts, (W - 24 - ts.get_width(), buttons[0].rect.top - int(H * 0.055)))

        pygame.display.flip()
        clock.tick(10)  # 10 fps is plenty for a status panel

    pygame.quit()


if __name__ == "__main__":
    main()
