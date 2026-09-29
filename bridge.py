"""
bridge.py - DJI FPV Controller 2 -> vJoy Bridge for Wardogs
============================================================
Reads your DJI FPV Controller 2 via the Windows Multimedia (WinMM)
joystick API and feeds a vJoy virtual joystick that Wardogs sees
as a standard HOTAS -- identical to how it sees your Saitek X52.

Uses WinMM directly because SDL/pygame ignores the DJI controller.

Prerequisites:
    1. vJoy driver installed (https://github.com/njz3/vJoy/releases)
    2. vJoy device #1 configured with 8 axes + 16 buttons
    3. pip install -r requirements.txt

Usage:
    python bridge.py              # run with default config
    python bridge.py --device 0   # pick a specific WinMM joystick slot
    python bridge.py --silent     # no live display, minimal output
"""

import json
import sys
import os
import io
import time
import math
import argparse
import ctypes
import ctypes.wintypes as w
import webbrowser
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

# ── Try to import vJoy ─────────────────────────────────────────────
try:
    from pyvjoystick import vjoy
    VJOY_AVAILABLE = True
except ImportError:
    VJOY_AVAILABLE = False
except Exception as e:
    print(f"  [!] vJoy import error: {e}")
    VJOY_AVAILABLE = False

# ── Try to import pygame for GUI ───────────────────────────────────
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════
# WinMM Joystick API (reads the DJI controller that SDL ignores)
# ═══════════════════════════════════════════════════════════════════

winmm = ctypes.WinDLL('winmm')

# Constants
JOYERR_NOERROR = 0
JOY_RETURNALL = 0x000000FF
JOY_RETURNRAWDATA = 0x00000100

class JOYCAPS(ctypes.Structure):
    _fields_ = [
        ('wMid', w.WORD),
        ('wPid', w.WORD),
        ('szPname', ctypes.c_wchar * 32),
        ('wXmin', w.UINT), ('wXmax', w.UINT),
        ('wYmin', w.UINT), ('wYmax', w.UINT),
        ('wZmin', w.UINT), ('wZmax', w.UINT),
        ('wNumButtons', w.UINT),
        ('wPeriodMin', w.UINT), ('wPeriodMax', w.UINT),
        ('wRmin', w.UINT), ('wRmax', w.UINT),
        ('wUmin', w.UINT), ('wUmax', w.UINT),
        ('wVmin', w.UINT), ('wVmax', w.UINT),
        ('wCaps', w.UINT),
        ('wMaxAxes', w.UINT),
        ('wNumAxes', w.UINT),
        ('wMaxButtons', w.UINT),
        ('szRegKey', ctypes.c_wchar * 32),
        ('szOEMVxD', ctypes.c_wchar * 260),
    ]

class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ('dwSize', w.DWORD),
        ('dwFlags', w.DWORD),
        ('dwXpos', w.DWORD),
        ('dwYpos', w.DWORD),
        ('dwZpos', w.DWORD),
        ('dwRpos', w.DWORD),
        ('dwUpos', w.DWORD),
        ('dwVpos', w.DWORD),
        ('dwButtons', w.DWORD),
        ('dwButtonNumber', w.DWORD),
        ('dwPOV', w.DWORD),
        ('dwReserved1', w.DWORD),
        ('dwReserved2', w.DWORD),
    ]


