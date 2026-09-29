"""
detect.py - DJI FPV Controller 2 Diagnostic Tool
==================================================
Lists all controllers via Windows Multimedia API and shows live
axis + button data in a pygame window.

Run this FIRST to identify your controller's axis indices.
Move one stick at a time and note which axis index changes.
Use that info to update config.json if the defaults don't match.
"""

import sys
import os
import io
import time
import ctypes
import ctypes.wintypes as w

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

import pygame


# ── WinMM Joystick API ────────────────────────────────────────────

winmm = ctypes.WinDLL('winmm')
JOYERR_NOERROR = 0
JOY_RETURNALL = 0x000000FF

class JOYCAPS(ctypes.Structure):
    _fields_ = [
        ('wMid', w.WORD), ('wPid', w.WORD),
        ('szPname', ctypes.c_wchar * 32),
        ('wXmin', w.UINT), ('wXmax', w.UINT),
        ('wYmin', w.UINT), ('wYmax', w.UINT),
        ('wZmin', w.UINT), ('wZmax', w.UINT),
        ('wNumButtons', w.UINT),
        ('wPeriodMin', w.UINT), ('wPeriodMax', w.UINT),
        ('wRmin', w.UINT), ('wRmax', w.UINT),
        ('wUmin', w.UINT), ('wUmax', w.UINT),
        ('wVmin', w.UINT), ('wVmax', w.UINT),
        ('wCaps', w.UINT), ('wMaxAxes', w.UINT),
        ('wNumAxes', w.UINT), ('wMaxButtons', w.UINT),
        ('szRegKey', ctypes.c_wchar * 32),
        ('szOEMVxD', ctypes.c_wchar * 260),
    ]

class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ('dwSize', w.DWORD), ('dwFlags', w.DWORD),
        ('dwXpos', w.DWORD), ('dwYpos', w.DWORD),
        ('dwZpos', w.DWORD), ('dwRpos', w.DWORD),
        ('dwUpos', w.DWORD), ('dwVpos', w.DWORD),
        ('dwButtons', w.DWORD), ('dwButtonNumber', w.DWORD),
        ('dwPOV', w.DWORD),
        ('dwReserved1', w.DWORD), ('dwReserved2', w.DWORD),
    ]

AXIS_NAMES = ["X", "Y", "Z", "R", "U", "V"]


def get_joystick(joy_id):
    """Get caps for a WinMM joystick. Returns (caps, info) or None."""
    caps = JOYCAPS()
    result = winmm.joyGetDevCapsW(joy_id, ctypes.byref(caps), ctypes.sizeof(JOYCAPS))
    if result != JOYERR_NOERROR:
        return None
    info = JOYINFOEX()
    info.dwSize = ctypes.sizeof(JOYINFOEX)
    info.dwFlags = JOY_RETURNALL
    return caps, info


def poll_joystick(joy_id, info):
    """Poll joystick state. Returns True on success."""
    return winmm.joyGetPosEx(joy_id, ctypes.byref(info)) == JOYERR_NOERROR


def get_axis_value(info, caps, axis_index):
    """Get normalized axis value (-1.0 .. +1.0)."""
    raw_values = [info.dwXpos, info.dwYpos, info.dwZpos,
                  info.dwRpos, info.dwUpos, info.dwVpos]
    ranges = [
        (caps.wXmin, caps.wXmax), (caps.wYmin, caps.wYmax),
        (caps.wZmin, caps.wZmax), (caps.wRmin, caps.wRmax),
        (caps.wUmin, caps.wUmax), (caps.wVmin, caps.wVmax),
    ]
    if axis_index >= 6:
        return 0.0
    raw = raw_values[axis_index]
    amin, amax = ranges[axis_index]
    if amax == amin:
        return 0.0
    return ((raw - amin) / (amax - amin)) * 2.0 - 1.0


# ── Constants ──────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 820, 520
BAR_W, BAR_H = 200, 18
PADDING = 20
FPS = 60

# Colors
BG          = (18, 18, 24)
PANEL       = (28, 28, 38)
BORDER      = (55, 55, 75)
TEXT_DIM    = (120, 120, 150)
TEXT_BRIGHT = (220, 220, 240)
ACCENT      = (0, 200, 160)
ACCENT2     = (80, 140, 255)
BAR_BG      = (40, 40, 55)
RED         = (255, 80, 80)
GREEN       = (80, 255, 140)
YELLOW      = (255, 220, 80)


