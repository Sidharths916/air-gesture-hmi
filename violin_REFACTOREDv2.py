#!/usr/bin/env python3
"""
AR VIRTUAL VIOLIN  -  Final + Song Mode + Retry
════════════════════════════════════════════════════════
"""

import time
import threading
import wave
import tempfile
import os
import math
import json
from collections import deque

import cv2
import numpy as np
import mediapipe as mp

try:
    import pygame
    _PYGAME = True
except ImportError:
    _PYGAME = False

try:
    from scipy.signal import lfilter as _lfilter
    _SCIPY = True
except ImportError:
    _SCIPY = False

# ═══════════════════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════════════════

SR = 22050
OPEN_HZ   = [196.00, 293.66, 440.00, 659.25]   # G3 D4 A4 E5
STR_NAMES = ["G", "D", "A", "E"]
NOTE_NAMES = {
    0: ["G3","G#3","A3","A#3","B3","C4","C#4","D4"],
    1: ["D4","D#4","E4","F4","F#4","G4","G#4","A4"],
    2: ["A4","A#4","B4","C5","C#5","D5","D#5","E5"],
    3: ["E5","F5","F#5","G5","G#5","A5","A#5","B5"],
}

def _bpf(x, freq, q=7.0):
    w0 = 2 * np.pi * freq / SR
    alpha = np.sin(w0) / (2 * q)
    b0, b2 = alpha, -alpha
    a0 = 1 + alpha
    a1 = -2 * np.cos(w0)
    a2 = 1 - alpha
    b = np.array([b0/a0, 0.0, b2/a0])
    a = np.array([1.0, a1/a0, a2/a0])
    if _SCIPY:
        return _lfilter(b, a, x).astype(np.float32)
    y = np.zeros_like(x)
    z1 = z2 = 0.0
    for i, xi in enumerate(x):
        yi = b[0]*xi + z1
        z1 = b[1]*xi - a[1]*yi + z2
        z2 = b[2]*xi - a[2]*yi
        y[i] = yi
    return y

def _make_sustain_loop(freq: float, loop_dur: float = 0.25) -> np.ndarray:
    n = int(SR * loop_dur)
    t = np.linspace(0.0, loop_dur, n, endpoint=False).astype(np.float32)
    rng = np.random.default_rng(int(freq * 100) % (2**32 - 1))
    vib_hz = 6.0
    n_vib = round(vib_hz * loop_dur)
    vib_hz = n_vib / loop_dur
    vib = 1.0 + 0.007 * np.sin(2.0 * np.pi * vib_hz * t)
    phase_inc = 2.0 * np.pi * freq / SR
    phase = phase_inc * np.arange(n, dtype=np.float32)
    sig = np.zeros(n, dtype=np.float32)
    for k in range(1, 16):
        sig += (1.0 / k) * np.sin(k * phase * (1 + 0.0004 * k * k)) * vib
    sig += 0.028 * rng.standard_normal(n).astype(np.float32)
    sig = np.tanh(1.35 * sig)
    body = (0.28 * _bpf(sig, 280.) +
            0.22 * _bpf(sig, 450.) +
            0.16 * _bpf(sig, 720.))
    sig = 0.72 * sig + 0.28 * body
    pk = float(np.max(np.abs(sig)))
    if pk > 0: sig = sig / pk * 0.82
    mono = (sig * 32767).astype(np.int16)
    return np.column_stack([mono, mono])

def _make_attack(freq: float, dur: float = 0.12) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, endpoint=False).astype(np.float32)
    rng = np.random.default_rng(int(freq * 7) % (2**32 - 1))
    phase = 2.0 * np.pi * freq * t
    sig = np.zeros(n, dtype=np.float32)
    for k in range(1, 10):
        sig += (1.0 / k) * np.sin(k * phase * (1 + 0.0004 * k * k))
    sig += 0.04 * rng.standard_normal(n).astype(np.float32)
    sig = np.tanh(1.2 * sig)
    env = np.ones(n, dtype=np.float32)
    env[:n] = np.linspace(0, 1, n) ** 0.5
    sig *= env
    pk = float(np.max(np.abs(sig)))
    if pk > 0: sig = sig / pk * 0.85
    mono = (sig * 32767).astype(np.int16)
    return np.column_stack([mono, mono])

def _play_wav_bg(path):
    def _go():
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        except:
            pass
        for cmd in [f'aplay -q "{path}"', f'afplay "{path}"']:
            if os.system(cmd + ' &') == 0: return
    threading.Thread(target=_go, daemon=True).start()

