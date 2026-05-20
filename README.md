\# ✋ Air Gesture HMI



!\[Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)

!\[Accuracy](https://img.shields.io/badge/Accuracy-98.88%25-brightgreen)

!\[FPS](https://img.shields.io/badge/FPS-33.6-blue)

!\[License](https://img.shields.io/badge/License-MIT-yellow)



A real-time multimodal gesture-controlled HCI system. Achieves \*\*98.88% letter recognition accuracy\*\* across 26 classes (A–Z) at \*\*33.6 FPS / 29.7ms latency\*\* on CPU — no GPU required.



> Developed as part of an MSc project in gesture-based HCI.



\---



\## Demo

\[!\[Demo](https://img.shields.io/badge/Watch-Demo-red?logo=youtube)](YOUR\_YOUTUBE\_LINK)

!\[Demo](assets/demo.gif)



\---



\## Abstract

Air Gesture HMI uses real-time hand landmark detection and a hybrid RF+DTW pipeline to translate mid-air gestures into system commands. Achieves \*\*98.88% accuracy\*\* across 26 letter classes (A–Z) at \*\*33.6 FPS / 29.7ms latency\*\* on CPU.



\---



\## Performance

| Metric | Value |

|---|---|

| Letter recognition accuracy | \*\*98.88%\*\* |

| Letter classes | \*\*26 (A–Z)\*\* |

| RF trees | 200 |

| Features | 13 landmark features |

| Average FPS | \*\*33.6 FPS\*\* |

| Average latency | \*\*29.7 ms\*\* |

| Min latency | 17.6 ms |

| Hardware | CPU only — no GPU |



\---



\## Features

| Mode | Description |

|---|---|

| ✏️ Draw | Air-draw. Exports: PNG, Anaglyph 3D, STL, textured OBJ+MTL+PNG |

| ✍️ Write | Air-write letters. RF+DTW model auto-types into any active window |

| 🖱️ Mouse | Full cursor control — move, click, drag, scroll |

| ⌨️ OSK | Transparent fullscreen on-screen keyboard overlay |

| 🎹 Piano | Virtual air piano with synthesized audio |

| 🎸 Guitar | Virtual air guitar with strum detection |

| 🎻 Violin | Bow-stroke physics + IIR-filtered synthesized audio |

| 🎵 Song Mode | Guided playback via JSON song files |



\---



\## How It Works

\### Hybrid RF + DTW Pipeline

1\. \*\*Random Forest\*\* — 200 trees, 13 landmark features per stroke

2\. \*\*DTW Template Matching\*\* — shape-matches strokes against templates

3\. \*\*Score Fusion\*\* — RF posterior + DTW distance → final decision



> \*\*98.88% accuracy across all 26 letters (A–Z)\*\*



\### 3D Export Pipeline

Canvas pixels → height-map geometry → triangle mesh

→ .stl (3D-printable)

→ .obj + .mtl + .png (textured — Blender/Unity ready)



\---



\## Tech Stack

| Category | Technology |

|---|---|

| Language | Python 3.10 |

| Computer Vision | OpenCV 4.x, MediaPipe 0.10 |

| Machine Learning | scikit-learn (RF), DTW |

| Audio | pygame.mixer, scipy.signal |

| System | pywin32, pynput, pyautogui |

| Math/DSP | NumPy, SciPy |



\---



\## Installation

```bash

git clone https://github.com/Sidharths916/air-gesture-hmi.git

cd air-gesture-hmi

"C:\\Users\\YOU\\AppData\\Local\\Programs\\Python\\Python310\\python.exe" -m venv venv

venv\\Scripts\\activate

pip install -r requirements.txt

```

Download `letter\_recognizer.pkl` from Releases → place in `models/`

```bash

python main.py

```



\---



\## Citation

```bibtex

@misc{airgesturehmi2026,

&#x20; author = {Sidharth},

&#x20; title  = {Air Gesture HMI},

&#x20; year   = {2026},

&#x20; url    = {https://github.com/Sidharths916/air-gesture-hmi}

}

```



\---

\## License

MIT License



\## Acknowledgements

\- MediaPipe by Google

\- OpenCV

\- pygame

\- scikit-learn

