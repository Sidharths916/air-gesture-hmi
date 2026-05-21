# ✋ Air Gesture HMI

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green?logo=opencv)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.14-orange)
![Accuracy](https://img.shields.io/badge/Accuracy-98.88%25-brightgreen)
![FPS](https://img.shields.io/badge/FPS-33.6-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

A real-time multimodal gesture-controlled HCI system using trajectory-based hand landmark detection and a hybrid Random Forest + DTW air-writing recognition pipeline. Achieves **98.88% letter recognition accuracy** across 26 classes (A–Z) at **33.6 FPS / 29.7ms latency** on CPU — no GPU or specialised hardware required beyond a standard webcam.

> Developed as part of an MSc project in gesture-based human-computer interaction.

---

## Demo

[![Demo Video](https://img.shields.io/badge/Watch-Demo-red?logo=youtube)](YOUR_YOUTUBE_LINK)

![Demo](assets/demo.gif)

---

## Abstract

Air Gesture HMI is a touchless human-computer interaction system that translates mid-air hand gestures into system-level commands using real-time computer vision and a hybrid machine learning pipeline. The system integrates a Random Forest classifier (200 estimators, 13 features) with Dynamic Time Warping template matching, achieving **98.88% classification accuracy** across 26 letter classes (A–Z) at **33.6 FPS with 29.7ms average inference latency** on consumer CPU hardware — no GPU required.

---

## Performance

| Metric | Value |
|---|---|
| Letter recognition accuracy | **98.88%** |
| Letter classes | **26 (A–Z)** |
| Random Forest trees | 200 |
| Landmark features | 13 |
| Average FPS | **33.6 FPS** |
| Average latency | **29.7 ms** |
| Min latency | 17.6 ms |
| Hardware | CPU only — no GPU needed |

---

## Requirements

- **OS:** Windows 10 or Windows 11 (64-bit)
- **Python:** 3.10 exactly — [download here](https://www.python.org/downloads/release/python-3119/)
- **Hardware:** Standard USB webcam
- **GPU:** Not required — runs entirely on CPU

---

## Libraries

### Third-Party (install via requirements.txt)

| Library | Version | Purpose |
|---|---|---|
| `opencv-python` | 4.11.0.86 | Camera capture, frame processing, window rendering, UI overlay drawing |
| `opencv-contrib-python` | 4.11.0.86 | Extended OpenCV modules |
| `numpy` | 1.26.4 | Matrix operations, canvas manipulation, waveform synthesis, 3D geometry |
| `mediapipe` | **0.10.14** | Real-time hand landmark detection (21 keypoints per hand) |
| `scikit-learn` | **1.3.2** | Random Forest classifier for letter recognition |
| `scipy` | 1.15.3 | IIR digital filtering for violin audio simulation |
| `pygame` | 2.6.1 | Primary audio engine for instruments and UI feedback |
| `pywin32` | 311 | Transparent overlay windows, always-on-top management (Windows API) |
| `pynput` | 1.8.1 | Simulates real keyboard keypresses from recognised gestures |
| `pyautogui` | 0.9.54 | Mouse cursor control, clicking, scrolling, system hotkeys |
| `playsound` | 1.2.2 | Fallback audio playback |
| `matplotlib` | 3.10.9 | Dependency of mediapipe |
| `Pillow` | 12.2.0 | Image processing support |
| `jax` / `jaxlib` | 0.6.2 | Dependency of mediapipe |
| `protobuf` | 4.25.9 | Dependency of mediapipe |
| `sounddevice` | 0.5.5 | Audio I/O support |

> ⚠️ `mediapipe==0.10.14` and `scikit-learn==1.3.2` are pinned — do not upgrade them.
> The trained model was built with these exact versions. Newer versions will break compatibility.

### Standard Library (no install needed)

`sys` · `os` · `cv2` · `time` · `pickle` · `threading` · `datetime` · `collections` · `logging` · `json` · `glob` · `math` · `wave` · `tempfile` · `winsound`

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/air-gesture-hmi.git
cd air-gesture-hmi

# 2. Create virtual environment with Python 3.10 exactly
"C:\Users\YOUR_NAME\AppData\Local\Programs\Python\Python310\python.exe" -m venv venv
venv\Scripts\activate

# 3. Install all dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. Download the trained model from GitHub Releases
letter_recognizer.pkl in the models/ folder

# 5. Run
python main.py
```

---

## Project Structure

```
air-gesture-hmi/
│
├── main.py                    — Core app loop, gesture engine, mode router, UI overlay
├── piano_FINALv4.py           — Piano instrument module
├── guitar_FINALv4.py          — Guitar instrument module
├── violin_REFACTOREDv2.py     — Violin instrument (bow physics + IIR filter)
│
├── assets/
│   ├── songs/                 — JSON song files for guided playback
│   ├── start.mp3              — Startup audio feedback
│   ├── exit.mp3               — Exit audio feedback
│   └── icon.ico               — Application icon
│
├── models/
│   └── letter_recognizer.pkl  — Trained RF + template bank (download from Releases)
│
├── data/
│   └── drawings/              — Exported user drawings saved here
│
├── config.json                — User settings (auto-saved)
└── requirements.txt           — All Python dependencies with pinned versions
```

---

## Modes and Gesture Reference

### 🏠 Main Menu

Entered on startup. All modes are launched from here.

| Gesture | Action |
|---|---|
| ☝️ 1 finger | → Draw mode |
| ✌️ 2 fingers | → Write mode |
| 🤟 3 fingers | → Mouse mode |
| 4 fingers | → On-Screen Keyboard (OSK) |
| 👍 Thumbs up | → Music mode |
| 👌 OK | → Gesture Shortcuts mode |
| ✊ Fist | Pause system |

---

### ✏️ Draw Mode

Renders a transparent fullscreen overlay on top of the desktop. Draws directly on screen using index fingertip position.

**Functions implemented:**
- Transparent always-on-top overlay window via win32 API
- Smoothed fingertip tracking with interpolation buffer
- Gap-filling for fast hand movements (sub-step interpolation)
- Black color workaround — drawn as `(20,20,20)` to survive STL threshold
- Anaglyph 3D generation (red-cyan stereo pair)
- STL mesh export (height-map extrusion, binary STL format)
- Textured OBJ + MTL + PNG export (color-preserving, Blender/Unity ready)

| Gesture | Action |
|---|---|
| ☝️ 1 finger | Draw with current color |
| ✌️ 2 fingers | Cycle to next color |
| 🤟 3 fingers | **Save** — exports 2D PNG + Anaglyph PNG + STL + OBJ/MTL/PNG |
| 4 fingers | Clear canvas |
| 🤙 Pinky | Toggle eraser (40px radius) |
| 🖐️ Palm | Back to Main Menu |

**Export files saved to** `data/drawings/`:
- `drawing_TIMESTAMP.png` — 2D flat image
- `drawing_TIMESTAMP_anaglyph.png` — red-cyan 3D anaglyph
- `drawing_TIMESTAMP.stl` — 3D printable mesh
- `drawing_TIMESTAMP.obj` + `.mtl` + `.png` — textured 3D model

---

### ✍️ Write Mode

Air-write letters — the system recognises them and types into whatever window is active on your PC.

**Functions implemented:**
- Stroke trajectory capture via index fingertip
- Stroke normalisation (centroid-zero, unit-scale)
- Stroke resampling to 64 points
- 13-feature extraction (mean x/y, std x/y, width, height, aspect ratio, path length, density, start/end points, curvature)
- Hybrid RF + DTW prediction with score fusion
- Confidence threshold filtering (>40% required to type)
- Real keyboard simulation via pynput

| Gesture | Action |
|---|---|
| ☝️ 1 finger | Draw stroke |
| Still for 1.5s | Recognise stroke → auto-type letter |
| ✌️ 2 fingers | Type a Space |
| 🤟 3 fingers | Backspace (delete last character) |
| 4 fingers | Clear current stroke |
| 🖐️ Palm | Back to Main Menu |

---

### 🖱️ Mouse Mode

Full mouse control via finger gestures. Index finger position maps to cursor position on screen.

**Functions implemented:**
- Smooth cursor movement with exponential smoothing
- Fail-safe disabled for performance (`pyautogui.PAUSE = 0`)
- Continuous scroll with 80ms cooldown
- Toggle drag (mouseDown / mouseUp)

| Gesture | Action |
|---|---|
| ☝️ Index only | Move cursor |
| 💍 Ring only | Left click |
| 🤙 Pinky only | Right click |
| ✊ Fist | Toggle drag (click-hold / release) |
| ✌️ 2 fingers | Scroll up |
| 🤟 3 fingers | Scroll down |
| 🖐️ Palm | Back to Main Menu |

---

### ⌨️ On-Screen Keyboard (OSK)

Transparent fullscreen keyboard rendered directly on top of the desktop. Two input modes available.

**Functions implemented:**
- Full QWERTY keyboard layout with special keys
- Transparent always-on-top overlay via win32 API
- Z-depth pressing detection (`z < 0.2` = press)
- Static mode: hover-to-activate with configurable dwell time
- Dynamic mode: continuous press with key repeat
- Shift, Caps Lock, Ctrl, Alt, Win modifier keys
- Visual hover progress indicator (colour fill)
- Text field display with cursor blink

**Supported keys:** Full A–Z, 0–9, SPACE, ENTER, BKSP, TAB, SHIFT, CAPS, CTRL, ALT, WIN

| Interaction | Action |
|---|---|
| Hover index finger over key + push forward (Z < 0.2) | Press key |
| Hover over MODE button | Switch Static ↔ Dynamic input mode |
| 🖐️ Palm | Back to Main Menu |

---

### 🎮 Gesture Shortcuts Mode

Maps named gestures to system-level keyboard shortcuts.

**Functions implemented:**
- Windows Snipping Tool screenshot trigger
- File save hotkey
- Browser/app navigation back
- Zoom in / zoom out
- Tab close
- Application switcher

| Gesture | Action | Shortcut |
|---|---|---|
| 👍 Thumbs up | Screenshot | Win + Shift + S |
| 👌 OK | Save file | Ctrl + S |
| 🤙 Pinky | Navigate back | Alt + Left |
| 💍 Ring only | Zoom out | Ctrl + – |
| 4 fingers | Close tab | Ctrl + W |
| ✌️ 2 fingers | Switch app | Alt + Tab |
| 🤟 3 fingers | Zoom in | Ctrl + + |
| 🖐️ Palm | Back to Main Menu | — |

---

### 🎵 Music Mode

Hub for instrument selection and song mode.

| Gesture | Action |
|---|---|
| ☝️ 1 finger | Select Piano |
| ✌️ 2 fingers | Select Guitar |
| 🤟 3 fingers | Select Violin |
| 🖐️ Palm | Back to Main Menu |

After selecting an instrument:

| Gesture | Action |
|---|---|
| 👍 Thumbs up | Launch free-play mode |
| 👌 OK | Enter song selection |
| 🖐️ Palm | Cancel — back to Music Menu |

**Song Selection:**

| Gesture | Action |
|---|---|
| 👌 OK | Play selected song |
| ✌️ 2 fingers (swipe right) | Next song |
| 🤟 3 fingers (swipe left) | Previous song |
| 🖐️ Palm | Back to instrument choice |

---

### 🎹 Piano Mode (`piano_FINALv4.py`)

Virtual air piano. Hover fingers above on-screen keys and push forward to play.

**Functions implemented:**
- Synthesized piano tones (sine + harmonic overtones)
- ADSR envelope shaping per note
- Z-depth key press detection
- Full chromatic scale across multiple octaves
- Polyphonic playback via pygame.mixer channels

---

### 🎸 Guitar Mode (`guitar_FINALv4.py`)

Virtual air guitar. Strum strings with hand movement.

**Functions implemented:**
- String layout rendered on screen
- Strum gesture detection (lateral hand movement)
- Per-string synthesized audio (sawtooth + harmonics)
- Chord finger position detection

---

### 🎻 Violin Mode (`violin_REFACTOREDv2.py`)

Virtual air violin with bow-stroke simulation.

**Functions implemented:**
- Bow-stroke direction and speed detection
- IIR digital low-pass filter via `scipy.signal.lfilter` for realistic timbre
- String selection by hand Y-position
- Note pitch mapped to bow position on string
- Synthesized bowed string audio with continuous tone shaping

---

### 🔒 Security — Handover Protocol

Detects when a different person takes over and locks the system.

**Functions implemented:**
- HSV colour signature capture from torso ROI on startup
- Per-frame colour verification with hue tolerance matching
- Streak-based locking (15 failed frames → lock)
- Streak-based unlocking (10 passed frames → unlock)
- Fist-hold handover: hold fist for 3 seconds to recalibrate for a new user
- Locked screen overlay with status display

| Action | Trigger |
|---|---|
| Auto-lock | Different person detected for 15 consecutive frames |
| Auto-unlock | Original user returns — 10 consecutive matching frames |
| Manual handover | Hold ✊ Fist for 3 seconds |
| Force recalibrate | Press `U` key |

---

## Keyboard Shortcuts (While App is Running)

| Key | Action |
|---|---|
| `ESC` | Exit application |
| `U` | Force recalibrate user identity |
| `R` | Reset and reinitialise camera |
| `H` | Toggle hand skeleton overlay |
| `M` | Toggle mirror mode |
| `S` | Toggle sound feedback on/off |
| `G` | Toggle gesture hints overlay |
| `F` | Toggle FPS display |
| `+` / `=` | Increase UI panel opacity |
| `-` / `_` | Decrease UI panel opacity |
| `[` | Decrease UI font size |
| `]` | Increase UI font size |
| `T` | Increase gesture stability threshold |
| `Y` | Decrease gesture stability threshold |
| `I` | Decrease gesture cooldown time |
| `V` | Reset all calibrations |
| Type `whomadeyou` | 🥚 Easter egg |

---

## How the ML Pipeline Works

### Hand Tracking
MediaPipe Hands detects **21 3D landmarks** per hand at 33.6 FPS on CPU. Normalised x, y, z coordinates are used to count fingers, classify named gestures via rule-based heuristics, and track fingertip trajectories.

### Air-Writing — Hybrid RF + DTW

**Stage 1 — Feature extraction**
Each stroke is normalised (centroid-zero, unit-scale), resampled to 64 points, and 13 features are extracted:
stroke length, mean x, mean y, std x, std y, width, height, aspect ratio, path length, point density, start point, end point, curvature.

**Stage 2 — Random Forest**
200-tree ensemble predicts letter class probabilities from the 13 features.

**Stage 3 — DTW Template Matching**
Stroke shape is compared against up to 15 stored templates per class using Dynamic Time Warping distance.

**Stage 4 — Score Fusion**
RF posterior probability and DTW distance are combined. Result is accepted only if confidence > 40%.

> **98.88% accuracy across all 26 letters (A–Z)**

### 3D Export Pipeline

```
Canvas pixels (BGR)
  → Grayscale + threshold (any pixel > 0 = drawn)
  → Downsample 4× (reduce vertex count)
  → Per-pixel cube geometry (8 vertices, 12 triangles each)
  → Binary STL file (80-byte header + triangle list)
  → Texture PNG (original canvas)
  → OBJ + MTL (UV-mapped, references texture PNG)
```

---

## Configuration (`config.json`)

Settings are auto-saved on every change and reloaded on startup.

| Setting | Default | Description |
|---|---|---|
| `ui_opacity` | 0.7 | Panel background transparency |
| `font_scale` | 0.55 | UI text size |
| `show_skeleton` | true | Hand landmark skeleton overlay |
| `mirror` | true | Flip camera horizontally |
| `sound_feedback` | true | Beep on gesture actions |
| `show_gesture_hints` | true | Show gesture hint overlay |
| `stability_threshold` | 0.7 | Gesture consistency required (0.5–0.95) |
| `global_cooldown` | 0.8 | Minimum seconds between gesture actions |
| `show_fps` | false | FPS counter display |

---

## Known Issues

- Minor shutdown cleanup inconsistencies may occur on some systems
- First launch takes a few seconds while MediaPipe initialises on CPU
- OSK and Draw transparent overlay require Windows — fallback to basic overlay on non-Windows
- Max latency spikes (first frame ~1200ms) are camera warm-up — not representative of runtime performance

---

## Citation

```bibtex
@misc{airgesturehmi2026,
  author    = {Sidharth},
  title     = {Air Gesture HMI: A Real-Time Multimodal Gesture-Controlled
               Human-Machine Interface Using Hybrid RF-DTW Recognition},
  year      = {2026},
  publisher = {GitHub},
  url       = {https://github.com/Sidharths916/air-gesture-hmi}
}
```

---

## Future Work

- Multi-hand support
- Cross-platform support (Linux, macOS)
- CNN comparison study (RF+DTW vs deep learning baseline)
- Real-time custom gesture recording
- Mobile / embedded deployment (Raspberry Pi)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

- [MediaPipe](https://mediapipe.dev/) by Google — hand landmark detection
- [OpenCV](https://opencv.org/) — computer vision framework
- [pygame](https://www.pygame.org/) — audio engine
- [scikit-learn](https://scikit-learn.org/) — machine learning
