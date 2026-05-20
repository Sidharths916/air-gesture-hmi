#!/usr/bin/env python3
"""
AR VIRTUAL GUITAR  -  Final + Song Mode + Retry
══════════════════════════════════════════════════════
"""

import time
import threading
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

# ═══════════════════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════════════════

SR = 22050
OPEN_HZ = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
STR_NAMES = ["E2","A2","D3","G3","B3","E4"]
N_FRETS = 13

def _karplus(freq: float, duration: float = 2.2) -> np.ndarray:
    N = int(SR / freq)
    rng = np.random.default_rng(int(freq * 37) % (2**32 - 1))
    buf = list(rng.uniform(-1, 1, N).astype(np.float64))
    n_samp = int(SR * duration)
    out = np.zeros(n_samp, np.float64)
    for i in range(n_samp):
        out[i] = buf[0]
        avg = 0.5 * (buf[0] + buf[1]) * 0.996
        buf.pop(0)
        buf.append(avg)
    pk = np.max(np.abs(out))
    if pk > 0: out = out / pk * 0.80
    mono = (out * 32767).astype(np.int16)
    return np.column_stack([mono, mono])

class GuitarAudio:
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
            pygame.mixer.set_num_channels(8)
        except Exception as e:
            print(f"Audio: {e}"); return
        for si, base in enumerate(OPEN_HZ):
            for fi in range(N_FRETS):
                freq = base * (2.0 ** (fi / 12.0))
                snd = pygame.sndarray.make_sound(_karplus(freq))
                with self._lock:
                    self._cache[(si, fi)] = snd
        self.ready = True
        print(f"Audio: {len(self._cache)} guitar notes ready")
    def play(self, si: int, fi: int, vol: float = 0.8):
        if not self.ready or not _PYGAME: return
        key = (int(si), int(np.clip(fi, 0, N_FRETS - 1)))
        with self._lock:
            snd = self._cache.get(key)
        if snd:
            try:
                ch = pygame.mixer.Channel(si)
                ch.set_volume(float(np.clip(vol, 0.1, 1.0)))
                ch.play(snd)
            except Exception:
                pass

# ═══════════════════════════════════════════════════════
# GUITAR GEOMETRY
# ═══════════════════════════════════════════════════════

class GuitarGeometry:
    RELOCK_THRESH = 45
    def __init__(self):
        self.ready = False
        self.neck_pos = None
        self.body_pos = None
        self.axis = None
        self.perp = None
        self.length = 0.0
        self.strings = []
        self._last_neck = None
        self._neck_buf = deque(maxlen=6)
        self._body_buf = deque(maxlen=6)
    def update(self, neck_center: np.ndarray, body_center: np.ndarray):
        self._neck_buf.append(neck_center)
        self._body_buf.append(body_center)
        nc = np.mean(self._neck_buf, axis=0).astype(np.float32)
        bc = np.mean(self._body_buf, axis=0).astype(np.float32)
        if self._last_neck is not None:
            movement = float(np.linalg.norm(nc - self._last_neck))
            if movement < self.RELOCK_THRESH:
                return
        self._lock(nc, bc)
    def _lock(self, nc: np.ndarray, bc: np.ndarray):
        d = bc - nc
        ln = float(np.linalg.norm(d))
        if ln < 30: return
        self.axis = (d / ln).astype(np.float32)
        self.perp = np.array([-self.axis[1], self.axis[0]], np.float32)
        self.length = ln
        self.neck_pos = nc - self.axis * ln * 0.12
        self.body_pos = bc + self.axis * ln * 0.12
        spacing = ln * 0.038
        self.strings = []
        for i in range(6):
            off = (i - 2.5) * spacing
            self.strings.append({
                'start': self.neck_pos + self.perp * off,
                'end': self.body_pos + self.perp * off,
                'offset': off,
                'radius': spacing * 0.42,
            })
        self._last_neck = nc.copy()
        self.ready = True
    def get_fret(self, finger_pos: np.ndarray) -> int:
        if not self.ready: return 0
        rel = finger_pos - self.neck_pos
        along = float(np.dot(rel, self.axis))
        fret = int((along / max(self.length, 1)) * 12)
        return int(np.clip(fret, 0, N_FRETS - 1))

