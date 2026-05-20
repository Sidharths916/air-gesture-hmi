#!/usr/bin/env python3
"""
AR VIRTUAL PIANO  -  Final + Song Mode + Visual Metronome
══════════════════════════════════════════════════════════
"""

import time
import threading
import math
import json
import os
from collections import deque

import cv2
import numpy as np
import mediapipe as mp

try:
    import pygame
    _PYGAME = True
except ImportError:
    _PYGAME = False

# ═══════════════════════════════════════════════════════
# AUDIO (same as original)
# ═══════════════════════════════════════════════════════

SR = 22050

def _synth_piano(freq: float, duration: float = 1.4) -> np.ndarray:
    n = int(SR * duration)
    t = np.linspace(0.0, duration, n, endpoint=False).astype(np.float32)
    B = 0.0001
    sig = np.zeros(n, dtype=np.float32)
    for k in range(1, 13):
        f_k = freq * k * math.sqrt(1.0 + B * k * k)
        amp = (1.0 / k) * math.exp(-0.25 * (k - 1))
        sig += amp * np.sin(2.0 * np.pi * f_k * t)
    sig += 0.18 * np.sin(2.0 * np.pi * freq * 1.0012 * t)
    atk = int(0.008 * n); dcy = int(0.12 * n); rel = int(0.25 * n); sl = 0.55
    env = np.ones(n, dtype=np.float32) * sl
    if atk: env[:atk] = np.linspace(0, 1, atk)
    if dcy: env[atk:atk+dcy] = np.linspace(1, sl, dcy)
    if rel and rel < n: env[-rel:] = np.linspace(sl, 0, rel)
    sig *= env
    sig = np.tanh(1.1 * sig)
    pk = float(np.max(np.abs(sig)))
    if pk > 0: sig = sig / pk * 0.82
    mono = (sig * 32767).astype(np.int16)
    return np.column_stack([mono, mono])

WHITE_NOTES = ['C3','D3','E3','F3','G3','A3','B3',
               'C4','D4','E4','F4','G4','A4','B4',
               'C5','D5','E5','F5','G5','A5','B5']
BLACK_NOTES = {
    'C#3': (0,0.6), 'D#3': (1,0.6), 'F#3': (3,0.6), 'G#3': (4,0.6), 'A#3': (5,0.6),
    'C#4': (7,0.6), 'D#4': (8,0.6), 'F#4': (10,0.6), 'G#4': (11,0.6), 'A#4': (12,0.6),
    'C#5': (14,0.6), 'D#5': (15,0.6), 'F#5': (17,0.6), 'G#5': (18,0.6), 'A#5': (19,0.6),
}

NOTE_FREQS = {}
for i, note in enumerate(['C2','C#2','D2','D#2','E2','F2','F#2','G2','G#2','A2','A#2','B2',
                           'C3','C#3','D3','D#3','E3','F3','F#3','G3','G#3','A3','A#3','B3',
                           'C4','C#4','D4','D#4','E4','F4','F#4','G4','G#4','A4','A#4','B4',
                           'C5','C#5','D5','D#5','E5','F5','F#5','G5','G#5','A5','A#5','B5',
                           'C6']):
    midi = 36 + i
    NOTE_FREQS[note] = 440.0 * (2.0 ** ((midi - 69) / 12.0))

class PianoAudio:
    def __init__(self):
        self.ready = False
        self._cache = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._init, daemon=True).start()
    def _init(self):
        if not _PYGAME:
            print("Audio: pygame not available"); return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(SR, -16, 2, 512)
                pygame.mixer.init(SR, -16, 2, 512)
            pygame.mixer.set_num_channels(16)
        except Exception as e:
            print(f"Audio: {e}"); return
        all_notes = WHITE_NOTES + list(BLACK_NOTES.keys())
        for note in all_notes:
            freq = NOTE_FREQS.get(note, 440.0)
            snd = pygame.sndarray.make_sound(_synth_piano(freq))
            with self._lock:
                self._cache[note] = snd
        self.ready = True
        print(f"Audio: {len(self._cache)} piano notes ready")
    def play(self, note: str, vol: float = 0.85):
        if not self.ready or not _PYGAME: return
        with self._lock:
            snd = self._cache.get(note)
        if snd:
            try:
                ch = pygame.mixer.find_channel(True)
                if ch:
                    ch.set_volume(float(np.clip(vol, 0.1, 1.0)))
                    ch.play(snd)
            except Exception:
                pass

