# DJI FPV Controller 2 → vJoy Bridge for Wardogs

Turns your DJI FPV Controller 2 into a standard DirectInput joystick that Wardogs
recognizes as a HOTAS — same as your Saitek X52.

## How It Works

```
DJI FPV Controller 2 ──USB-C──► [bridge.py] ──► vJoy Virtual Joystick ──► Wardogs
       (HID device)              reads axes       (looks like a                sees a
                                 & buttons         real HOTAS)                 joystick
```

The bridge reads your DJI controller's sticks and buttons, applies deadzones/curves,
and feeds them to a **vJoy** virtual joystick device. Wardogs sees vJoy as a
standard flight stick — no different from a Saitek X52.

---

## Prerequisites

1. **Python 3.8 or higher**:
   - `SETUP.bat` will automatically check for and install Python if it is missing on your system.
   - If installing manually, download from [python.org](https://www.python.org/downloads/) and make sure to check **"Add python.exe to PATH"**.
2. **Windows 10 / 11** (64-bit)

---

## Quick Start

### 1. Run Setup (`SETUP.bat`)

Double-click **`SETUP.bat`**:
- Checks for Python; automatically installs it if missing.
- Installs required Python packages (`pygame`, `pyvjoystick`).
- Checks if vJoy is installed. If not, it will automatically launch `vJoySetup_v2.2.2.0_Win10_Win11.exe` included in this folder.

### 2. Configure vJoy (One-Time)

After vJoy is installed:
1. Open **"Configure vJoy"** from the Windows Start menu.
2. Set up **Device #1**:
   - ✅ Check **all 8 axes** (X, Y, Z, Rx, Ry, Rz, Slider, Dial)
   - Set **Number of Buttons** to **16**
   - Click **Apply**

### 3. Find Your Axis Numbers

1. Plug in your DJI FPV Controller 2 via USB-C
2. Power it on (tap power once, then hold it)
3. Double-click **`DETECT.bat`**
4. Move **one stick at a time** and note which axis index moves
5. If the default config doesn't match, edit `config.json` (see below)

### 4. Launch the Bridge

Double-click **`BRIDGE.bat`** — keep it running while you play.

### 5. Configure Wardogs

1. Launch Wardogs
2. Go to **Settings → Gamepad → HOTAS**
3. Set **Enable HOTAS** to **Enabled**
4. Bind your axes to **vJoy Device** (NOT the DJI controller directly)
5. Use the **Firing Range** to test and fine-tune

---

## Config Reference (`config.json`)

### Axis Mapping

The `axes` section maps DJI stick movements to vJoy axes:

| Config Key | Default Source | vJoy Axis | What It Does |
|------------|---------------|-----------|--------------|
| `roll`     | Axis 2        | X         | Right stick left/right |
| `pitch`    | Axis 3        | Y         | Right stick up/down |
| `throttle` | Axis 1        | SL0       | Left stick up/down |
| `yaw`      | Axis 0        | RZ        | Left stick left/right |

**If your sticks don't match** (detect.py shows different numbers), change `source_axis`.

### Axis Options

| Option     | Range         | Description |
|------------|---------------|-------------|
| `invert`   | true/false    | Flip the axis direction |
| `deadzone` | 0.0 – 0.5    | Dead area at center (0.03 = 3%) |
| `expo`     | 0.0 – 1.0    | Response curve: 0=linear, 1=cubic (more precision at center) |
| `trim`     | -1.0 – 1.0   | Offset the center point |

### Available vJoy Axes

`X`, `Y`, `Z`, `RX`, `RY`, `RZ`, `SL0` (Slider), `SL1` (Dial)

### Buttons

Maps DJI button indices to vJoy button numbers. The keys are DJI button numbers
(as strings), values are vJoy button numbers (1–32):

```json
"buttons": {
    "0": 1,
    "1": 2,
    "2": 3
}
```

---

## Troubleshooting

### Controller not detected
- Use a **data-capable** USB-C cable (not charge-only)
- Power on correctly: tap once, then **hold** power
- Close **DJI Assistant 2** if it's running
- In Device Manager, **disable** "HS-Data Channel" and "MA Channel" if present

### Axes don't match
- Run `DETECT.bat` and note which axis index moves for each stick
- Update `source_axis` in `config.json` to match

### Double input in Wardogs
- In Wardogs, only bind the **vJoy Device**, not the DJI controller
- Or install [HidHide](https://github.com/nefarius/HidHide) to hide the DJI
  device from games while keeping it visible to the bridge

### Wardogs doesn't see vJoy
- Make sure "Configure vJoy" shows Device #1 as active (green)
- Run `joy.cpl` (Win+R → `joy.cpl`) to verify vJoy appears in Game Controllers

---

## Files

| File              | Purpose |
|-------------------|---------|
| `SETUP.bat`       | One-time setup — installs dependencies & vJoy |
| `DETECT.bat`      | Identify your controller's axis/button numbers |
| `BRIDGE.bat`      | Launch the bridge (keep running while playing) |
| `vJoySetup_v2.2.2.0_Win10_Win11.exe` | vJoy driver installer |
| `config.json`     | Axis mapping, deadzones, curves |
| `bridge.py`       | Main bridge script |
| `detect.py`       | Controller diagnostic tool |
| `requirements.txt`| Python dependencies |