class PickDetector:
    def __init__(self):
        self._prev = None
        self._last_t = [0.0] * 6
        self._cool = 0.10
        self._min_mv = 3.0
    def update(self, pick_pos: np.ndarray, geom: GuitarGeometry):
        if not geom.ready: return None, 0.0
        rel = pick_pos - geom.strings[0]['start']
        off = float(np.dot(rel, geom.perp))
        if self._prev is None:
            self._prev = off; return None, 0.0
        move = off - self._prev
        spd = abs(move)
        fired = None
        if spd > self._min_mv:
            now = time.time()
            for i, s in enumerate(geom.strings):
                if (self._prev - s['offset']) * (off - s['offset']) < 0:
                    along = float(np.dot(pick_pos - geom.neck_pos, geom.axis))
                    if 0 < along < geom.length:
                        if now - self._last_t[i] > self._cool:
                            if abs(off - s['offset']) < s['radius'] or abs(self._prev - s['offset']) < s['radius']:
                                fired = i
                                self._last_t[i] = now
                                break
        self._prev = off
        return fired, spd

# ═══════════════════════════════════════════════════════
# DRAWING
# ═══════════════════════════════════════════════════════

def draw_guitar(frame, geom: GuitarGeometry, vibration, phase):
    if not geom.ready: return
    ax = geom.axis; pp = geom.perp; ln = geom.length
    np_ = geom.neck_pos; bp = geom.body_pos
    C_WOOD = (40,80,140); C_NECK = (30,60,100); C_FRET = (160,160,160)
    C_EDGE = (80,130,180); C_BODY = (45,88,148)
    nw = int(ln * 0.025)
    body_c = bp + ax * ln * 0.08
    cv2.ellipse(frame, (int(body_c[0]), int(body_c[1])), (int(ln*0.26), int(ln*0.20)), 0, 0, 360, C_BODY, -1)
    cv2.ellipse(frame, (int(body_c[0]), int(body_c[1])), (int(ln*0.26), int(ln*0.20)), 0, 0, 360, C_EDGE, 2)
    cv2.circle(frame, (int(body_c[0]), int(body_c[1])), int(ln*0.07), (15,25,50), -1)
    cv2.circle(frame, (int(body_c[0]), int(body_c[1])), int(ln*0.07), C_EDGE, 2)
    nk = np.array([np_ + pp*nw, np_ - pp*nw, bp - pp*nw, bp + pp*nw], np.int32)
    nl = frame.copy(); cv2.fillPoly(nl, [nk], C_NECK)
    cv2.addWeighted(nl, 0.80, frame, 0.20, 0, frame)
    cv2.polylines(frame, [nk], True, C_EDGE, 2)
    for f in range(1, N_FRETS):
        t = f / 12.0
        fp = np_ + ax * ln * t
        cv2.line(frame, (int((fp + pp*nw*1.1)[0]), int((fp + pp*nw*1.1)[1])),
                       (int((fp - pp*nw*1.1)[0]), int((fp - pp*nw*1.1)[1])), C_FRET, 1)
        if f in [3,5,7,9,12]:
            cv2.circle(frame, (int(fp[0]), int(fp[1])), 4, C_FRET, -1)
    head = np_ - ax * ln * 0.10
    cv2.circle(frame, (int(head[0]), int(head[1])), int(ln*0.045), C_NECK, -1)
    cv2.circle(frame, (int(head[0]), int(head[1])), int(ln*0.045), C_EDGE, 2)
    br = bp + ax * ln * 0.10; bw = ln * 0.10
    cv2.line(frame, (int((br + pp*bw)[0]), int((br + pp*bw)[1])),
                   (int((br - pp*bw)[0]), int((br - pp*bw)[1])), (160,130,60), 3)
    for i, s in enumerate(geom.strings):
        vib = vibration[i]
        col = (0,240,200) if vib > 0.3 else (210,210,210)
        thick = 3 if vib > 0.3 else 2
        if vib > 0.2:
            pts = []
            for u in np.linspace(0,1,18):
                p = s['start'] + (s['end'] - s['start']) * u
                p = p + pp * vib * np.sin(phase[i] + u*4*np.pi) * 5
                pts.append((int(p[0]), int(p[1])))
            cv2.polylines(frame, [np.array(pts)], False, col, thick)
        else:
            cv2.line(frame, (int(s['start'][0]), int(s['start'][1])),
                           (int(s['end'][0]),   int(s['end'][1])), col, thick)