class TapDetector:
    def __init__(self):
        self._y_buf = deque(maxlen=5)
        self._on_note = None
        self._tapped = False
        self.VEL_THRESH = 3.5
        self.LIFT_THRESH = -1.5
    def update(self, y_px: float, note):
        self._y_buf.append(y_px)
        vel = 0.0
        if len(self._y_buf) >= 3:
            deltas = [self._y_buf[i] - self._y_buf[i-1] for i in range(-1, -3, -1)]
            vel = float(np.mean(deltas))
        if note != self._on_note:
            self._on_note = note
            self._tapped = False
        if note is None:
            self._tapped = False
            return None
        if not self._tapped and vel > self.VEL_THRESH:
            self._tapped = True
            return note
        if vel < self.LIFT_THRESH:
            self._tapped = False
        return None

class PianoLayout:
    def __init__(self, w: int, h: int):
        n_white = len(WHITE_NOTES)
        margin = 20
        total_w = w - 2 * margin
        self.key_w = total_w // n_white
        self.wh = int(h * 0.30)
        self.bh = int(self.wh * 0.62)
        self.bw = int(self.key_w * 0.60)
        self.key_y = h - self.wh - 20
        self.white_rects = {}
        for i, note in enumerate(WHITE_NOTES):
            x = margin + i * self.key_w
            self.white_rects[note] = (x, self.key_y, self.key_w - 2, self.wh)
        self.black_rects = {}
        for note, (white_idx, _) in BLACK_NOTES.items():
            x = margin + white_idx * self.key_w + self.key_w - self.bw // 2
            self.black_rects[note] = (x, self.key_y, self.bw, self.bh)
    def note_at(self, px: int, py: int):
        for note, (x, y, w, h) in self.black_rects.items():
            if x <= px <= x + w and y <= py <= y + h:
                return note
        for note, (x, y, w, h) in self.white_rects.items():
            if x <= px <= x + w and y <= py <= y + h:
                return note
        return None
    def draw(self, frame, active_notes: set, hover_notes: set):
        for note, (x, y, w, h) in self.white_rects.items():
            if note in active_notes:
                col, alpha, thick = (200,200,200), 0.35, 3
            elif note in hover_notes:
                col, alpha, thick = (200,200,200), 0.15, 2
            else:
                col, alpha, thick = (200,200,200), 0.08, 1
            ov = frame.copy()
            cv2.rectangle(ov, (x, y), (x+w, y+h), col, -1)
            cv2.addWeighted(ov, alpha, frame, 1-alpha, 0, frame)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (180,180,180), thick)
            lbl = note.replace('#', 's')
            cv2.putText(frame, lbl, (x+4, y+h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200,200,200), 1)
        for note, (x, y, w, h) in self.black_rects.items():
            if note in active_notes:
                col, alpha, thick = (80,80,80), 0.45, 3
            elif note in hover_notes:
                col, alpha, thick = (60,60,60), 0.20, 2
            else:
                col, alpha, thick = (30,30,30), 0.12, 1
            ov = frame.copy()
            cv2.rectangle(ov, (x, y), (x+w, y+h), col, -1)
            cv2.addWeighted(ov, alpha, frame, 1-alpha, 0, frame)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (160,160,160), thick)

# ═══════════════════════════════════════════════════════
# SONG ENGINE (with visual metronome)
# ═══════════════════════════════════════════════════════