class WinMMJoystick:
    """Reads a joystick via the Windows Multimedia API."""

    def __init__(self, joy_id):
        self.joy_id = joy_id
        self.caps = JOYCAPS()
        self.info = JOYINFOEX()
        self.info.dwSize = ctypes.sizeof(JOYINFOEX)
        self.info.dwFlags = JOY_RETURNALL

        result = winmm.joyGetDevCapsW(joy_id, ctypes.byref(self.caps), ctypes.sizeof(JOYCAPS))
        if result != JOYERR_NOERROR:
            raise RuntimeError(f"joyGetDevCaps failed for device {joy_id} (error {result})")

        self.name = self.caps.szPname.strip()
        self.vid = self.caps.wMid
        self.pid = self.caps.wPid
        self.num_axes = self.caps.wNumAxes
        self.num_buttons = self.caps.wNumButtons

        # Axis ranges
        self.axis_ranges = [
            (self.caps.wXmin, self.caps.wXmax),
            (self.caps.wYmin, self.caps.wYmax),
            (self.caps.wZmin, self.caps.wZmax),
            (self.caps.wRmin, self.caps.wRmax),
            (self.caps.wUmin, self.caps.wUmax),
            (self.caps.wVmin, self.caps.wVmax),
        ]

    def poll(self):
        """Read current state. Returns True on success."""
        result = winmm.joyGetPosEx(self.joy_id, ctypes.byref(self.info))
        return result == JOYERR_NOERROR

    def get_axis(self, axis_index):
        """Get axis value normalized to -1.0 .. +1.0"""
        if axis_index < 0 or axis_index >= 6:
            return 0.0

        raw_values = [
            self.info.dwXpos,
            self.info.dwYpos,
            self.info.dwZpos,
            self.info.dwRpos,
            self.info.dwUpos,
            self.info.dwVpos,
        ]

        raw = raw_values[axis_index]
        amin, amax = self.axis_ranges[axis_index]

        if amax == amin:
            return 0.0

        # Normalize to -1.0 .. +1.0
        return ((raw - amin) / (amax - amin)) * 2.0 - 1.0

    def get_button(self, button_index):
        """Get button state (0 or 1)."""
        return 1 if (self.info.dwButtons & (1 << button_index)) else 0


def find_dji_controller(device_index=None):
    """Find the DJI FPV Controller 2 via WinMM. DJI VID = 0x2CA3."""
    DJI_VID = 0x2CA3
    num_devs = winmm.joyGetNumDevs()

    if device_index is not None:
        try:
            joy = WinMMJoystick(device_index)
            return joy
        except RuntimeError:
            return None

    # Auto-detect: strictly look for DJI VID
    for i in range(num_devs):
        try:
            joy = WinMMJoystick(i)
            if joy.vid == DJI_VID:
                return joy
        except RuntimeError:
            continue

    # Note: Do not fall back to other non-vJoy devices; if DJI is unplugged
    # or off, we must report it as disconnected.
    return None


def list_all_joysticks():
    """List all WinMM joysticks."""
    num_devs = winmm.joyGetNumDevs()
    found = []
    for i in range(num_devs):
        try:
            joy = WinMMJoystick(i)
            found.append((i, joy))
        except RuntimeError:
            continue
    return found


# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"

# vJoy HID usage codes for axes
VJOY_AXIS_MAP = {
    "X":   0x30,
    "Y":   0x31,
    "Z":   0x32,
    "RX":  0x33,
    "RY":  0x34,
    "RZ":  0x35,
    "SL0": 0x36,
    "SL1": 0x37,
}


# ═══════════════════════════════════════════════════════════════════
# Display constants
# ═══════════════════════════════════════════════════════════════════

SCREEN_W, SCREEN_H = 600, 430
FPS = 60
BAR_W, BAR_H = 160, 14

# Colors
BG          = (12, 12, 18)
PANEL       = (22, 22, 32)
BORDER      = (50, 50, 65)
TEXT_DIM    = (100, 100, 130)
TEXT_BRIGHT = (210, 210, 230)
ACCENT      = (0, 200, 160)
ACCENT2     = (80, 140, 255)
BAR_BG      = (35, 35, 48)
GREEN       = (80, 255, 140)
RED         = (255, 80, 80)
YELLOW      = (255, 220, 80)
ORANGE      = (255, 160, 60)


# ═══════════════════════════════════════════════════════════════════
# Math helpers
# ═══════════════════════════════════════════════════════════════════

def apply_deadzone(value, deadzone):
    """Apply deadzone with smooth transition."""
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def apply_expo(value, expo):
    """Apply exponential curve. expo=0 is linear, expo=1 is full cubic."""
    if expo <= 0:
        return value
    linear = value
    cubic = value ** 3 if value >= 0 else -((-value) ** 3)
    return linear * (1.0 - expo) + cubic * expo


