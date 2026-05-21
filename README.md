# ✋ Air Gesture HMI

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green?logo=opencv)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.14-orange)
![Accuracy](https://img.shields.io/badge/Accuracy-98.88%25-brightgreen)
![FPS](https://img.shields.io/badge/FPS-33.6-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

### Real-Time Multimodal Gesture-Controlled Human–Computer Interaction System

A real-time gesture-based HCI system using MediaPipe hand tracking, trajectory analysis, and a hybrid Random Forest + Dynamic Time Warping recognition pipeline.

**98.88% air-writing accuracy · 33.6 FPS · CPU-only execution · No specialised hardware required**

</div>

---

## 🚀 Features

* ✍️ Real-time air-writing recognition (A–Z)
* 🖱️ Gesture-controlled virtual mouse
* 🎨 Transparent desktop drawing overlay
* ⌨️ Gesture-controlled on-screen keyboard
* 🎵 Virtual piano, guitar, and violin interaction
* ⚡ Real-time system shortcut gestures
* 🧠 Hybrid RF + DTW recognition pipeline
* 📦 CPU-only execution — no GPU required
* 🖨️ STL / OBJ 3D export from drawings
* 🔒 User handover / lock protection system

---
## 🎥 Demo

[![Demo Video](https://img.shields.io/badge/Watch-Demo-red?logo=youtube)](#)

![Demo](https://github.com/Sidharths916/air-gesture-hmi/assets/Mouse_mode.gif)
---

## 🧠 Project Overview

Air Gesture HMI is a touchless human-computer interaction system that translates mid-air hand gestures into real-time desktop interaction using computer vision and machine learning.

The system combines:

* **MediaPipe Hands** for 21-point 3D hand landmark tracking
* **Rule-based gesture recognition** for interaction control
* **Random Forest classification** for air-writing recognition
* **Dynamic Time Warping (DTW)** for trajectory similarity matching
* **Real-time desktop integration** using PyAutoGUI, Pynput, and Win32 APIs

The application runs entirely on CPU using a standard webcam.

---

# 📊 Performance

| Metric                      | Value        |
| --------------------------- | ------------ |
| Letter recognition accuracy | **98.88%**   |
| Letter classes              | 26 (A–Z)     |
| Random Forest estimators    | 200          |
| Feature count               | 13           |
| Average FPS                 | **33.6 FPS** |
| Average latency             | **29.7 ms**  |
| Runtime hardware            | CPU only     |
| GPU required                | ❌ No         |

### Benchmark Environment

* Windows 11 (64-bit)
* Python 3.10
* Standard USB webcam
* CPU-only execution

---

# 🏗️ System Architecture

```text
Webcam Feed
     ↓
MediaPipe Hand Tracking
     ↓
21 Landmark Extraction
     ↓
Gesture / Trajectory Analysis
     ↓
RF + DTW Recognition Pipeline
     ↓
Mode Router
     ↓
Desktop Interaction / Audio / 3D Export
```

---

# ⚡ Quick Start

## 1. Clone Repository

```bash
git clone https://github.com/Sidharths916/air-gesture-hmi.git
cd air-gesture-hmi
```

## 2. Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

## 3. Install Dependencies

```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

## 4. Download Trained Model

Download `letter_recognizer.pkl` from GitHub Releases and place it inside:

```text
models/
```

## 5. Run

```bash
python main.py
```

---

# 🧰 Tech Stack

| Category          | Technologies                        |
| ----------------- | ----------------------------------- |
| Computer Vision   | OpenCV, MediaPipe                   |
| Machine Learning  | Scikit-learn, Random Forest, DTW    |
| Interaction Layer | PyAutoGUI, Pynput, PyWin32          |
| Audio             | pygame, scipy                       |
| Rendering         | OpenCV overlays, Win32 transparency |
| Language          | Python 3.10                         |

---

# 📁 Project Structure

```text
air-gesture-hmi/
│
├── main.py                    # Core application loop
├── piano_FINALv4.py           # Piano module
├── guitar_FINALv4.py          # Guitar module
├── violin_REFACTOREDv2.py     # Violin module
│
├── assets/                    # Media assets
├── data/                      # User-generated drawings
├── models/                    # Trained ML models
│
├── config.json                # Runtime settings
├── requirements.txt           # Python dependencies
└── README.md
```

---

# 🎮 Modes

## ✏️ Draw Mode

Transparent desktop overlay with:

* fingertip drawing
* colour switching
* eraser support
* 3D export pipeline
* STL / OBJ generation
* anaglyph rendering

### Export Support

* PNG
* STL
* OBJ + MTL + texture PNG
* Anaglyph 3D image

---

## ✍️ Write Mode

Real-time air-writing recognition system.

### Pipeline

1. Trajectory capture
2. Stroke normalisation
3. Feature extraction
4. RF classification
5. DTW template matching
6. Score fusion
7. Real keyboard output

### Recognition Features

* 13 handcrafted geometric features
* 64-point trajectory resampling
* confidence threshold filtering
* DTW similarity comparison

---

## 🖱️ Mouse Mode

Gesture-controlled virtual mouse system.

### Supported Actions

* cursor movement
* left click
* right click
* drag / hold
* scroll up/down

---

## ⌨️ On-Screen Keyboard

Transparent gesture-controlled virtual keyboard.

### Features

* fullscreen overlay
* hover interaction
* Z-depth press detection
* static & dynamic modes
* modifier key support

---

## 🎵 Music Mode

Gesture-controlled virtual instruments.

### Included Instruments

* 🎹 Piano
* 🎸 Guitar
* 🎻 Violin

### Audio Features

* synthesized tones
* harmonic layering
* ADSR shaping
* bow simulation
* chord detection

---

## 🎮 Gesture Shortcut Mode

Maps gestures directly to system shortcuts.

### Examples

| Gesture | Action       |
| ------- | ------------ |
| 👍      | Screenshot   |
| 👌      | Save file    |
| ✌️      | Alt + Tab    |
| 🤟      | Zoom in      |
| 🤙      | Browser back |

---

## 🔒 Handover Security System

Basic user handover detection system using torso colour verification.

### Features

* user verification
* auto-lock on mismatch
* auto-unlock on return
* manual recalibration

---

# 🧠 Air-Writing ML Pipeline

## Stage 1 — Hand Tracking

MediaPipe Hands extracts 21 3D landmarks per frame.

## Stage 2 — Feature Extraction

Each trajectory is:

* centroid normalised
* unit scaled
* resampled to 64 points

13 geometric features are extracted including:

* width / height
* aspect ratio
* path length
* curvature
* start / end coordinates
* spatial density

## Stage 3 — Random Forest

A 200-tree Random Forest predicts class probabilities.

## Stage 4 — DTW Matching

Dynamic Time Warping compares trajectory similarity against stored templates.

## Stage 5 — Score Fusion

RF probability and DTW similarity scores are fused for final prediction.

> Final accuracy achieved: **98.88% across all 26 letters (A–Z)**

---

# ⚙️ Requirements

## Software

* Windows 10 / 11
* Python 3.10

## Hardware

* Standard webcam
* CPU execution only

---

# 📦 Major Dependencies

| Library      | Purpose                     |
| ------------ | --------------------------- |
| OpenCV       | Computer vision & rendering |
| MediaPipe    | Hand landmark tracking      |
| Scikit-learn | Random Forest classifier    |
| pygame       | Audio engine                |
| scipy        | Signal filtering            |
| pyautogui    | Mouse & keyboard control    |
| pynput       | System input simulation     |
| pywin32      | Transparent overlays        |

> `mediapipe==0.10.14` and `scikit-learn==1.3.2` are intentionally pinned for compatibility.

---

# ⌨️ Runtime Keyboard Shortcuts

| Key | Action                  |
| --- | ----------------------- |
| ESC | Exit application        |
| U   | Recalibrate user        |
| R   | Reset camera            |
| H   | Toggle skeleton overlay |
| M   | Toggle mirror mode      |
| S   | Toggle sound            |
| F   | Toggle FPS display      |

---

# ⚠️ Known Issues

* Initial startup latency may occur during MediaPipe initialisation
* Transparent overlays are Windows-dependent
* First camera frame may spike in latency during warm-up

---

# 🔮 Future Work

* Multi-hand support
* Linux/macOS support
* CNN-based recognition comparison
* Mobile deployment
* Custom gesture recording
* Embedded deployment (Raspberry Pi)

---

# 📚 Citation

```bibtex
@misc{airgesturehmi2026,
  author    = {Sidharth S},
  title     = {Air Gesture HMI: Real-Time Multimodal Gesture-Controlled Human-Computer Interaction System},
  year      = {2026},
  publisher = {GitHub},
  url       = {https://github.com/Sidharths916/air-gesture-hmi}
}
```

---

# 📄 License

Licensed under the MIT License.

---

# 🙏 Acknowledgements

* MediaPipe by Google
* OpenCV
* pygame
* scikit-learn