class SongEngine:
    def __init__(self, song_data, layout, audio, w, h):
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
        self.played_notes = set()
        self.layout = layout
        self.audio = audio
        self.w = w
        self.h = h
        self.falling_notes = []
        self.note_height = 80
        self.note_width = 60
        self.active_notes = set()
        self.hover_notes = set()

        # Metronome state
        self.metronome_enabled = True   # can be toggled with a key (M)
        self.last_beat_time = 0
        self.beat_phase = 0.0           # 0..1 within current beat
        self.beat_animation = 0.0       # for bouncing ball (0..1)

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
                'duration': note.get('duration', 0.5),
                'dead': False,
                'hit': False
            })
        self.last_beat_time = self.start_time
        self.beat_phase = 0.0
        self.beat_animation = 0.0

    def update(self, current_time, played_notes_set):
        if self.start_time is None:
            return self.score, self.combo, self.perfect, self.good, self.missed
        elapsed = current_time - self.start_time
        hit_window = 0.1

        # Update metronome animation
        beat_length = self.beat_duration
        if beat_length > 0:
            # Phase within current beat (0..1)
            self.beat_phase = (elapsed % beat_length) / beat_length
            # Bouncing ball: sine wave that peaks at beat start
            self.beat_animation = max(0, math.sin(math.pi * self.beat_phase)) ** 0.8

        # Process notes (unchanged)
        for fn in self.falling_notes[:]:
            if fn['dead']:
                continue
            note_time = fn['start_beat'] * self.beat_duration
            if elapsed >= note_time - hit_window and not fn.get('hit', False):
                fn['dead'] = True
                if fn['note'] in played_notes_set:
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
                played_notes_set.discard(fn['note'])
        self.falling_notes = [fn for fn in self.falling_notes if not fn.get('dead', False)]
        return self.score, self.combo, self.perfect, self.good, self.missed

    def draw(self, frame):
        # Draw falling notes (same as before)
        for fn in self.falling_notes:
            rect = self.layout.white_rects.get(fn['note']) or self.layout.black_rects.get(fn['note'])
            if rect:
                x = rect[0] + rect[2]//2 - self.note_width//2
                y = int((fn['start_beat'] * self.beat_duration - (time.time() - self.start_time)) * 200) + 50
                if 0 < y < self.layout.key_y:
                    cv2.rectangle(frame, (x, y), (x+self.note_width, y+self.note_height), (0,200,255), -1)
                    cv2.rectangle(frame, (x, y), (x+self.note_width, y+self.note_height), (255,255,255), 2)
                    cv2.putText(frame, fn['note'], (x+5, y+self.note_height-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)

        # Draw score/combo panel
        cv2.rectangle(frame, (10,10), (250, 120), (0,0,0), -1)
        cv2.putText(frame, f"SCORE: {self.score}", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(frame, f"COMBO: {self.combo}", (20,70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        cv2.putText(frame, f"PERFECT: {self.perfect}  GOOD: {self.good}  MISS: {self.missed}", (20,100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

        # Draw visual metronome (if enabled)
        if self.metronome_enabled:
            bar_width = 120
            bar_height = 15
            bar_x = (frame.shape[1] - bar_width) // 2
            bar_y = 130
            # Background bar
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_width, bar_y+bar_height), (50,50,50), -1)
            # Fill based on beat phase (0..1)
            fill = int(bar_width * self.beat_phase)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x+fill, bar_y+bar_height), (0,200,255), -1)
            # Bouncing ball
            ball_radius = 12
            ball_x = bar_x + int(bar_width * self.beat_phase)
            ball_y = bar_y - 20 - int(self.beat_animation * 20)  # moves up and down
            cv2.circle(frame, (ball_x, ball_y), ball_radius, (0,200,255), -1)
            cv2.circle(frame, (ball_x, ball_y), ball_radius, (255,255,255), 2)
            # Beat indicator text
            cv2.putText(frame, f"{self.bpm} BPM", (bar_x + bar_width//2 - 30, bar_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

        return frame

# ═══════════════════════════════════════════════════════
# FREE-PLAY MAIN (unchanged)
# ═══════════════════════════════════════════════════════

FINGERTIP_IDS = [4, 8, 12, 16, 20]

def main():
    print("AR Piano starting...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found."); return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7, min_tracking_confidence=0.65)

    ret, frame0 = cap.read()
    h, w = (frame0.shape[:2] if ret else (720, 1280))

    audio = PianoAudio()
    layout = PianoLayout(w, h)

    detectors = {i: TapDetector() for i in range(10)}
    active_notes = {}
    last_note_str = ""
    flash_until = 0.0

    print("Show both hands above the piano keys | Tap fingers down to play | ESC = exit\n")

    while True:
        ok, frame = cap.read()
        if not ok: continue
        try:
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)
            hover_notes = set()
            now = time.time()

            if res.multi_hand_landmarks and res.multi_handedness:
                for hi, hlm in enumerate(res.multi_hand_landmarks):
                    for fi, lid in enumerate(FINGERTIP_IDS):
                        slot = hi * 5 + fi
                        lm = hlm.landmark[lid]
                        px = int(np.clip(lm.x * w, 0, w-1))
                        py = int(np.clip(lm.y * h, 0, h-1))
                        note = layout.note_at(px, py)
                        if note:
                            hover_notes.add(note)
                        fired = detectors[slot].update(float(py), note)
                        if fired:
                            vol = 0.7
                            audio.play(fired, vol)
                            active_notes[fired] = now + 0.35
                            last_note_str = fired
                            flash_until = now + 0.4
                        hand_col = (255,120,80) if hi == 0 else (80,180,255)
                        cv2.circle(frame, (px, py), 10, hand_col, -1)
                        cv2.circle(frame, (px, py), 13, (255,255,255), 2)

            active_notes = {n: t for n, t in active_notes.items() if t > now}
            layout.draw(frame, set(active_notes.keys()), hover_notes)

            cv2.rectangle(frame, (0,0), (w,80), (12,12,12), -1)
            cv2.rectangle(frame, (0,78), (w,80), (0,160,220), -1)
            cv2.putText(frame, "AR PIANO (FREE)", (18,52), cv2.FONT_HERSHEY_DUPLEX, 1.5, (0,200,255), 3)

            if not audio.ready:
                cv2.putText(frame, "Synthesising notes...", (w//2-120, h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,200,255), 2)

            nc = (0,220,255) if now < flash_until else (70,70,70)
            cv2.putText(frame, last_note_str, (w//2-45, h//2-20), cv2.FONT_HERSHEY_DUPLEX, 2.2, nc, 4)

            cv2.circle(frame, (w-260,30), 8, (255,120,80), -1)
            cv2.putText(frame, "Hand 1", (w-245,36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,120,80), 1)
            cv2.circle(frame, (w-160,30), 8, (80,180,255), -1)
            cv2.putText(frame, "Hand 2", (w-145,36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80,180,255), 1)

            for i, txt in enumerate(["Tap fingers DOWN onto keys to play",
                                      "Both hands supported (10 fingers)",
                                      "ESC = exit"]):
                cv2.putText(frame, txt, (18, h - layout.wh - 45 + i*16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (90,90,90), 1)

            cv2.imshow("AR Piano", frame)
        except Exception as e:
            print(f"Frame error (skipped): {e}")

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    try: hands.close()
    except: pass
    print("Piano closed.")

# ═══════════════════════════════════════════════════════
# SONG MODE (with visual metronome and retry)
# ═══════════════════════════════════════════════════════

def run_song_mode(song_path):
    """Launch piano with song following, visual metronome, and restart on fist hold."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found."); return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7, min_tracking_confidence=0.65)

    ret, frame0 = cap.read()
    h, w = (frame0.shape[:2] if ret else (720, 1280))

    with open(song_path, 'r') as f:
        song_data = json.load(f)

    audio = PianoAudio()
    layout = PianoLayout(w, h)
    song_engine = SongEngine(song_data, layout, audio, w, h)
    song_engine.start()

    detectors = {i: TapDetector() for i in range(10)}
    active_notes = {}
    last_note_str = ""
    flash_until = 0.0

    # Retry gesture state
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

    print(f"Playing song: {song_data['title']} | Tap notes in time | Hold FIST 1s to restart | M = toggle metronome | ESC = exit")

    while True:
        ok, frame = cap.read()
        if not ok: continue
        try:
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)
            hover_notes = set()
            now = time.time()

            played_this_frame = set()

            # Detect fist for retry (on any hand)
            if res.multi_hand_landmarks:
                for hlm in res.multi_hand_landmarks:
                    if detect_fist(hlm.landmark):
                        if fist_start_time is None:
                            fist_start_time = now
                        elif now - fist_start_time >= retry_hold_duration:
                            song_engine.start()
                            print("Song restarted!")
                            fist_start_time = None
                            flash_until = 0
                            active_notes.clear()
                        break
                else:
                    fist_start_time = None
            else:
                fist_start_time = None

            if res.multi_hand_landmarks and res.multi_handedness:
                for hi, hlm in enumerate(res.multi_hand_landmarks):
                    for fi, lid in enumerate(FINGERTIP_IDS):
                        slot = hi * 5 + fi
                        lm = hlm.landmark[lid]
                        px = int(np.clip(lm.x * w, 0, w-1))
                        py = int(np.clip(lm.y * h, 0, h-1))
                        note = layout.note_at(px, py)
                        if note:
                            hover_notes.add(note)
                            played_this_frame.add(note)
                        fired = detectors[slot].update(float(py), note)
                        if fired:
                            vol = 0.7
                            audio.play(fired, vol)
                            active_notes[fired] = now + 0.35
                            last_note_str = fired
                            flash_until = now + 0.4
                        hand_col = (255,120,80) if hi == 0 else (80,180,255)
                        cv2.circle(frame, (px, py), 10, hand_col, -1)
                        cv2.circle(frame, (px, py), 13, (255,255,255), 2)

            active_notes = {n: t for n, t in active_notes.items() if t > now}
            layout.draw(frame, set(active_notes.keys()), hover_notes)

            # Update song engine
            score, combo, perfect, good, missed = song_engine.update(now, played_this_frame)
            frame = song_engine.draw(frame)

            cv2.rectangle(frame, (0,0), (w,80), (12,12,12), -1)
            cv2.rectangle(frame, (0,78), (w,80), (0,200,255), -1)
            cv2.putText(frame, f"SONG: {song_data['title']}", (18,52), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0,200,255), 2)

            nc = (0,220,255) if now < flash_until else (70,70,70)
            cv2.putText(frame, last_note_str, (w//2-45, h//2-20), cv2.FONT_HERSHEY_DUPLEX, 2.2, nc, 4)

            # Show retry hint if fist is being held
            if fist_start_time is not None:
                elapsed = now - fist_start_time
                if elapsed < retry_hold_duration:
                    remaining = retry_hold_duration - elapsed
                    cv2.putText(frame, f"Hold FIST {remaining:.1f}s to restart", (20, h-30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

            # Shortcut to toggle metronome
            cv2.putText(frame, "M: toggle metronome", (w-180, h-20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150,150,150), 1)

            cv2.imshow("AR Piano - Song Mode", frame)
        except Exception as e:
            print(f"Frame error: {e}")

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif key == ord('m') or key == ord('M'):
            song_engine.metronome_enabled = not song_engine.metronome_enabled
            print(f"Metronome: {'ON' if song_engine.metronome_enabled else 'OFF'}")

    cap.release()
    cv2.destroyAllWindows()
    try: hands.close()
    except: pass
    print("Song mode finished.")

def run_piano():
    main()

if __name__ == "__main__":
    main()