def process_axis(raw_value, axis_cfg):
    """Full axis pipeline: invert -> deadzone -> expo -> trim -> clamp."""
    v = raw_value
    if axis_cfg.get("invert", False):
        v = -v
    v = apply_deadzone(v, axis_cfg.get("deadzone", 0.03))
    v = apply_expo(v, axis_cfg.get("expo", 0.0))
    v += axis_cfg.get("trim", 0.0)
    return max(-1.0, min(1.0, v))


def to_vjoy_range(value):
    """Convert -1.0 .. +1.0 to vJoy range (0x1 .. 0x8000)."""
    return int(((value + 1.0) / 2.0) * 0x7FFE) + 1


# ═══════════════════════════════════════════════════════════════════
# Drawing helpers (pygame)
# ═══════════════════════════════════════════════════════════════════

def draw_bar(surface, x, y, value, color=None, w_=BAR_W, h_=BAR_H):
    if color is None:
        color = ACCENT
    pygame.draw.rect(surface, BAR_BG, (x, y, w_, h_), border_radius=3)
    center = x + w_ // 2
    fill_w = int((w_ / 2) * abs(value))
    if value >= 0:
        pygame.draw.rect(surface, color, (center, y + 1, fill_w, h_ - 2), border_radius=2)
    else:
        pygame.draw.rect(surface, color, (center - fill_w, y + 1, fill_w, h_ - 2), border_radius=2)
    pygame.draw.line(surface, BORDER, (center, y), (center, y + h_), 1)


def draw_crosshair(surface, cx, cy, size, x_val, y_val):
    half = size // 2
    pygame.draw.rect(surface, BAR_BG, (cx - half, cy - half, size, size), border_radius=4)
    pygame.draw.rect(surface, BORDER, (cx - half, cy - half, size, size), 1, border_radius=4)
    pygame.draw.line(surface, BORDER, (cx - half, cy), (cx + half, cy), 1)
    pygame.draw.line(surface, BORDER, (cx, cy - half), (cx, cy + half), 1)
    dx = int(x_val * half * 0.9)
    dy = int(y_val * half * 0.9)
    pygame.draw.circle(surface, ACCENT2, (cx + dx, cy + dy), 5)
    pygame.draw.circle(surface, GREEN, (cx + dx, cy + dy), 3)


def acquire_vjoy(vjoy_id):
    """
    Attempt to initialize and acquire vJoy device.
    Returns (vj_device, None) on success, or (None, error_message) on failure.
    """
    if not VJOY_AVAILABLE:
        return None, "pyvjoystick or vJoy driver is missing or not installed."
    try:
        if hasattr(vjoy, '_sdk') and hasattr(vjoy._sdk, 'vJoyEnabled'):
            try:
                if not vjoy._sdk.vJoyEnabled():
                    return None, "vJoy driver is installed but disabled/not running in Windows."
            except Exception:
                pass

        vj = vjoy.VJoyDevice(vjoy_id)
        # Center all possible axes so none float at 0 (full negative deflection)
        for hid in [0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37]:
            try:
                vj.set_axis(hid, 0x4000)
            except Exception:
                pass
        return vj, None
    except Exception as e:
        err = str(e).strip()
        if not err:
            err = f"vJoy device #{vjoy_id} not available or not enabled."
        return None, err