class ViolinAudio:
    def __init__(self):
        self.ready = False
        self._pygame = False
        self._sustain = {}
        self._attack = {}
        self._wav = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._init, daemon=True).start()
    def _init(self):
        if _PYGAME:
            try:
                pygame.mixer.pre_init(SR, -16, 2, 512)
                pygame.init()
                pygame.mixer.init(SR, -16, 2, 512)
                pygame.mixer.set_num_channels(12)
                self._pygame = True
                print("Audio: pygame OK")
            except Exception as e:
                print(f"Audio: pygame failed ({e}), winsound fallback")
        for si, base in enumerate(OPEN_HZ):
            for fi in range(8):
                freq = base * (2.0 ** (fi / 12.0))
                key = (si, fi)
                if self._pygame:
                    sus = pygame.sndarray.make_sound(_make_sustain_loop(freq))
                    atk = pygame.sndarray.make_sound(_make_attack(freq))
                    with self._lock:
                        self._sustain[key] = sus
                        self._attack[key] = atk
                else:
                    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                    mono = _make_sustain_loop(freq, 0.8)[:,0]
                    with wave.open(tmp.name, 'w') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(SR)
                        wf.writeframes(mono.tobytes())
                    with self._lock:
                        self._wav[key] = tmp.name
        self.ready = True
        print(f"Audio: {4*8} notes ready")
    def get_sounds(self, si, fi):
        key = (int(si), int(np.clip(fi, 0, 7)))
        with self._lock:
            return self._sustain.get(key), self._attack.get(key)
    def get_wav(self, si, fi):
        key = (int(si), int(np.clip(fi, 0, 7)))
        with self._lock:
            return self._wav.get(key)

# ═══════════════════════════════════════════════════════
# VIOLIN GEOMETRY
# ═══════════════════════════════════════════════════════

class ViolinGeometry:
    def __init__(self):
        self.shoulder = self.wrist = self.axis = self.perp = None
        self.arm_len = self.spacing = 0.0
        self.offsets = []
        self.ready = False
        self._sh_buf = deque(maxlen=8)
        self._wr_buf = deque(maxlen=8)
        self.fixed_arm_len = None
    def update(self, shoulder: np.ndarray, wrist: np.ndarray):
        self._sh_buf.append(shoulder)
        self._wr_buf.append(wrist)
        sh = np.mean(self._sh_buf, axis=0).astype(np.float32)
        wr = np.mean(self._wr_buf, axis=0).astype(np.float32)
        d = wr - sh
        ln = float(np.linalg.norm(d))
        if ln < 20: return
        self.shoulder = sh
        self.wrist = wr
        self.arm_len = ln
        if self.fixed_arm_len is None:
            self.fixed_arm_len = ln
        self.axis = (d / ln).astype(np.float32)
        self.perp = np.array([-self.axis[1], self.axis[0]], np.float32)
        self.spacing = ln * 0.020
        self.offsets = [(i - 1.5) * self.spacing for i in range(4)]
        self.ready = True
    def get_fret(self, fp: np.ndarray) -> int:
        if not self.ready: return 0
        along = float(np.dot(fp - self.shoulder, self.axis))
        return int(np.clip((1.0 - along / max(self.arm_len, 1)) * 10, 0, 7))
    def string_from_y(self, bow_y_px: float, shoulder_y_px: float, h: int) -> int:
        ref_top = shoulder_y_px - h * 0.04
        ref_bot = shoulder_y_px + h * 0.35
        span = max(ref_bot - ref_top, 1.0)
        t = (bow_y_px - ref_top) / span
        return int(np.clip(t * 4, 0, 3))
    def string_endpoints(self):
        if not self.ready: return []
        return [(self.shoulder + self.perp * o, self.wrist + self.perp * o) for o in self.offsets]

# ═══════════════════════════════════════════════════════
# BOW TRACKER
# ═══════════════════════════════════════════════════════

class BowTracker:
    def __init__(self):
        self._x_buf = deque(maxlen=8)
        self._sp_buf = deque(maxlen=6)
        self.velocity = 0.0
        self.speed = 0.0
        self._active = False
        self.THRESH_ON = 2.5
        self.THRESH_OFF = 1.2
    def update(self, bow_x: float):
        self._x_buf.append(bow_x)
        if len(self._x_buf) >= 2:
            if len(self._x_buf) >= 4:
                raw = (self._x_buf[-1] - self._x_buf[-4]) / 3.0
            else:
                raw = self._x_buf[-1] - self._x_buf[-2]
            self.velocity = 0.55 * raw + 0.45 * self.velocity
        spd = abs(self.velocity)
        self._sp_buf.append(spd)
        self.speed = float(np.mean(self._sp_buf))
        if not self._active and self.speed > self.THRESH_ON:
            self._active = True
        elif self._active and self.speed < self.THRESH_OFF:
            self._active = False
        speed_norm = float(np.clip(self.speed / 25.0, 0.0, 1.0))
        direction = 1 if self.velocity >= 0 else -1
        return self._active, speed_norm, direction

# ═══════════════════════════════════════════════════════
# DRAWING
# ═══════════════════════════════════════════════════════