# ═══════════════════════════════════════════════════════
# SONG ENGINE (guitar version)
# ═══════════════════════════════════════════════════════

class GuitarSongEngine:
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
        self.played_success = False  # will be set each frame
        self.audio = audio
        self.geom = geom
        self.w = w
        self.h = h
        self.falling_notes = []
        self.note_width = 80
        self.note_height = 30
        # Note name to (string, fret) mapping (simplified)
        self.note_map = {
            'C4': (3,1), 'D4': (3,3), 'E4': (4,0), 'F4': (4,1), 'G4': (3,5),
            'A4': (2,0), 'B4': (2,2), 'C5': (2,3), 'D5': (2,5), 'E5': (1,0),
            'F5': (1,1), 'G5': (1,3), 'A5': (1,5), 'B5': (0,2), 'E2': (5,0),
            'A2': (4,0), 'D3': (3,0), 'G3': (2,0), 'B3': (1,0)
        }
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
            if 0 < y < self.h-100:
                cv2.rectangle(frame, (20, y), (20+self.note_width, y+self.note_height), (0,200,255), -1)
                cv2.rectangle(frame, (20, y), (20+self.note_width, y+self.note_height), (255,255,255), 2)
                cv2.putText(frame, fn['note'], (25, y+self.note_height-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)
        cv2.rectangle(frame, (10,10), (250, 120), (0,0,0), -1)
        cv2.putText(frame, f"SCORE: {self.score}", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(frame, f"COMBO: {self.combo}", (20,70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        cv2.putText(frame, f"PERFECT: {self.perfect}  GOOD: {self.good}  MISS: {self.missed}", (20,100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
        return frame

# ═══════════════════════════════════════════════════════
# FREE-PLAY MAIN
# ═══════════════════════════════════════════════════════

def main():
    print("AR Guitar starting...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found."); return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.70, min_tracking_confidence=0.65)

    audio = GuitarAudio()
    geom = GuitarGeometry()
    pick_d = PickDetector()

    vibration = [0.0] * 6
    phase = [0.0] * 6
    last_note = ""
    flash_until = 0.0
    active_fret = 0

    print("Show both hands | Left hand = neck (frets) | Right hand = pick | ESC = exit\n")

    while True:
        ok, frame = cap.read()
        if not ok: break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)

        neck_center = pick_center = None
        neck_index = pick_index = None

        if res.multi_hand_landmarks and res.multi_handedness:
            hand_data = []
            for i, hlm in enumerate(res.multi_hand_landmarks):
                mp_draw.draw_landmarks(frame, hlm, mp_hands.HAND_CONNECTIONS)
                pts = [(lm.x * w, lm.y * h) for lm in hlm.landmark]
                cx = float(np.mean([p[0] for p in pts]))
                hand_data.append({
                    'center': np.array([cx, np.mean([p[1] for p in pts])], np.float32),
                    'index': np.array(pts[8], np.float32),
                    'x': cx,
                })
            if len(hand_data) >= 2:
                hand_data.sort(key=lambda h: h['x'])
                neck = hand_data[0]
                pick = hand_data[1]
                neck_center = neck['center']
                neck_index = neck['index']
                pick_center = pick['center']
                pick_index = pick['index']
                geom.update(neck_center, pick_center)

        if neck_index is not None and geom.ready:
            active_fret = geom.get_fret(neck_index)

        if pick_index is not None and geom.ready:
            fired, spd = pick_d.update(pick_index, geom)
            if fired is not None:
                vibration[fired] = min(2.0, 0.7 + spd / 25.0)
                phase[fired] = 0.0
                vol = float(np.clip(0.3 + spd / 60.0, 0.2, 1.0))
                audio.play(fired, active_fret, vol)
                last_note = f"{STR_NAMES[fired]} fret {active_fret}"
                flash_until = time.time() + 0.5
                cv2.circle(frame, (int(pick_index[0]), int(pick_index[1])), 14, (0,240,200), -1)
                cv2.circle(frame, (int(pick_index[0]), int(pick_index[1])), 14, (255,255,255), 2)

        if neck_index is not None:
            cv2.circle(frame, (int(neck_index[0]), int(neck_index[1])), 12, (255,120,60), -1)
            cv2.circle(frame, (int(neck_index[0]), int(neck_index[1])), 12, (255,255,255), 2)

        for i in range(6):
            vibration[i] *= 0.93
            phase[i] += 0.4

        if geom.ready:
            draw_guitar(frame, geom, vibration, phase)
            for i, s in enumerate(geom.strings):
                mid = (s['start'] + s['end']) * 0.5
                cv2.putText(frame, STR_NAMES[i], (int(mid[0])-20, int(mid[1])+5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,240,200) if vibration[i]>0.3 else (120,120,120), 1)

        cv2.rectangle(frame, (0,0), (w,80), (12,12,12), -1)
        cv2.rectangle(frame, (0,78), (w,80), (0,160,100), -1)
        cv2.putText(frame, "AR GUITAR (FREE)", (18,52), cv2.FONT_HERSHEY_DUPLEX, 1.5, (0,200,120), 3)

        if len(hand_data if res.multi_hand_landmarks else []) < 2:
            status = "Show both hands to camera"
        elif not geom.ready:
            status = "Hold hands apart to form guitar"
        elif not audio.ready:
            status = "Loading sounds..."
        else:
            status = "Pick strings with right hand | Left hand frets"
        cv2.putText(frame, status, (18,72), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (185,185,185), 2)

        nc = (0,240,200) if time.time() < flash_until else (70,70,70)
        cv2.putText(frame, last_note, (w//2-100, h//2+20), cv2.FONT_HERSHEY_DUPLEX, 1.8, nc, 3)

        cv2.putText(frame, "FRET", (w-90,132), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (150,150,150), 1)
        bh = 140; by = 150; fx = w-90
        cv2.rectangle(frame, (fx, by), (fx+18, by+bh), (42,42,42), 1)
        fill = int(bh * active_fret / 12)
        cv2.rectangle(frame, (fx+1, by+bh-fill), (fx+17, by+bh-1), (0,200,120), -1)
        cv2.putText(frame, str(active_fret), (fx-5, by+bh+22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140,140,140), 1)

        for i, txt in enumerate(["Left hand (left of frame) = neck + frets", "Right hand = pick strings", "ESC = exit"]):
            cv2.putText(frame, txt, (18, h-55+i*18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (85,85,85), 1)

        cv2.imshow("AR Guitar", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    try: hands.close()
    except: pass
    print("Guitar closed.")

# ═══════════════════════════════════════════════════════
# SONG MODE (with retry)
# ═══════════════════════════════════════════════════════

def run_song_mode(song_path):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found."); return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.70, min_tracking_confidence=0.65)

    with open(song_path, 'r') as f:
        song_data = json.load(f)

    audio = GuitarAudio()
    geom = GuitarGeometry()
    pick_d = PickDetector()
    song_engine = GuitarSongEngine(song_data, audio, geom, 1280, 720)
    song_engine.start()

    vibration = [0.0]*6
    phase = [0.0]*6
    last_note = ""
    flash_until = 0.0
    active_fret = 0

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

    print(f"Playing song: {song_data['title']} | Pluck notes in time | Hold FIST 1s to restart | ESC = exit")

    while True:
        ok, frame = cap.read()
        if not ok: break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)

        neck_center = pick_center = None
        neck_index = pick_index = None

        # Detect fist for retry on ANY hand
        if res.multi_hand_landmarks:
            for hlm in res.multi_hand_landmarks:
                if detect_fist(hlm.landmark):
                    if fist_start_time is None:
                        fist_start_time = time.time()
                    elif time.time() - fist_start_time >= retry_hold_duration:
                        song_engine.start()
                        print("Song restarted!")
                        fist_start_time = None
                        flash_until = 0
                        # Also clear any pending notes
                    break
            else:
                fist_start_time = None

        if res.multi_hand_landmarks and res.multi_handedness:
            hand_data = []
            for i, hlm in enumerate(res.multi_hand_landmarks):
                mp_draw.draw_landmarks(frame, hlm, mp_hands.HAND_CONNECTIONS)
                pts = [(lm.x * w, lm.y * h) for lm in hlm.landmark]
                cx = float(np.mean([p[0] for p in pts]))
                hand_data.append({
                    'center': np.array([cx, np.mean([p[1] for p in pts])], np.float32),
                    'index': np.array(pts[8], np.float32),
                    'x': cx,
                })
            if len(hand_data) >= 2:
                hand_data.sort(key=lambda h: h['x'])
                neck = hand_data[0]
                pick = hand_data[1]
                neck_center = neck['center']
                neck_index = neck['index']
                pick_center = pick['center']
                pick_index = pick['index']
                geom.update(neck_center, pick_center)

        if neck_index is not None and geom.ready:
            active_fret = geom.get_fret(neck_index)

        played_string = None
        if pick_index is not None and geom.ready:
            fired, spd = pick_d.update(pick_index, geom)
            if fired is not None:
                played_string = fired
                vibration[fired] = min(2.0, 0.7 + spd/25.0)
                phase[fired] = 0.0
                vol = float(np.clip(0.3 + spd/60.0, 0.2, 1.0))
                audio.play(fired, active_fret, vol)
                last_note = f"{STR_NAMES[fired]} fret {active_fret}"
                flash_until = time.time() + 0.5
                cv2.circle(frame, (int(pick_index[0]), int(pick_index[1])), 14, (0,240,200), -1)
                cv2.circle(frame, (int(pick_index[0]), int(pick_index[1])), 14, (255,255,255), 2)

        if neck_index is not None:
            cv2.circle(frame, (int(neck_index[0]), int(neck_index[1])), 12, (255,120,60), -1)
            cv2.circle(frame, (int(neck_index[0]), int(neck_index[1])), 12, (255,255,255), 2)

        for i in range(6):
            vibration[i] *= 0.93
            phase[i] += 0.4

        if geom.ready:
            draw_guitar(frame, geom, vibration, phase)

        score, combo, perfect, good, missed = song_engine.update(time.time(), played_string if played_string is not None else -1, active_fret)
        frame = song_engine.draw(frame)

        cv2.rectangle(frame, (0,0), (w,80), (12,12,12), -1)
        cv2.rectangle(frame, (0,78), (w,80), (0,200,255), -1)
        cv2.putText(frame, f"SONG: {song_data['title']}", (18,52), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0,200,255), 2)

        nc = (0,240,200) if time.time() < flash_until else (70,70,70)
        cv2.putText(frame, last_note, (w//2-100, h//2+20), cv2.FONT_HERSHEY_DUPLEX, 1.8, nc, 3)

        if fist_start_time is not None:
            elapsed = time.time() - fist_start_time
            if elapsed < retry_hold_duration:
                remaining = retry_hold_duration - elapsed
                cv2.putText(frame, f"Hold FIST {remaining:.1f}s to restart", (20, h-30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,200,255), 2)

        cv2.imshow("AR Guitar - Song Mode", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    try: hands.close()
    except: pass
    print("Song mode finished.")

def run_guitar():
    main()

if __name__ == "__main__":
    main()