def show_vjoy_retry_screen(screen, clock, font_title, font_main, font_small, error_msg, vjoy_id):
    """
    Displays a polished error and retry screen when vJoy is not running or not configured.
    Returns True when user clicks 'Try Again', or False if user quits / presses Esc.
    """
    retry_btn_rect = pygame.Rect(SCREEN_W // 2 - 140, 290, 130, 36)
    quit_btn_rect = pygame.Rect(SCREEN_W // 2 + 10, 290, 130, 36)
    credit_rect = pygame.Rect(SCREEN_W // 2 - 70, SCREEN_H - 24, 140, 20)

    waiting = True
    while waiting:
        mouse_pos = pygame.mouse.get_pos()
        hover_retry = retry_btn_rect.collidepoint(mouse_pos)
        hover_quit = quit_btn_rect.collidepoint(mouse_pos)
        hover_credit = credit_rect.collidepoint(mouse_pos)

        if hover_retry or hover_quit or hover_credit:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hover_retry:
                    return True
                elif hover_quit:
                    return False
                elif hover_credit:
                    webbrowser.open("https://github.com/mokocode")

        screen.fill(BG)

        # Header panel
        pygame.draw.rect(screen, PANEL, (0, 0, SCREEN_W, 44))
        pygame.draw.line(screen, BORDER, (0, 44), (SCREEN_W, 44), 1)

        t1 = font_title.render("DJI -> vJoy Bridge", True, TEXT_BRIGHT)
        screen.blit(t1, (14, 5))
        st = font_main.render("VJOY NOT RUNNING", True, RED)
        screen.blit(st, (14, 26))

        # Warning card
        card_rect = pygame.Rect(30, 64, SCREEN_W - 60, 205)
        pygame.draw.rect(screen, PANEL, card_rect, border_radius=6)
        pygame.draw.rect(screen, RED, card_rect, width=1, border_radius=6)

        warn_title = font_title.render("vJoy Driver or Device Not Detected", True, RED)
        screen.blit(warn_title, (48, 80))

        err_line = font_small.render(f"Reason: {error_msg[:68]}", True, ORANGE)
        screen.blit(err_line, (48, 108))

        steps = [
            f"1. Make sure vJoy is installed and running on your system.",
            f"2. Open 'Configure vJoy' from Start Menu and verify Device #{vjoy_id} exists.",
            f"3. Ensure at least 8 axes and 16 buttons are enabled and checked.",
            f"4. Once configured or launched, click 'Try Again' below to proceed.",
        ]
        sy = 140
        for step in steps:
            st_text = font_small.render(step, True, TEXT_BRIGHT)
            screen.blit(st_text, (48, sy))
            sy += 24

        # 'Try Again' button
        btn_bg = ACCENT if hover_retry else (0, 140, 110)
        pygame.draw.rect(screen, btn_bg, retry_btn_rect, border_radius=5)
        retry_lbl = font_main.render("Try Again", True, BG if hover_retry else TEXT_BRIGHT)
        screen.blit(retry_lbl, retry_lbl.get_rect(center=retry_btn_rect.center))

        # 'Quit' button
        quit_bg = BORDER if not hover_quit else (80, 80, 100)
        pygame.draw.rect(screen, quit_bg, quit_btn_rect, border_radius=5)
        quit_lbl = font_main.render("Quit", True, TEXT_BRIGHT)
        screen.blit(quit_lbl, quit_lbl.get_rect(center=quit_btn_rect.center))

        # Footer
        hint = font_small.render("Press Enter to Try Again  |  Esc to Quit", True, TEXT_DIM)
        screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H - 40))

        credit = font_small.render("Made by mokocode", True, ACCENT)
        credit_rect = credit.get_rect(center=(SCREEN_W // 2, SCREEN_H - 18))
        screen.blit(credit, credit_rect)

        pygame.display.flip()
        clock.tick(60)

    return False


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def load_config():
    if not CONFIG_PATH.exists():
        print(f"  [X] Config not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="DJI FPV Controller 2 -> vJoy Bridge")
    parser.add_argument("--device", type=int, default=None, help="WinMM joystick index (run detect to find)")
    parser.add_argument("--vjoy-id", type=int, default=1, help="vJoy device ID (default: 1)")
    parser.add_argument("--silent", action="store_true", help="No GUI, minimal console output")
    parser.add_argument("--list", action="store_true", help="List all detected controllers and exit")
    args = parser.parse_args()

    # ── Banner ──
    print()
    print("  +======================================================+")
    print("  |   DJI FPV Controller 2 -> vJoy Bridge for Wardogs    |")
    print("  |                 Made by mokocode                     |")
    print("  +======================================================+")
    print()

    # ── List mode ──
    if args.list:
        joysticks = list_all_joysticks()
        if not joysticks:
            print("  No controllers found.")
        else:
            print(f"  Found {len(joysticks)} controller(s):\n")
            for idx, joy in joysticks:
                dji_marker = " <-- DJI" if joy.vid == 0x2CA3 else ""
                vjoy_marker = " <-- vJoy" if 'vjoy' in joy.name.lower() else ""
                print(f"    [{idx}] {joy.name} (VID:{joy.vid:#06x} PID:{joy.pid:#06x}) "
                      f"axes:{joy.num_axes} buttons:{joy.num_buttons}{dji_marker}{vjoy_marker}")
        print()
        return

    # ── Load config ──
    cfg = load_config()
    polling_hz = cfg.get("polling_rate_hz", 500)
    poll_interval = 1.0 / polling_hz

    # ── Init pygame for GUI ──
    screen = None
    clock = None
    font_title = font_main = font_small = None

    if not args.silent and PYGAME_AVAILABLE:
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("DJI -> vJoy Bridge")
        try:
            wm_info = pygame.display.get_wm_info()
            hwnd = wm_info.get('window')
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        font_title = pygame.font.SysFont("Consolas", 16, bold=True)
        font_main  = pygame.font.SysFont("Consolas", 13)
        font_small = pygame.font.SysFont("Consolas", 11)
        clock = pygame.time.Clock()

    # ── Check & Init vJoy (with retry screen if not running) ──
    vj = None
    while vj is None:
        vj, vjoy_err = acquire_vjoy(args.vjoy_id)
        if vj is not None:
            print(f"  [OK] vJoy device #{args.vjoy_id} acquired and axes centered")
            break

        # Failed to acquire vJoy
        print(f"\n  [X] vJoy device #{args.vjoy_id} not available: {vjoy_err}")
        print("      -> Ensure vJoy driver is installed and running.")
        print(f"      -> In 'Configure vJoy', ensure device #{args.vjoy_id} is added with 8 axes and 16 buttons.")

        if screen is not None:
            retry = show_vjoy_retry_screen(screen, clock, font_title, font_main, font_small, vjoy_err, args.vjoy_id)
            if not retry:
                print("  Startup cancelled by user.")
                if PYGAME_AVAILABLE:
                    pygame.quit()
                sys.exit(0)
        else:
            # Silent / console mode retry prompt
            try:
                ans = input("  Press Enter to try again (or Ctrl+C to exit)... ")
            except (KeyboardInterrupt, EOFError):
                print("\n  Exiting.")
                sys.exit(0)

    # ── Initial scan for DJI controller ──
    print("\n  Scanning controllers via Windows Multimedia API...")
    joysticks = list_all_joysticks()
    for idx, joy in joysticks:
        dji_marker = " <-- DJI" if joy.vid == 0x2CA3 else ""
        vjoy_marker = " <-- vJoy" if 'vjoy' in joy.name.lower() else ""
        print(f"    [{idx}] {joy.name} (VID:{joy.vid:#06x} PID:{joy.pid:#06x}) "
              f"axes:{joy.num_axes} buttons:{joy.num_buttons}{dji_marker}{vjoy_marker}")

    dji = find_dji_controller(args.device)
    if dji:
        print(f"\n  [OK] DJI controller connected: slot [{dji.joy_id}] {dji.name}")
        print(f"       VID:{dji.vid:#06x} PID:{dji.pid:#06x} axes:{dji.num_axes} buttons:{dji.num_buttons}")
    else:
        print("\n  [!] DJI controller not connected yet. Waiting for connection...")
        print("      Make sure it is powered on and plugged in via USB-C.")

    print()
    print("  Bridge active. In Wardogs, bind your HOTAS to 'vJoy Device'.")
    print("  Press Ctrl+C or close window to stop.\n")

    # ── Axis config lookup ──
    axes_cfg = cfg.get("axes", {})
    buttons_cfg = cfg.get("buttons", {})

    # Pre-resolve axis names -> HID usage codes
    axis_entries = []
    for label, acfg in axes_cfg.items():
        vjoy_name = acfg.get("vjoy_axis", "X").upper()
        hid_usage = VJOY_AXIS_MAP.get(vjoy_name)
        if hid_usage is None:
            print(f"  [!] Unknown vJoy axis '{vjoy_name}' for '{label}', skipping")
            continue
        axis_entries.append({
            "label": label,
            "source": acfg["source_axis"],
            "hid_usage": hid_usage,
            "vjoy_name": vjoy_name,
            "cfg": acfg,
        })

    # ── Main loop ──
    running = True
    processed_values = {}
    frame_count = 0
    gui_interval = 1.0 / 60.0
    last_gui_time = 0.0
    last_console_time = 0.0
    last_reconnect_time = 0.0
    is_connected = False
    credit_rect = pygame.Rect(SCREEN_W // 2 - 70, SCREEN_H - 24, 140, 20)

    try:
        while running:
            t_start = time.perf_counter()
            now = t_start

            # ── Connection check / auto-reconnect scan ──
            if dji is None:
                if (now - last_reconnect_time) >= 1.0:
                    last_reconnect_time = now
                    dji = find_dji_controller(args.device)
                    if dji:
                        print(f"\n  [OK] DJI controller connected: slot [{dji.joy_id}] {dji.name}")

            # ── Read DJI -> Write vJoy (high rate, up to 500 Hz) ──
            if dji is not None and dji.poll():
                is_connected = True
                # Axes
                for entry in axis_entries:
                    src_idx = entry["source"]
                    raw = dji.get_axis(src_idx)
                    processed = process_axis(raw, entry["cfg"])
                    processed_values[entry["label"]] = processed
                    vjoy_val = to_vjoy_range(processed)
                    vj.set_axis(entry["hid_usage"], vjoy_val)

                # Buttons
                for src_str, dst_btn in buttons_cfg.items():
                    src_btn = int(src_str)
                    state = dji.get_button(src_btn)
                    vj.set_button(dst_btn, state)
            else:
                if is_connected:
                    print("\n  [!] DJI controller disconnected!")
                is_connected = False
                dji = None  # Force re-acquisition scan
                # Center axes on vJoy when disconnected
                for entry in axis_entries:
                    processed_values[entry["label"]] = 0.0
                    vj.set_axis(entry["hid_usage"], 0x4000)
                for src_str, dst_btn in buttons_cfg.items():
                    vj.set_button(int(dst_btn), 0)

            # ── Handle pygame events and GUI redraw (throttled to ~60 FPS) ──
            if screen is not None and (now - last_gui_time) >= gui_interval:
                last_gui_time = now

                mouse_pos = pygame.mouse.get_pos()
                hover_credit = credit_rect.collidepoint(mouse_pos)
                if hover_credit:
                    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
                else:
                    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            running = False
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if hover_credit:
                            webbrowser.open("https://github.com/mokocode")

                screen.fill(BG)

                # Header
                pygame.draw.rect(screen, PANEL, (0, 0, SCREEN_W, 44))
                pygame.draw.line(screen, BORDER, (0, 44), (SCREEN_W, 44), 1)

                t1 = font_title.render("DJI -> vJoy Bridge", True, TEXT_BRIGHT)
                screen.blit(t1, (14, 5))

                if is_connected and dji is not None:
                    st = font_main.render("CONNECTED", True, GREEN)
                    screen.blit(st, (14, 26))
                    nt = font_small.render(f"DJI slot [{dji.joy_id}] VID:{dji.vid:#06x}", True, TEXT_DIM)
                    screen.blit(nt, (SCREEN_W - nt.get_width() - 14, 28))
                else:
                    st = font_main.render("DISCONNECTED - WAITING FOR CONTROLLER", True, RED)
                    screen.blit(st, (14, 26))
                    nt = font_small.render("Turn on & plug in DJI FPV Controller 2", True, ORANGE)
                    screen.blit(nt, (SCREEN_W - nt.get_width() - 14, 28))

                vjt = font_small.render(f"-> vJoy #{args.vjoy_id}", True, ACCENT)
                screen.blit(vjt, (SCREEN_W - vjt.get_width() - 14, 8))

                # ── Axis readouts ──
                y_offset = 58
                lbl = font_main.render("AXIS MAPPING", True, ACCENT)
                screen.blit(lbl, (14, y_offset))
                y_offset += 22

                for entry in axis_entries:
                    label = entry["label"].upper()
                    val = processed_values.get(entry["label"], 0.0)

                    tag = font_main.render(f"{label:>8s} -> {entry['vjoy_name']:>4s}", True, TEXT_DIM)
                    screen.blit(tag, (14, y_offset))

                    bar_x = 180
                    bar_color = ACCENT2 if abs(val) > 0.1 else ACCENT
                    draw_bar(screen, bar_x, y_offset, val, bar_color)

                    vt = font_main.render(f"{val:+.2f}", True, TEXT_BRIGHT if is_connected else TEXT_DIM)
                    screen.blit(vt, (bar_x + BAR_W + 10, y_offset))

                    y_offset += 24

                # ── Stick visualizers ──
                viz_y = y_offset + 20

                roll_v = processed_values.get("roll", 0.0)
                pitch_v = processed_values.get("pitch", 0.0)
                draw_crosshair(screen, 120, viz_y + 60, 110, roll_v, pitch_v)
                rl = font_small.render("Right Stick (Roll/Pitch)", True, TEXT_DIM)
                screen.blit(rl, (120 - rl.get_width() // 2, viz_y + 120))

                yaw_v = processed_values.get("yaw", 0.0)
                thr_v = processed_values.get("throttle", 0.0)
                draw_crosshair(screen, 340, viz_y + 60, 110, yaw_v, thr_v)
                ll = font_small.render("Left Stick (Yaw/Throttle)", True, TEXT_DIM)
                screen.blit(ll, (340 - ll.get_width() // 2, viz_y + 120))

                # ── Buttons ──
                btn_y = viz_y + 150
                bl = font_main.render("BUTTONS", True, ACCENT)
                screen.blit(bl, (14, btn_y))
                btn_y += 20

                for src_str, dst_btn in buttons_cfg.items():
                    src_btn = int(src_str)
                    pressed = dji.get_button(src_btn) if (is_connected and dji is not None) else False
                    col_idx = list(buttons_cfg.keys()).index(src_str)
                    bx = 14 + col_idx * 52
                    color = GREEN if pressed else BORDER
                    pygame.draw.rect(screen, color, (bx, btn_y, 42, 20), border_radius=4)
                    if not pressed:
                        pygame.draw.rect(screen, BAR_BG, (bx + 2, btn_y + 2, 38, 16), border_radius=3)
                    bt = font_small.render(f"{src_btn}->{dst_btn}", True, TEXT_BRIGHT if pressed else TEXT_DIM)
                    screen.blit(bt, (bx + 21 - bt.get_width() // 2, btn_y + 3))

                # Footer
                ft = font_small.render("ESC to quit  |  In Wardogs: Settings > HOTAS > select 'vJoy Device'", True, TEXT_DIM)
                screen.blit(ft, (SCREEN_W // 2 - ft.get_width() // 2, SCREEN_H - 32))

                credit = font_small.render("Made by mokocode", True, ACCENT2 if hover_credit else ACCENT)
                credit_rect = credit.get_rect(center=(SCREEN_W // 2, SCREEN_H - 17))
                screen.blit(credit, credit_rect)

                pygame.display.flip()

            # Console live status line (every 0.5s)
            if (now - last_console_time) >= 0.5:
                last_console_time = now
                if is_connected:
                    parts = [f"{e['label'][:3].upper()}:{processed_values.get(e['label'], 0.0):+0.2f}" for e in axis_entries]
                    status_str = " | ".join(parts)
                    sys.stdout.write(f"\r  [Live] {status_str}    ")
                else:
                    sys.stdout.write("\r  [Live] Controller DISCONNECTED - waiting for DJI controller...    ")
                sys.stdout.flush()

            # ── Timing ──
            elapsed = time.perf_counter() - t_start
            sleep_time = poll_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            frame_count += 1

    except KeyboardInterrupt:
        print("\n  Bridge stopped.\n")

    # ── Cleanup: center all axes on exit ──
    if vj is not None:
        try:
            for entry in axis_entries:
                vj.set_axis(entry["hid_usage"], 0x4000)
            for src_str, dst_btn in buttons_cfg.items():
                vj.set_button(int(dst_btn), 0)
        except Exception:
            pass

    if PYGAME_AVAILABLE:
        try:
            pygame.quit()
        except Exception:
            pass

    print("  [OK] Clean shutdown. See you in the skies.\n")


if __name__ == "__main__":
    main()