def draw_violin(frame, geom: ViolinGeometry, vibration, phase, active_str, fret):
    if not geom.ready: return
    sh = geom.shoulder
    ax = geom.axis
    pp = geom.perp
    aln = geom.fixed_arm_len
    ang = math.degrees(math.atan2(float(ax[1]), float(ax[0])))
    bs = aln * 0.40
    CB = (45, 80, 130)
    CB2 = (58, 95, 148)
    CW = (30, 55, 96)
    CN = (34, 62, 108)
    CE = (88, 140, 188)
    CF = (8, 14, 22)
    nw = int(bs * 0.13)
    bl = frame.copy()
    lo = sh + ax * bs * 0.36
    hi = sh + ax * bs * 0.14
    wc = sh + ax * bs * 0.25
    cv2.ellipse(bl, (int(lo[0]), int(lo[1])), (int(bs*0.60), int(bs*0.40)), ang, 0, 360, CB, -1)
    cv2.ellipse(bl, (int(hi[0]), int(hi[1])), (int(bs*0.44), int(bs*0.30)), ang, 0, 360, CB2, -1)
    cv2.ellipse(bl, (int(wc[0]), int(wc[1])), (int(bs*0.21), int(bs*0.13)), ang, 0, 360, CW, -1)
    cv2.addWeighted(bl, 0.82, frame, 0.18, 0, frame)
    cv2.ellipse(frame, (int(lo[0]), int(lo[1])), (int(bs*0.60), int(bs*0.40)), ang, 0, 360, CE, 2)
    cv2.ellipse(frame, (int(hi[0]), int(hi[1])), (int(bs*0.44), int(bs*0.30)), ang, 0, 360, CE, 2)
    cv2.ellipse(frame, (int(wc[0]), int(wc[1])), (int(bs*0.21), int(bs*0.13)), ang, 0, 360, CE, 1)
    cv2.ellipse(frame, (int(lo[0]), int(lo[1])), (int(bs*0.56), int(bs*0.36)), ang, 0, 360, CW, 1)
    for sd in (-1, 1):
        fc = wc + pp * sd * bs * 0.21
        up = fc - ax * bs * 0.065
        dn = fc + ax * bs * 0.075
        cv2.circle(frame, (int(up[0]), int(up[1])), max(2, int(bs*0.022)), CF, -1)
        cv2.circle(frame, (int(dn[0]), int(dn[1])), max(2, int(bs*0.020)), CF, -1)
        cv2.line(frame, (int(up[0]), int(up[1])), (int(dn[0]), int(dn[1])), CF, 2)
    tail = sh - ax * bs * 0.05
    cv2.line(frame, (int((tail + pp * bs * 0.07)[0]), int((tail + pp * bs * 0.07)[1])),
                   (int((tail - pp * bs * 0.07)[0]), int((tail - pp * bs * 0.07)[1])), CF, 3)
    nk = np.array([sh + pp * nw, sh - pp * nw,
                   geom.wrist - pp * (nw * 0.55), geom.wrist + pp * (nw * 0.55)], np.int32)
    nl = frame.copy()
    cv2.fillPoly(nl, [nk], CN)
    cv2.addWeighted(nl, 0.82, frame, 0.18, 0, frame)
    cv2.polylines(frame, [nk], True, CE, 2)
    fw = int(nw * 0.62)
    fb = np.array([sh + pp * fw, sh - pp * fw,
                   geom.wrist - pp * (fw * 0.50), geom.wrist + pp * (fw * 0.50)], np.int32)
    fbl = frame.copy()
    cv2.fillPoly(fbl, [fb], CF)
    cv2.addWeighted(fbl, 0.72, frame, 0.28, 0, frame)
    cv2.line(frame, (int((geom.wrist + pp * nw)[0]), int((geom.wrist + pp * nw)[1])),
                   (int((geom.wrist - pp * nw)[0]), int((geom.wrist - pp * nw)[1])), CE, 3)
    scr = geom.wrist + ax * bs * 0.11
    sr = max(4, int(bs * 0.085))
    cv2.circle(frame, (int(scr[0]), int(scr[1])), sr, CN, -1)
    cv2.circle(frame, (int(scr[0]), int(scr[1])), sr, CE, 2)
    cv2.circle(frame, (int(scr[0]), int(scr[1])), sr // 2, CE, -1)
    br = sh + ax * bs * 0.03
    bw = bs * 0.11
    cv2.line(frame, (int((br + pp * bw)[0]), int((br + pp * bw)[1])),
                   (int((br - pp * bw)[0]), int((br - pp * bw)[1])), (180, 155, 80), 3)
    for sd in (-1, 1):
        ft = br + pp * sd * bw * 0.6
        cv2.line(frame, (int(ft[0]), int(ft[1])),
                       (int((ft + ax * bs * 0.025)[0]), int((ft + ax * bs * 0.025)[1])), (180, 155, 80), 2)
    for i, (s, e) in enumerate(geom.string_endpoints()):
        ac = (i == active_str)
        vib = vibration[i]
        col = (0, 255, 180) if ac else (200, 200, 200)
        thick = 3 if ac else 1
        if vib > 0.2:
            pts = []
            for u in np.linspace(0, 1, 16):
                p = s + (e - s) * u
                p = p + geom.perp * vib * np.sin(phase[i] + u * 4 * np.pi) * 6
                pts.append((int(p[0]), int(p[1])))
            cv2.polylines(frame, [np.array(pts)], False, col, thick)
        else:
            cv2.line(frame, (int(s[0]), int(s[1])), (int(e[0]), int(e[1])), col, thick)
    if fret > 0 and geom.ready:
        t = 1.0 - fret / 10.0
        fp = geom.shoulder + geom.axis * geom.arm_len * t + geom.perp * geom.offsets[active_str]
        cv2.circle(frame, (int(fp[0]), int(fp[1])), 9, (0, 255, 180), -1)
        cv2.circle(frame, (int(fp[0]), int(fp[1])), 9, (255, 255, 255), 2)

def draw_bow(frame, grip, wrist, bow_speed, geom: ViolinGeometry):
    bv = grip - wrist
    ln = float(np.linalg.norm(bv))
    if ln < 5: return
    u = bv / ln
    pp = np.array([-u[1], u[0]], np.float32)
    bl = geom.fixed_arm_len * 0.68 if geom.ready else 300.0
    frog = grip - u * bl * 0.10
    tip = grip + u * bl * 0.90
    active = bow_speed > 0.05
    sc = (0, 210, 90) if active else (35, 65, 115)
    hc = (255, 255, 210) if active else (185, 185, 160)
    th = 7 if active else 5
    cv2.line(frame, (int(frog[0]), int(frog[1])), (int(tip[0]), int(tip[1])), sc, th)
    hs = frog + pp * 10
    he = tip + pp * 4
    cv2.line(frame, (int(hs[0]), int(hs[1])), (int(he[0]), int(he[1])), hc, 2)
    cv2.line(frame, (int(frog[0]), int(frog[1])), (int(hs[0]), int(hs[1])), sc, 2)
    cv2.line(frame, (int(tip[0]), int(tip[1])), (int(he[0]), int(he[1])), sc, 2)
    fp = np.array([frog + pp * 13, frog - pp * 13, frog - pp * 13 + u * 26, frog + pp * 13 + u * 26], np.int32)
    fl = frame.copy()
    cv2.fillPoly(fl, [fp], (85, 85, 85))
    cv2.addWeighted(fl, 0.75, frame, 0.25, 0, frame)
    cv2.polylines(frame, [fp], True, sc, 2)
    tp = np.array([tip + pp * 7, tip - pp * 7, tip - pp * 7 + u * 13, tip + pp * 7 + u * 13], np.int32)
    cv2.fillPoly(frame, [tp], sc)
    if active:
        mid = grip + u * bl * 0.28
        cv2.circle(frame, (int(mid[0]), int(mid[1])), 12, (0, 255, 180), -1)
        cv2.circle(frame, (int(mid[0]), int(mid[1])), 7, (255, 255, 255), 2)

# ═══════════════════════════════════════════════════════
# SONG ENGINE (violin version)
# ═══════════════════════════════════════════════════════

class ViolinSongEngine:
    def __init__(self, song_data, audio, geom, w, h):
        self.song = song_data
        self.bpm = song_data.get('bpm', 120)
        self.beat_duration = 60.0 / self.bpm
        self.notes = song_data['tracks'][0]['notes']
        self.start_time = None
        self.score = 0
        self.combo = 0
        self.missed = 0
        self.perfect = 0
        self.good = 0
        self.audio = audio
        self.geom = geom
        self.w = w
        self.h = h
        self.falling_notes = []
        self.note_width = 80
        self.note_height = 30
        self.note_map = self._build_note_map()
    def _build_note_map(self):
        mapping = {}
        for si, notes in NOTE_NAMES.items():
            for fi, note in enumerate(notes):
                mapping[note] = (si, fi)
        return mapping
    def start(self):
        self.start_time = time.time()
        self.score = 0
        self.combo = 0
        self.missed = 0
        self.perfect = 0
        self.good = 0
        self.falling_notes = []
        for note in self.notes:
            self.falling_notes.append({
                'note': note['note'],
                'start_beat': note['start_beat'],
                'dead': False,
                'hit': False
            })
    def update(self, current_time, played_string, played_fret):
        if self.start_time is None:
            return self.score, self.combo, self.perfect, self.good, self.missed
        elapsed = current_time - self.start_time
        hit_window = 0.1
        for fn in self.falling_notes[:]:
            if fn['dead']:
                continue
            note_time = fn['start_beat'] * self.beat_duration
            if elapsed >= note_time - hit_window and not fn.get('hit', False):
                fn['dead'] = True
                expected = self.note_map.get(fn['note'])
                if expected and (played_string, played_fret) == expected:
                    self.score += 10
                    self.combo += 1
                    diff = abs(elapsed - note_time)
                    if diff < 0.05:
                        self.perfect += 1
                    else:
                        self.good += 1
                else:
                    self.missed += 1
                    self.combo = 0
        self.falling_notes = [fn for fn in self.falling_notes if not fn.get('dead', False)]
        return self.score, self.combo, self.perfect, self.good, self.missed
    def draw(self, frame):
        for fn in self.falling_notes:
            y = int((fn['start_beat'] * self.beat_duration - (time.time() - self.start_time)) * 150) + 50
            if 0 < y < self.h - 100:
                cv2.rectangle(frame, (20, y), (20 + self.note_width, y + self.note_height), (0, 200, 255), -1)
                cv2.rectangle(frame, (20, y), (20 + self.note_width, y + self.note_height), (255, 255, 255), 2)
                cv2.putText(frame, fn['note'], (25, y + self.note_height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        cv2.rectangle(frame, (10, 10), (250, 120), (0, 0, 0), -1)
        cv2.putText(frame, f"SCORE: {self.score}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"COMBO: {self.combo}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame, f"PERFECT: {self.perfect}  GOOD: {self.good}  MISS: {self.missed}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        return frame

# ═══════════════════════════════════════════════════════
# FREE-PLAY MAIN
# ═══════════════════════════════════════════════════════

def main():
    print("AR Violin starting...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found.")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mp_pose = mp.solutions.pose
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils

    pose = mp_pose.Pose(min_detection_confidence=0.65, min_tracking_confidence=0.60)
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.65, min_tracking_confidence=0.60)

    audio = ViolinAudio()
    geom = ViolinGeometry()
    bow_t = BowTracker()

    vibration = [0.0] * 4
    phase = [0.0] * 4
    active_str = 2
    active_fret = 0
    flash_until = 0.0
    last_note = "A4"
    dir_sym = ""

    _sus_ch = None
    _sus_key = None
    _was_bowing = False

    print("Left arm = violin | Bow hand = sweep left/right | Fret hand = press neck | ESC = exit\n")

    while True:
        ok, frame = cap.read()
        if not ok: break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        pose_res = pose.process(rgb)
        hands_res = hands.process(rgb)

        l_shoulder_found = False
        shoulder_y_px = h * 0.35
        if pose_res.pose_landmarks:
            lm = pose_res.pose_landmarks.landmark
            mp_draw.draw_landmarks(frame, pose_res.pose_landmarks,
                                   mp_pose.POSE_CONNECTIONS,
                                   mp_draw.DrawingSpec((55,55,55),1,1),
                                   mp_draw.DrawingSpec((35,35,35),1,1))
            sh = np.array([lm[12].x * w, lm[12].y * h], np.float32)
            wr = np.array([lm[16].x * w, lm[16].y * h], np.float32)
            shoulder_y_px = float(lm[12].y * h)
            geom.update(sh, wr)
            l_shoulder_found = True

        bow_grip = bow_wrist = fret_tip = None
        bow_y_px = shoulder_y_px + h * 0.15

        if hands_res.multi_hand_landmarks and hands_res.multi_handedness:
            for i, hlm in enumerate(hands_res.multi_hand_landmarks):
                mp_draw.draw_landmarks(frame, hlm, mp_hands.HAND_CONNECTIONS)
                label = hands_res.multi_handedness[i].classification[0].label
                wpt = np.array([hlm.landmark[0].x * w, hlm.landmark[0].y * h], np.float32)
                itip = np.array([hlm.landmark[8].x * w, hlm.landmark[8].y * h], np.float32)
                ttip = np.array([hlm.landmark[4].x * w, hlm.landmark[4].y * h], np.float32)
                if label == 'Right':
                    bow_grip = (itip + ttip) * 0.5
                    bow_wrist = wpt
                    bow_y_px = float(hlm.landmark[0].y * h)
                else:
                    fret_tip = itip

        if fret_tip is not None and geom.ready:
            active_fret = geom.get_fret(fret_tip)
            cv2.circle(frame, (int(fret_tip[0]), int(fret_tip[1])), 14, (0,255,80), 2)

        if bow_grip is not None:
            active_str = geom.string_from_y(bow_y_px, shoulder_y_px, h)

        is_bowing = False
        bow_speed = 0.0
        bow_dir = 1
        if bow_grip is not None:
            bx_world = float(bow_grip[0])
            is_bowing, bow_speed, bow_dir = bow_t.update(bx_world)
            if is_bowing:
                dir_sym = ">>" if bow_dir > 0 else "<<"
                vibration[active_str] = min(2.0, 0.6 + bow_speed * 1.4)

        if audio.ready and _PYGAME:
            cur_key = (active_str, active_fret)
            if is_bowing:
                vol = float(np.clip(0.15 + bow_speed * 0.85, 0.05, 1.0))
                if not _was_bowing or _sus_key != cur_key:
                    try:
                        if _sus_ch is not None:
                            _sus_ch.stop()
                        sus, atk = audio.get_sounds(*cur_key)
                        if atk:
                            atk_ch = pygame.mixer.Channel(6)
                            atk_ch.set_volume(vol)
                            atk_ch.play(atk)
                        if sus:
                            _sus_ch = pygame.mixer.Channel(7)
                            _sus_ch.set_volume(vol * 0.70)
                            _sus_ch.play(sus, loops=-1)
                    except:
                        pass
                    _sus_key = cur_key
                else:
                    try:
                        if _sus_ch is not None:
                            _sus_ch.set_volume(vol * 0.70)
                    except:
                        pass
                last_note = NOTE_NAMES[active_str][active_fret]
                flash_until = time.time() + 0.30
            else:
                if _was_bowing:
                    try:
                        if _sus_ch is not None:
                            _sus_ch.fadeout(200)
                    except:
                        pass
                    _sus_ch = None
                    _sus_key = None
            _was_bowing = is_bowing
        elif audio.ready and not _PYGAME and is_bowing:
            path = audio.get_wav(active_str, active_fret)
            if path:
                _play_wav_bg(path)
            last_note = NOTE_NAMES[active_str][active_fret]
            flash_until = time.time() + 0.30

        for i in range(4):
            vibration[i] *= 0.91
            phase[i] += 0.45

        if geom.ready:
            draw_violin(frame, geom, vibration, phase, active_str, active_fret)
        if bow_grip is not None and bow_wrist is not None:
            draw_bow(frame, bow_grip, bow_wrist, bow_speed, geom)

        zone_span = h * 0.35
        zone_start = shoulder_y_px - h * 0.04
        zone_h_px = zone_span / 4
        for i, sn in enumerate(STR_NAMES):
            y0 = int(zone_start + i * zone_h_px)
            y1 = int(y0 + zone_h_px)
            y0 = max(0, y0)
            y1 = min(h, y1)
            ac = (i == active_str and bow_grip is not None)
            ov = frame.copy()
            cv2.rectangle(ov, (w-28, y0), (w, y1), (0,255,180) if ac else (40,40,40), -1)
            cv2.addWeighted(ov, 0.35 if ac else 0.15, frame, 1.0 - (0.35 if ac else 0.15), 0, frame)
            cv2.rectangle(frame, (w-28, y0), (w, y1), (0,255,180) if ac else (70,70,70), 1)
            cv2.putText(frame, sn, (w-22, y0 + (y1 - y0) // 2 + 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (0,255,180) if ac else (110,110,110), 2)

        cv2.rectangle(frame, (0,0), (w,96), (10,10,10), -1)
        cv2.rectangle(frame, (0,94), (w,96), (0,170,120), -1)
        cv2.putText(frame, "AR VIOLIN (FREE)", (18,40), cv2.FONT_HERSHEY_DUPLEX, 1.3, (0,220,150), 3)

        if not l_shoulder_found:
            status = "Show your body to camera"
        elif not geom.ready:
            status = "Raise left arm (violin position)"
        elif bow_grip is None:
            status = "Raise bow hand (right)"
        elif not audio.ready:
            status = "Tuning strings..."
        else:
            status = "Bow left/right to play | Raise/lower bow for string"
        cv2.putText(frame, status, (18,72), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (185,185,185), 2)

        nc = (0,255,180) if time.time() < flash_until else (80,80,80)
        cv2.putText(frame, last_note, (w//2-55, h//2+20), cv2.FONT_HERSHEY_DUPLEX, 2.5, nc, 4)
        if time.time() < flash_until and dir_sym:
            cv2.putText(frame, dir_sym, (w//2+80, h//2+20), cv2.FONT_HERSHEY_DUPLEX, 1.8, (50,255,120), 3)

        if bow_grip is not None:
            bw = int(bow_speed * (w//2 - 20))
            col = (0,210,90) if is_bowing else (60,60,60)
            cx = w//2
            cv2.rectangle(frame, (cx-bw, h-28), (cx+bw, h-10), col, -1)
            cv2.line(frame, (cx, h-34), (cx, h-4), (80,80,80), 1)
            cv2.putText(frame, "BOW SPEED", (cx-45, h-32), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100,100,100), 1)

        px = 14
        cv2.putText(frame, "STRINGS", (px,132), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (150,150,150), 1)
        for i, s in enumerate(STR_NAMES):
            sy = 155 + i * 42
            ac = (i == active_str)
            cv2.line(frame, (px, sy), (px+80, sy), (0,255,180) if ac else (65,65,65), 3 if ac else 1)
            cv2.putText(frame, s, (px-1, sy+7), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (0,255,180) if ac else (100,100,100), 2)

        fx = w-140
        bh = 140
        by = 150
        cv2.putText(frame, "FRET", (fx,132), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (150,150,150), 1)
        cv2.rectangle(frame, (fx, by), (fx+18, by+bh), (42,42,42), 1)
        fill = int(bh * active_fret / 7)
        cv2.rectangle(frame, (fx+1, by+bh-fill), (fx+17, by+bh-1), (0,255,180), -1)
        cv2.putText(frame, str(active_fret), (fx-5, by+bh+22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140,140,140), 1)

        for i, txt in enumerate(["Left arm = neck",
                                 "Bow hand sweeps left/right | height = string",
                                 "Fret hand moves along neck = pitch",
                                 "C = recalibrate violin size | ESC = exit"]):
            cv2.putText(frame, txt, (18, h-76+i*19), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (85,85,85), 1)

        cv2.imshow("AR Violin", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif key == ord('c') or key == ord('C'):
            geom.fixed_arm_len = None
            print("Recalibrating violin size...")

    try:
        if _sus_ch is not None:
            _sus_ch.stop()
    except:
        pass
    cap.release()
    cv2.destroyAllWindows()
    try: pose.close(); hands.close()
    except: pass
    print("Violin closed.")

# ═══════════════════════════════════════════════════════
# SONG MODE (with retry)
# ═══════════════════════════════════════════════════════

def run_song_mode(song_path):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found.")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mp_pose = mp.solutions.pose
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils

    pose = mp_pose.Pose(min_detection_confidence=0.65, min_tracking_confidence=0.60)
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.65, min_tracking_confidence=0.60)

    with open(song_path, 'r') as f:
        song_data = json.load(f)

    audio = ViolinAudio()
    geom = ViolinGeometry()
    bow_t = BowTracker()
    song_engine = ViolinSongEngine(song_data, audio, geom, 1280, 720)
    song_engine.start()

    vibration = [0.0] * 4
    phase = [0.0] * 4
    active_str = 2
    active_fret = 0
    flash_until = 0.0
    last_note = "A4"
    dir_sym = ""

    _sus_ch = None
    _sus_key = None
    _was_bowing = False

    # Retry gesture
    fist_start_time = None
    retry_hold_duration = 1.0

    def detect_fist(landmarks):
        if not landmarks: return False
        thumb_tip = landmarks[4]
        index_tip = landmarks[8]
        middle_tip = landmarks[12]
        ring_tip = landmarks[16]
        pinky_tip = landmarks[20]
        index_up = index_tip.y < landmarks[6].y - 0.03
        middle_up = middle_tip.y < landmarks[10].y - 0.03
        ring_up = ring_tip.y < landmarks[14].y - 0.03
        pinky_up = pinky_tip.y < landmarks[18].y - 0.03
        thumb_extended = abs(thumb_tip.x - landmarks[2].x) > 0.05
        return not index_up and not middle_up and not ring_up and not pinky_up and not thumb_extended

    print(f"Playing song: {song_data['title']} | Bow notes in time | Hold FIST 1s to restart | ESC = exit")

    while True:
        ok, frame = cap.read()
        if not ok: break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Detect fist for retry on ANY hand
        hands_res = hands.process(rgb)
        if hands_res.multi_hand_landmarks:
            for hlm in hands_res.multi_hand_landmarks:
                if detect_fist(hlm.landmark):
                    if fist_start_time is None:
                        fist_start_time = time.time()
                    elif time.time() - fist_start_time >= retry_hold_duration:
                        song_engine.start()
                        print("Song restarted!")
                        fist_start_time = None
                        flash_until = 0
                    break
            else:
                fist_start_time = None
        else:
            fist_start_time = None

        pose_res = pose.process(rgb)

        l_shoulder_found = False
        shoulder_y_px = h * 0.35
        if pose_res.pose_landmarks:
            lm = pose_res.pose_landmarks.landmark
            mp_draw.draw_landmarks(frame, pose_res.pose_landmarks,
                                   mp_pose.POSE_CONNECTIONS,
                                   mp_draw.DrawingSpec((55,55,55),1,1),
                                   mp_draw.DrawingSpec((35,35,35),1,1))
            sh = np.array([lm[12].x * w, lm[12].y * h], np.float32)
            wr = np.array([lm[16].x * w, lm[16].y * h], np.float32)
            shoulder_y_px = float(lm[12].y * h)
            geom.update(sh, wr)
            l_shoulder_found = True

        bow_grip = bow_wrist = fret_tip = None
        bow_y_px = shoulder_y_px + h * 0.15

        if hands_res.multi_hand_landmarks and hands_res.multi_handedness:
            for i, hlm in enumerate(hands_res.multi_hand_landmarks):
                mp_draw.draw_landmarks(frame, hlm, mp_hands.HAND_CONNECTIONS)
                label = hands_res.multi_handedness[i].classification[0].label
                wpt = np.array([hlm.landmark[0].x * w, hlm.landmark[0].y * h], np.float32)
                itip = np.array([hlm.landmark[8].x * w, hlm.landmark[8].y * h], np.float32)
                ttip = np.array([hlm.landmark[4].x * w, hlm.landmark[4].y * h], np.float32)
                if label == 'Right':
                    bow_grip = (itip + ttip) * 0.5
                    bow_wrist = wpt
                    bow_y_px = float(hlm.landmark[0].y * h)
                else:
                    fret_tip = itip

        if fret_tip is not None and geom.ready:
            active_fret = geom.get_fret(fret_tip)
            cv2.circle(frame, (int(fret_tip[0]), int(fret_tip[1])), 14, (0,255,80), 2)

        if bow_grip is not None:
            active_str = geom.string_from_y(bow_y_px, shoulder_y_px, h)

        is_bowing = False
        bow_speed = 0.0
        bow_dir = 1
        played_string = None
        if bow_grip is not None:
            bx_world = float(bow_grip[0])
            is_bowing, bow_speed, bow_dir = bow_t.update(bx_world)
            if is_bowing:
                played_string = active_str
                dir_sym = ">>" if bow_dir > 0 else "<<"
                vibration[active_str] = min(2.0, 0.6 + bow_speed * 1.4)

        # Audio playback (same as free-play)
        if audio.ready and _PYGAME:
            cur_key = (active_str, active_fret)
            if is_bowing:
                vol = float(np.clip(0.15 + bow_speed * 0.85, 0.05, 1.0))
                if not _was_bowing or _sus_key != cur_key:
                    try:
                        if _sus_ch is not None:
                            _sus_ch.stop()
                        sus, atk = audio.get_sounds(*cur_key)
                        if atk:
                            atk_ch = pygame.mixer.Channel(6)
                            atk_ch.set_volume(vol)
                            atk_ch.play(atk)
                        if sus:
                            _sus_ch = pygame.mixer.Channel(7)
                            _sus_ch.set_volume(vol * 0.70)
                            _sus_ch.play(sus, loops=-1)
                    except:
                        pass
                    _sus_key = cur_key
                else:
                    try:
                        if _sus_ch is not None:
                            _sus_ch.set_volume(vol * 0.70)
                    except:
                        pass
                last_note = NOTE_NAMES[active_str][active_fret]
                flash_until = time.time() + 0.30
            else:
                if _was_bowing:
                    try:
                        if _sus_ch is not None:
                            _sus_ch.fadeout(200)
                    except:
                        pass
                    _sus_ch = None
                    _sus_key = None
            _was_bowing = is_bowing
        elif audio.ready and not _PYGAME and is_bowing:
            path = audio.get_wav(active_str, active_fret)
            if path:
                _play_wav_bg(path)
            last_note = NOTE_NAMES[active_str][active_fret]
            flash_until = time.time() + 0.30

        # Update song engine with played note
        score, combo, perfect, good, missed = song_engine.update(time.time(),
                                                                 played_string if played_string is not None else -1,
                                                                 active_fret)
        frame = song_engine.draw(frame)

        for i in range(4):
            vibration[i] *= 0.91
            phase[i] += 0.45

        if geom.ready:
            draw_violin(frame, geom, vibration, phase, active_str, active_fret)
        if bow_grip is not None and bow_wrist is not None:
            draw_bow(frame, bow_grip, bow_wrist, bow_speed, geom)

        # String zones (right edge)
        zone_span = h * 0.35
        zone_start = shoulder_y_px - h * 0.04
        zone_h_px = zone_span / 4
        for i, sn in enumerate(STR_NAMES):
            y0 = int(zone_start + i * zone_h_px)
            y1 = int(y0 + zone_h_px)
            y0 = max(0, y0)
            y1 = min(h, y1)
            ac = (i == active_str and bow_grip is not None)
            ov = frame.copy()
            cv2.rectangle(ov, (w-28, y0), (w, y1), (0,255,180) if ac else (40,40,40), -1)
            cv2.addWeighted(ov, 0.35 if ac else 0.15, frame, 1.0 - (0.35 if ac else 0.15), 0, frame)
            cv2.rectangle(frame, (w-28, y0), (w, y1), (0,255,180) if ac else (70,70,70), 1)
            cv2.putText(frame, sn, (w-22, y0 + (y1 - y0) // 2 + 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (0,255,180) if ac else (110,110,110), 2)

        cv2.rectangle(frame, (0,0), (w,96), (10,10,10), -1)
        cv2.rectangle(frame, (0,94), (w,96), (0,170,120), -1)
        cv2.putText(frame, f"SONG: {song_data['title']}", (18,40), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0,220,150), 2)

        if not l_shoulder_found:
            status = "Show your body to camera"
        elif not geom.ready:
            status = "Raise left arm (violin position)"
        elif bow_grip is None:
            status = "Raise bow hand (right)"
        elif not audio.ready:
            status = "Tuning strings..."
        else:
            status = "Bow left/right to play | Raise/lower bow for string"
        cv2.putText(frame, status, (18,72), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (185,185,185), 2)

        nc = (0,255,180) if time.time() < flash_until else (80,80,80)
        cv2.putText(frame, last_note, (w//2-55, h//2+20), cv2.FONT_HERSHEY_DUPLEX, 2.5, nc, 4)
        if time.time() < flash_until and dir_sym:
            cv2.putText(frame, dir_sym, (w//2+80, h//2+20), cv2.FONT_HERSHEY_DUPLEX, 1.8, (50,255,120), 3)

        if bow_grip is not None:
            bw = int(bow_speed * (w//2 - 20))
            col = (0,210,90) if is_bowing else (60,60,60)
            cx = w//2
            cv2.rectangle(frame, (cx-bw, h-28), (cx+bw, h-10), col, -1)
            cv2.line(frame, (cx, h-34), (cx, h-4), (80,80,80), 1)
            cv2.putText(frame, "BOW SPEED", (cx-45, h-32), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100,100,100), 1)

        px = 14
        cv2.putText(frame, "STRINGS", (px,132), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (150,150,150), 1)
        for i, s in enumerate(STR_NAMES):
            sy = 155 + i * 42
            ac = (i == active_str)
            cv2.line(frame, (px, sy), (px+80, sy), (0,255,180) if ac else (65,65,65), 3 if ac else 1)
            cv2.putText(frame, s, (px-1, sy+7), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (0,255,180) if ac else (100,100,100), 2)

        fx = w-140
        bh = 140
        by = 150
        cv2.putText(frame, "FRET", (fx,132), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (150,150,150), 1)
        cv2.rectangle(frame, (fx, by), (fx+18, by+bh), (42,42,42), 1)
        fill = int(bh * active_fret / 7)
        cv2.rectangle(frame, (fx+1, by+bh-fill), (fx+17, by+bh-1), (0,255,180), -1)
        cv2.putText(frame, str(active_fret), (fx-5, by+bh+22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140,140,140), 1)

        # Retry hint
        if fist_start_time is not None:
            elapsed = time.time() - fist_start_time
            if elapsed < retry_hold_duration:
                remaining = retry_hold_duration - elapsed
                cv2.putText(frame, f"Hold FIST {remaining:.1f}s to restart", (20, h-30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,200,255), 2)

        for i, txt in enumerate(["Left arm = neck",
                                 "Bow hand sweeps left/right | height = string",
                                 "Fret hand moves along neck = pitch",
                                 "C = recalibrate violin size | ESC = exit"]):
            cv2.putText(frame, txt, (18, h-76+i*19), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (85,85,85), 1)

        cv2.imshow("AR Violin - Song Mode", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif key == ord('c') or key == ord('C'):
            geom.fixed_arm_len = None
            print("Recalibrating violin size...")

    try:
        if _sus_ch is not None:
            _sus_ch.stop()
    except:
        pass
    cap.release()
    cv2.destroyAllWindows()
    try: pose.close(); hands.close()
    except: pass
    print("Song mode finished.")

def run_violin():
    main()

if __name__ == "__main__":
    main()