def draw_bar(surface, x, y, value, color=ACCENT):
    pygame.draw.rect(surface, BAR_BG, (x, y, BAR_W, BAR_H), border_radius=4)
    center = x + BAR_W // 2
    fill_w = int((BAR_W / 2) * abs(value))
    if value >= 0:
        pygame.draw.rect(surface, color, (center, y + 2, fill_w, BAR_H - 4), border_radius=3)
    else:
        pygame.draw.rect(surface, color, (center - fill_w, y + 2, fill_w, BAR_H - 4), border_radius=3)
    pygame.draw.line(surface, BORDER, (center, y), (center, y + BAR_H), 1)


def main():
    # ── Enumerate joysticks ──
    print()
    print("+==================================================+")
    print("|     DJI FPV Controller 2 -- Diagnostic Tool      |")
    print("+==================================================+")
    print()

    num_devs = winmm.joyGetNumDevs()
    devices = []

    for i in range(num_devs):
        result = get_joystick(i)
        if result:
            caps, info = result
            dji_marker = " <-- DJI" if caps.wMid == 0x2CA3 else ""
            vjoy_marker = " <-- vJoy" if 'vjoy' in caps.szPname.lower() else ""
            print(f"  [{i}] {caps.szPname.strip()} "
                  f"(VID:{caps.wMid:#06x} PID:{caps.wPid:#06x}) "
                  f"axes:{caps.wNumAxes} buttons:{caps.wNumButtons}"
                  f"{dji_marker}{vjoy_marker}")
            devices.append((i, caps, info))

    if not devices:
        print("  [!] No controllers detected.")
        print("      1. Plug in DJI controller via USB-C")
        print("      2. Power it on (tap once, then hold)")
        print("      3. Run this script again")
        print()
        input("  Press Enter to exit...")
        return

    # Auto-select: prefer DJI, then first non-vJoy device
    selected = None
    for idx, caps, info in devices:
        if caps.wMid == 0x2CA3:
            selected = (idx, caps, info)
            break
    if selected is None:
        for idx, caps, info in devices:
            if 'vjoy' not in caps.szPname.lower():
                selected = (idx, caps, info)
                break
    if selected is None:
        selected = devices[0]

    sel_id, sel_caps, sel_info = selected
    sel_name = sel_caps.szPname.strip()
    print(f"\n  Monitoring: [{sel_id}] {sel_name}\n")

    # ── Pygame GUI ──
    os.environ['SDL_VIDEO_CENTERED'] = '1'
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption(f"Detect: {sel_name}")
    try:
        wm_info = pygame.display.get_wm_info()
        hwnd = wm_info.get('window')
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont("Consolas", 18, bold=True)
    font_main  = pygame.font.SysFont("Consolas", 14)
    font_small = pygame.font.SysFont("Consolas", 12)

    button_flash = {}
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # Poll the controller
        poll_ok = poll_joystick(sel_id, sel_info)

        # Check buttons for flash
        if poll_ok:
            for b in range(sel_caps.wNumButtons):
                pressed = (sel_info.dwButtons & (1 << b)) != 0
                if pressed and b not in button_flash:
                    print(f"  Button {b} PRESSED")
                    button_flash[b] = time.time()
                elif not pressed and b in button_flash:
                    print(f"  Button {b} released")
                    del button_flash[b]

        # ── Draw ──
        screen.fill(BG)

        # Header
        title_text = f"{sel_name}  |  VID:{sel_caps.wMid:#06x}  PID:{sel_caps.wPid:#06x}  |  {sel_caps.wNumAxes} axes  |  {sel_caps.wNumButtons} buttons"
        title_surf = font_title.render(title_text, True, TEXT_BRIGHT)
        screen.blit(title_surf, (PADDING, 12))

        status = "READING" if poll_ok else "ERROR"
        status_color = GREEN if poll_ok else RED
        st_surf = font_main.render(status, True, status_color)
        screen.blit(st_surf, (SCREEN_W - st_surf.get_width() - PADDING, 14))

        # ── Axes panel ──
        panel_x, panel_y = PADDING, 45
        num_axes = min(sel_caps.wNumAxes, 6)
        panel_h = max(40, 28 + num_axes * 28)
        pygame.draw.rect(screen, PANEL, (panel_x, panel_y, SCREEN_W - 2 * PADDING, panel_h), border_radius=8)
        pygame.draw.rect(screen, BORDER, (panel_x, panel_y, SCREEN_W - 2 * PADDING, panel_h), 1, border_radius=8)

        lbl = font_main.render("AXES (move one stick at a time to identify)", True, ACCENT)
        screen.blit(lbl, (panel_x + 12, panel_y + 6))

        for i in range(num_axes):
            val = get_axis_value(sel_info, sel_caps, i) if poll_ok else 0.0
            row_y = panel_y + 28 + i * 28

            ax_lbl = font_main.render(f"Axis {i} ({AXIS_NAMES[i]}):", True, TEXT_DIM)
            screen.blit(ax_lbl, (panel_x + 20, row_y))

            bar_x = panel_x + 150
            color = ACCENT2 if abs(val) > 0.15 else ACCENT
            draw_bar(screen, bar_x, row_y, val, color)

            val_text = font_main.render(f"{val:+.3f}", True, TEXT_BRIGHT)
            screen.blit(val_text, (bar_x + BAR_W + 12, row_y))

            # Raw value
            raw_values = [sel_info.dwXpos, sel_info.dwYpos, sel_info.dwZpos,
                          sel_info.dwRpos, sel_info.dwUpos, sel_info.dwVpos]
            raw_text = font_small.render(f"raw:{raw_values[i]}", True, TEXT_DIM)
            screen.blit(raw_text, (bar_x + BAR_W + 85, row_y + 2))

        # ── Buttons panel ──
        btn_panel_y = panel_y + panel_h + 12
        num_buttons = sel_caps.wNumButtons
        btn_rows = (num_buttons + 15) // 16
        btn_panel_h = max(50, 32 + btn_rows * 32)
        pygame.draw.rect(screen, PANEL, (panel_x, btn_panel_y, SCREEN_W - 2 * PADDING, btn_panel_h), border_radius=8)
        pygame.draw.rect(screen, BORDER, (panel_x, btn_panel_y, SCREEN_W - 2 * PADDING, btn_panel_h), 1, border_radius=8)

        lbl2 = font_main.render("BUTTONS", True, ACCENT)
        screen.blit(lbl2, (panel_x + 12, btn_panel_y + 6))

        for i in range(num_buttons):
            row = i // 16
            col = i % 16
            bx = panel_x + 20 + col * 48
            by = btn_panel_y + 30 + row * 30

            pressed = (sel_info.dwButtons & (1 << i)) != 0 if poll_ok else False
            flash_age = time.time() - button_flash.get(i, 0) if i in button_flash else 999

            if pressed:
                color = GREEN
            elif flash_age < 0.5:
                color = YELLOW
            else:
                color = BORDER

            pygame.draw.rect(screen, color, (bx, by, 38, 22), border_radius=5)
            if not pressed:
                pygame.draw.rect(screen, BAR_BG, (bx + 2, by + 2, 34, 18), border_radius=4)

            btn_lbl = font_small.render(str(i), True, TEXT_BRIGHT if pressed else TEXT_DIM)
            screen.blit(btn_lbl, (bx + 19 - btn_lbl.get_width() // 2, by + 4))

        # ── Config hint ──
        hint_y = btn_panel_y + btn_panel_h + 15
        pygame.draw.rect(screen, PANEL, (panel_x, hint_y, SCREEN_W - 2 * PADDING, 60), border_radius=8)
        pygame.draw.rect(screen, BORDER, (panel_x, hint_y, SCREEN_W - 2 * PADDING, 60), 1, border_radius=8)

        hint_lbl = font_main.render("CONFIG MAPPING (update config.json if these don't match)", True, YELLOW)
        screen.blit(hint_lbl, (panel_x + 12, hint_y + 6))

        mapping_text = "Default: Axis 0=Yaw(LX)  Axis 1=Throttle(LY)  Axis 2=Roll(RX)  Axis 3=Pitch(RY)"
        hint_map = font_small.render(mapping_text, True, TEXT_DIM)
        screen.blit(hint_map, (panel_x + 12, hint_y + 28))

        hint_tip = font_small.render("Move ONE stick at a time. Note which axis number moves. Update 'source_axis' in config.json.", True, TEXT_DIM)
        screen.blit(hint_tip, (panel_x + 12, hint_y + 42))

        # ── Footer ──
        hint = font_small.render("ESC to quit  |  Note your axis numbers, then run BRIDGE.bat", True, TEXT_DIM)
        screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H - 18))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
