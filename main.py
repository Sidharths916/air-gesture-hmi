#!/usr/bin/env python3
"""
AIR GESTURE SYSTEM v3.8 - DRAW mode: 2D + Anaglyph + REAL 3D (STL) + COLORED 3D (OBJ+MTL+PNG)
═══════════════════════════════════════════════════════════════════════════════════════════
FIX: Entire canvas saved correctly (2D + Anaglyph + STL + Textured OBJ)
- Black/dark colors now drawn with (20,20,20) so they survive threshold
- STL export uses any non‑zero grayscale pixel (not fixed threshold 10)
- NEW: Exports textured OBJ+MTL+PNG – coloured 3D model (single texture, wide compatibility)
- Canvas persists until cleared (4 fingers) or mode exit
"""

import sys
import os
import cv2
import numpy as np
import mediapipe as mp
import time
import pickle
import threading
from datetime import datetime
from collections import deque
import logging
import json
import glob
import math

# Path handling
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(resource_path("gesture_log.txt")),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# Windows-specific for OSK
try:
    import win32gui
    import win32con
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    log.warning("win32 not available - OSK will use basic overlay")

# Typing support
try:
    from pynput.keyboard import Controller, Key
    keyboard = Controller()
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    log.warning("pynput not available - typing disabled")

# Mouse control
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
    SCREEN_W, SCREEN_H = pyautogui.size()
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    SCREEN_W, SCREEN_H = 1920, 1080
    log.warning("pyautogui not available - mouse control disabled")

# ==================== CONFIGURATION ====================

CANVAS_SIZE = (600, 600)
SAVE_DIR_DRAW = "data/drawings"
os.makedirs(SAVE_DIR_DRAW, exist_ok=True)

MUSIC_FILES = {
    'piano': 'piano_FINALv4.py',
    'guitar': 'guitar_FINALv4.py',
    'violin': 'violin_REFACTOREDv2.py'
}

SONGS_DIR = resource_path("assets/songs")
os.makedirs(SONGS_DIR, exist_ok=True)

EASTER_EGG_CODE = "whomadeyou"
EXIT_HOLD_TIME = 2.5
EASTER_COOLDOWN = 5.0
ASSETS_DIR = resource_path("assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

MODEL_PATH = resource_path("models/letter_recognizer.pkl")
DATASET_PATH = resource_path("data/processed/dataset.pkl")
RECOGNITION_AVAILABLE = False

SETTINGS_FILE = resource_path("config.json")

log.info(f"Assets dir: {ASSETS_DIR}")
log.info(f"Model path: {MODEL_PATH}")

print(f"\n{'='*70}")
print(f"  AIR GESTURE SYSTEM - DRAW: REAL 3D STL + COLORED OBJ Export")
print(f"{'='*70}\n")

# Load recognition model
try:
    with open(MODEL_PATH, "rb") as f:
        model_data = pickle.load(f)
    with open(DATASET_PATH, "rb") as f:
        dataset = pickle.load(f)
    rf_model = model_data["classifier"]
    templates = dataset["templates"]
    labels = dataset["labels"]
    template_bank = {}
    for template, label in zip(templates, labels):
        template_bank.setdefault(label, []).append(template)
    for letter in template_bank:
        if len(template_bank[letter]) > 15:
            indices = np.linspace(0, len(template_bank[letter])-1, 15, dtype=int)
            template_bank[letter] = [template_bank[letter][i] for i in indices]
    RECOGNITION_AVAILABLE = True
    log.info(f"Hybrid RF+DTW recognition loaded ({sum(len(v) for v in template_bank.values())} templates)")
except Exception as e:
    log.warning(f"Recognition model not available: {e}")
    template_bank = {}

print()

# ==================== AUDIO SYSTEM ====================

def play_sound(sound_file):
    def _play():
        try:
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(sound_file)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            except:
                try:
                    from playsound import playsound
                    playsound(sound_file)
                except Exception as e:
                    log.error(f"Sound error: {e}")
        except Exception as e:
            log.error(f"Sound thread error: {e}")
    threading.Thread(target=_play, daemon=True).start()

def beep():
    try:
        import winsound
        winsound.Beep(800, 80)
    except:
        pass

# ==================== EASTER EGG ====================

def trigger_easter_egg(app_instance):
    easter_video = resource_path(os.path.join("assets", "easter.mp4"))
    easter_sound = resource_path(os.path.join("assets", "easter.mp3"))
    if not os.path.exists(easter_video):
        log.warning("Easter egg video not found")
        return
    was_paused = app_instance.paused
    app_instance.paused = True
    if os.path.exists(easter_sound):
        play_sound(easter_sound)
    cap = cv2.VideoCapture(easter_video)
    log.info("EASTER EGG ACTIVATED!")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        h, w = frame.shape[:2]
        if w > 1280:
            scale = 1280 / w
            frame = cv2.resize(frame, (1280, int(h * scale)))
        cv2.imshow("Easter Egg", frame)
        if cv2.waitKey(30) & 0xFF == 27:
            break
    cap.release()
    cv2.destroyWindow("Easter Egg")
    app_instance.paused = was_paused
    log.info("Easter egg finished")

# ==================== CAMERA MANAGER ====================

class CameraManager:
    def __init__(self):
        self.available_cameras = []
        self.selected_cameras = []
        self.caps = []
    def detect_cameras(self, max_check=10):
        log.info("Detecting cameras...")
        for i in range(max_check):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    h, w = frame.shape[:2]
                    self.available_cameras.append({'index': i, 'res': f"{w}x{h}"})
                    log.info(f"  Camera {i}: {w}x{h}")
                cap.release()
        log.info(f"Found {len(self.available_cameras)} camera(s)")
        return len(self.available_cameras)
    def select_cameras(self):
        num = len(self.available_cameras)
        if num == 0:
            return False
        elif num == 1:
            log.info("Using Camera 0")
            self.selected_cameras = [0]
            return True
        else:
            print("="*70)
            print("MULTIPLE CAMERAS DETECTED")
            print("="*70)
            for cam in self.available_cameras:
                print(f"  {cam['index']}. Camera {cam['index']} ({cam['res']})")
            print("\nOptions:")
            print("  1. Camera 0 only")
            print("  2. Camera 1 only")
            print("  3. Both cameras (side-by-side)")
            print("="*70)
            choice = input("\nChoice [1-3]: ").strip()
            if choice == '2':
                self.selected_cameras = [1]
            elif choice == '3':
                self.selected_cameras = [0, 1]
            else:
                self.selected_cameras = [0]
            return True
    def open_cameras(self):
        for idx in self.selected_cameras:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.caps.append(cap)
                log.info(f"Opened camera {idx}")
        return len(self.caps) > 0
    def read_frames(self):
        frames = []
        for cap in self.caps:
            ret, frame = cap.read()
            frames.append(frame if ret else None)
        return frames
    def combine_frames(self, frames):
        valid = [f for f in frames if f is not None]
        if not valid:
            return None
        if len(valid) == 1:
            return valid[0]
        min_h = min(f.shape[0] for f in valid)
        resized = []
        for frame in valid:
            h, w = frame.shape[:2]
            new_w = int(w * min_h / h)
            resized.append(cv2.resize(frame, (new_w, min_h)))
        return np.hstack(resized)
    def release_all(self):
        for cap in self.caps:
            if cap.isOpened():
                cap.release()
        self.caps = []

# ==================== MUSIC LAUNCHER ====================

def launch_music(instrument):
    filename = MUSIC_FILES.get(instrument)
    if not filename:
        log.error(f"Unknown instrument: {instrument}")
        input("Press Enter...")
        return
    script_path = resource_path(filename)
    if not os.path.exists(script_path):
        log.error(f"Music script not found: {script_path}")
        input("Press Enter...")
        return
    print(f"\n{'='*70}\nLAUNCHING {instrument.upper()} (free-play)\n{'='*70}\n")
    try:
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            exec(f.read(), {'__name__': '__main__'})
    except KeyboardInterrupt:
        print("\nInstrument stopped")
    except Exception as e:
        log.exception(f"Error launching {instrument}: {e}")
    finally:
        print(f"\n{'='*70}\n")

# ==================== SONG LOADER ====================

def load_song_metadata(filepath, default_instrument=None):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        return None
    instrument = None
    if isinstance(data, dict):
        if 'instrument' in data:
            instrument = data['instrument'].lower()
        elif 'metadata' in data and isinstance(data['metadata'], dict):
            instrument = data['metadata'].get('instrument', '').lower()
    if not instrument:
        instrument = default_instrument
    if not instrument:
        if 'tracks' in data or 'songNotes' in data:
            instrument = 'piano'
        else:
            return None
    title = os.path.basename(filepath).replace('.json', '')
    if isinstance(data, dict):
        title = data.get('title', data.get('metadata', {}).get('title', title))
    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        title = data[0].get('name', title)
    bpm = 120
    if isinstance(data, dict):
        bpm = data.get('bpm', data.get('metadata', {}).get('tempo', 120))
    elif isinstance(data, list) and len(data) > 0:
        bpm = data[0].get('bpm', 120)
    notes = []
    # Standard format
    if isinstance(data, dict) and 'tracks' in data:
        for track in data['tracks']:
            for n in track.get('notes', []):
                notes.append({
                    'note': n.get('note'),
                    'start_beat': n.get('start_beat', 0.0),
                    'duration': n.get('duration', 0.5)
                })
    # Sectioned notes
    elif isinstance(data, dict) and 'content' in data:
        current_beat = 0.0
        dur_map = {'whole':4.0,'half':2.0,'quarter':1.0,'eighth':0.5,'sixteenth':0.25}
        for section in data['content']:
            for n in section.get('notes', []):
                pitch = n.get('pitch')
                dur_str = n.get('duration', 'quarter')
                dur = dur_map.get(dur_str, 1.0)
                if pitch:
                    notes.append({'note': pitch, 'start_beat': current_beat, 'duration': dur})
                current_beat += dur
    # Sky-music
    elif isinstance(data, list) and len(data)>0 and 'songNotes' in data[0]:
        sec_per_beat = 60.0/bpm
        note_map = {'1Key1':'C4','1Key2':'D4','1Key3':'E4','1Key4':'F4',
                    '1Key5':'G4','1Key6':'A4','1Key7':'B4','1Key8':'C5'}
        for item in data[0]['songNotes']:
            key_code = item.get('key')
            time_ms = item.get('time',0)
            note = note_map.get(key_code,'C4')
            start_beat = (time_ms/1000.0)/sec_per_beat
            notes.append({'note':note,'start_beat':start_beat,'duration':0.5})
    if not notes:
        return None
    notes.sort(key=lambda x: x['start_beat'])
    return {
        'title': title,
        'instrument': instrument,
        'bpm': bpm,
        'notes': notes
    }

# ==================== OSK KEYBOARD ====================

class OSKKeyboard:
    def __init__(self):
        self.screen_w = win32api.GetSystemMetrics(0) if WIN32_AVAILABLE else SCREEN_W
        self.screen_h = win32api.GetSystemMetrics(1) if WIN32_AVAILABLE else SCREEN_H
        self.key_w = 65
        self.key_h = 55
        self.key_spacing = 6
        self.rows = [
            ["`","1","2","3","4","5","6","7","8","9","0","-","=","BKSP"],
            ["TAB","Q","W","E","R","T","Y","U","I","O","P","[","]","\\"],
            ["CAPS","A","S","D","F","G","H","J","K","L",";","'","ENTER"],
            ["SHIFT","Z","X","C","V","B","N","M",",",".","/","SHIFT"],
            ["CTRL","WIN","ALT","SPACE","ALT","CTRL"]
        ]
        total_width = 14*(self.key_w+self.key_spacing)
        self.start_x = (self.screen_w - total_width)//2
        self.start_y = self.screen_h - (6*(self.key_h+self.key_spacing)) - 100
        self.key_positions = {}
        self._calculate_positions()
        self.mode = "STATIC"
        self.hover_key = None
        self.hover_start_time = None
        self.hover_threshold = 0.3
        self.last_pressed_key = None
        self.has_left_key = True
        self.last_key_time = 0
        self.repeat_delay = 0.15
        self.press_depth = 0.2
        self.shift_on = False
        self.caps_on = False
        self.ctrl_on = False
        self.alt_on = False
        self.text = ""
        self.cursor_blink = True
        self.last_blink_time = time.time()
        self.switch_button = {'x':self.screen_w-200,'y':50,'x2':self.screen_w-50,'y2':110}
        self.text_field = {'x':200,'y':50,'x2':self.screen_w-230,'y2':130}
    def _calculate_positions(self):
        y = self.start_y
        for row in self.rows:
            x = self.start_x
            for key in row:
                if key=="BKSP": w = self.key_w*1.5
                elif key=="TAB": w = self.key_w*1.3
                elif key=="CAPS": w = self.key_w*1.5
                elif key=="ENTER": w = self.key_w*1.5
                elif key=="SHIFT": w = self.key_w*1.8
                elif key=="SPACE": w = self.key_w*5
                else: w = self.key_w
                self.key_positions[key] = {'x':x,'y':y,'x2':x+w,'y2':y+self.key_h}
                x += w+self.key_spacing
            y += self.key_h+self.key_spacing
    def get_key_at_position(self,x,y):
        for key,pos in self.key_positions.items():
            if pos['x']<=x<=pos['x2'] and pos['y']<=y<=pos['y2']:
                return key
        return None
    def is_pressing(self,z): return z<self.press_depth
    def is_over_switch_button(self,x,y):
        b = self.switch_button
        return b['x']<=x<=b['x2'] and b['y']<=y<=b['y2']
    def switch_mode(self):
        self.mode = "DYNAMIC" if self.mode=="STATIC" else "STATIC"
        self.last_pressed_key = None
        self.has_left_key = True
        self.hover_key = None
    def update(self,finger_x,finger_y,finger_z):
        current_time = time.time()
        is_pressing = self.is_pressing(finger_z)
        key = self.get_key_at_position(finger_x,finger_y)
        if self.is_over_switch_button(finger_x,finger_y) and is_pressing:
            if self.hover_key=="SWITCH":
                if current_time-self.hover_start_time>=0.5:
                    self.switch_mode()
                    self.hover_key=None
                    self.hover_start_time=None
            else:
                self.hover_key="SWITCH"
                self.hover_start_time=current_time
            return
        if self.mode=="STATIC":
            if key is None:
                self.has_left_key=True
                self.hover_key=None
                self.hover_start_time=None
            elif is_pressing and key:
                if key!=self.last_pressed_key or self.has_left_key:
                    if key==self.hover_key:
                        hover_duration=current_time-self.hover_start_time
                        if hover_duration>=self.hover_threshold:
                            self.press_key(key)
                            self.last_pressed_key=key
                            self.has_left_key=False
                            self.hover_key=None
                            self.hover_start_time=None
                    else:
                        self.hover_key=key
                        self.hover_start_time=current_time
            else:
                self.hover_key=None
                self.hover_start_time=None
        else:
            if key and is_pressing:
                if key==self.hover_key:
                    hover_duration=current_time-self.hover_start_time
                    if hover_duration>=self.hover_threshold and self.last_key_time==0:
                        self.press_key(key)
                        self.last_key_time=current_time
                    elif self.last_key_time>0 and current_time-self.last_key_time>=self.repeat_delay:
                        self.press_key(key)
                        self.last_key_time=current_time
                else:
                    self.hover_key=key
                    self.hover_start_time=current_time
                    self.last_key_time=0
            else:
                self.hover_key=None
                self.hover_start_time=None
                self.last_key_time=0
    def press_key(self,key):
        if not PYNPUT_AVAILABLE:
            self.text += key if len(key)==1 else f"[{key}]"
            return
        try:
            if key=="BKSP":
                keyboard.press(Key.backspace); keyboard.release(Key.backspace)
                if self.text: self.text=self.text[:-1]
            elif key=="ENTER":
                keyboard.press(Key.enter); keyboard.release(Key.enter)
                self.text+="\n"
            elif key=="TAB":
                keyboard.press(Key.tab); keyboard.release(Key.tab)
            elif key=="SPACE":
                keyboard.press(Key.space); keyboard.release(Key.space)
                self.text+=" "
            elif key=="SHIFT":
                self.shift_on=not self.shift_on
            elif key=="CAPS":
                self.caps_on=not self.caps_on
            elif key=="CTRL":
                self.ctrl_on=not self.ctrl_on
            elif key=="ALT":
                self.alt_on=not self.alt_on
            elif key=="WIN":
                keyboard.press(Key.cmd); keyboard.release(Key.cmd)
            else:
                char=key
                if self.shift_on or self.caps_on:
                    char=char.upper() if char.isalpha() else char
                else:
                    char=char.lower()
                keyboard.press(char); keyboard.release(char)
                self.text+=char
                if self.shift_on:
                    self.shift_on=False
        except Exception as e:
            log.error(f"Key press error: {e}")
            self.text+=key if len(key)==1 else ""
    def draw_overlay(self,finger_x,finger_y,finger_z):
        frame = np.zeros((self.screen_h,self.screen_w,3),dtype=np.uint8)
        is_pressing=self.is_pressing(finger_z)
        tf=self.text_field
        overlay=frame.copy()
        cv2.rectangle(overlay,(tf['x'],tf['y']),(tf['x2'],tf['y2']),(30,30,30),-1)
        frame=cv2.addWeighted(overlay,0.3,frame,0.7,0)
        cv2.rectangle(frame,(tf['x'],tf['y']),(tf['x2'],tf['y2']),(255,255,0),3)
        if time.time()-self.last_blink_time>0.5:
            self.cursor_blink=not self.cursor_blink
            self.last_blink_time=time.time()
        display_text=self.text[-60:]
        if self.cursor_blink: display_text+="|"
        cv2.putText(frame,display_text,(tf['x']+15,tf['y']+55),cv2.FONT_HERSHEY_SIMPLEX,1.0,(255,255,255),2)
        mode_text=f"{self.mode} MODE"
        if self.shift_on: mode_text+=" | SHIFT"
        if self.caps_on: mode_text+=" | CAPS"
        if self.ctrl_on: mode_text+=" | CTRL"
        if self.alt_on: mode_text+=" | ALT"
        mode_color=(0,255,255) if self.mode=="STATIC" else (255,165,0)
        cv2.putText(frame,mode_text,(30,100),cv2.FONT_HERSHEY_DUPLEX,0.8,mode_color,2)
        b=self.switch_button
        is_switch_hover=(self.hover_key=="SWITCH")
        button_overlay=frame.copy()
        if is_switch_hover:
            cv2.rectangle(button_overlay,(b['x'],b['y']),(b['x2'],b['y2']),(0,255,0),-1)
        else:
            cv2.rectangle(button_overlay,(b['x'],b['y']),(b['x2'],b['y2']),(50,50,50),-1)
        frame=cv2.addWeighted(button_overlay,0.2,frame,0.8,0)
        border_color=(0,255,0) if is_switch_hover else (200,200,200)
        cv2.rectangle(frame,(b['x'],b['y']),(b['x2'],b['y2']),border_color,3)
        cv2.putText(frame,"MODE",(b['x']+35,b['y']+40),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255,255,255),2)
        for key,pos in self.key_positions.items():
            x,y=int(pos['x']),int(pos['y'])
            x2,y2=int(pos['x2']),int(pos['y2'])
            is_hover=(key==self.hover_key and is_pressing)
            if is_hover:
                key_overlay=frame.copy()
                if self.hover_start_time:
                    progress=min(1.0,(time.time()-self.hover_start_time)/self.hover_threshold)
                    fill_color=(0,int(255*progress),int(255*(1-progress)))
                else:
                    fill_color=(255,255,0)
                cv2.rectangle(key_overlay,(x,y),(x2,y2),fill_color,-1)
                frame=cv2.addWeighted(key_overlay,0.3,frame,0.7,0)
                border_color=(0,255,0); border_thickness=5; text_color=(0,0,255)
            else:
                if key in ["SHIFT","CAPS","CTRL","ALT"]:
                    if ((key=="SHIFT" and self.shift_on) or (key=="CAPS" and self.caps_on) or
                        (key=="CTRL" and self.ctrl_on) or (key=="ALT" and self.alt_on)):
                        key_overlay=frame.copy()
                        cv2.rectangle(key_overlay,(x,y),(x2,y2),(100,255,100),-1)
                        frame=cv2.addWeighted(key_overlay,0.2,frame,0.8,0)
                border_color=(0,0,255); border_thickness=2; text_color=(0,0,255)
            cv2.rectangle(frame,(x,y),(x2,y2),border_color,border_thickness)
            label=key[:4] if len(key)>4 else key
            font_scale=0.5 if len(label)>3 else 0.7
            text_size=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,font_scale,2)[0]
            text_x=x+(x2-x-text_size[0])//2
            text_y=y+(y2-y+text_size[1])//2
            cv2.putText(frame,label,(text_x+1,text_y+1),cv2.FONT_HERSHEY_SIMPLEX,font_scale,(255,255,255),3)
            cv2.putText(frame,label,(text_x,text_y),cv2.FONT_HERSHEY_SIMPLEX,font_scale,text_color,2)
        cv2.circle(frame,(int(finger_x),int(finger_y)),20,(255,0,255),-1)
        cv2.circle(frame,(int(finger_x),int(finger_y)),15,(255,0,255),4)
        cv2.circle(frame,(int(finger_x),int(finger_y)),5,(255,255,255),-1)
        if is_pressing:
            cv2.circle(frame,(int(finger_x),int(finger_y)),30,(0,255,0),5)
        z_color=(0,255,0) if is_pressing else (255,255,0)
        cv2.putText(frame,f"Z: {finger_z:.2f}",(int(finger_x)+20,int(finger_y)),cv2.FONT_HERSHEY_SIMPLEX,0.5,z_color,1)
        return frame

# ==================== RECOGNITION FUNCTIONS ====================

def normalize_stroke(points):
    points = np.array(points, dtype=np.float32)
    if len(points) < 2:
        return points
    centroid = points.mean(axis=0)
    points = points - centroid
    max_dist = np.max(np.linalg.norm(points, axis=1))
    if max_dist > 0:
        points = points / max_dist
    return points

def resample_stroke(points, n_points=64):
    points = np.array(points, dtype=np.float32)
    if len(points) < 2:
        return np.tile(points[0] if len(points) > 0 else [0, 0], (n_points, 1))
    distances = np.sqrt(((points[1:] - points[:-1]) ** 2).sum(axis=1))
    cumulative = np.insert(np.cumsum(distances), 0, 0)
    total_length = cumulative[-1]
    if total_length == 0:
        return np.tile(points[0], (n_points, 1))
    new_distances = np.linspace(0, total_length, n_points)
    new_points = []
    for d in new_distances:
        idx = np.searchsorted(cumulative, d)
        if idx >= len(points):
            idx = len(points) - 1
        new_points.append(points[idx])
    return np.array(new_points)

def extract_features(points):
    points = np.atleast_2d(points)
    features = []
    features.append(len(points))
    features.append(points[:, 0].mean())
    features.append(points[:, 1].mean())
    features.append(points[:, 0].std())
    features.append(points[:, 1].std())
    min_x, min_y = points.min(axis=0)
    max_x, max_y = points.max(axis=0)
    width, height = max_x - min_x, max_y - min_y
    features.extend([width, height, width / max(height, 1e-6)])
    path_length = np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1))
    features.append(path_length)
    area = width * height
    density = len(points) / max(area, 1e-6)
    features.append(density)
    if len(points) > 3:
        curvatures = []
        for i in range(2, len(points)):
            v1 = points[i-1] - points[i-2]
            v2 = points[i] - points[i-1]
            angle1 = np.arctan2(v1[1], v1[0])
            angle2 = np.arctan2(v2[1], v2[0])
            curvature = abs(angle2 - angle1)
            if curvature > np.pi:
                curvature = 2 * np.pi - curvature
            curvatures.append(curvature)
        curvatures = np.array(curvatures)
        features.extend([curvatures.mean(), curvatures.max(), curvatures.std()])
    else:
        features.extend([0, 0, 0])
    return np.array(features)

def dtw_distance(a, b):
    n, m = len(a), len(b)
    dtw = np.full((n + 1, m + 1), np.inf)
    dtw[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = np.linalg.norm(a[i-1] - b[j-1])
            dtw[i, j] = cost + min(dtw[i-1, j], dtw[i, j-1], dtw[i-1, j-1])
    return dtw[n, m]

def hybrid_predict(stroke):
    if not RECOGNITION_AVAILABLE or len(stroke) < 15:
        return None, 0.0
    try:
        norm = normalize_stroke(stroke)
        norm = resample_stroke(norm, 64)
        features = extract_features(norm).reshape(1, -1)
        probs = rf_model.predict_proba(features)[0]
        top_indices = np.argsort(probs)[::-1][:7]
        candidates = rf_model.classes_[top_indices]
        rf_confidence = probs[top_indices[0]]
        best_letter = None
        best_dist = np.inf
        all_distances = []
        for letter in candidates:
            if letter not in template_bank:
                continue
            for template in template_bank[letter]:
                d1 = dtw_distance(norm, template)
                d2 = dtw_distance(norm, template[::-1])
                dist = min(d1, d2)
                all_distances.append(dist)
                if dist < best_dist:
                    best_dist = dist
                    best_letter = letter
        if len(all_distances) > 1:
            avg_dist = np.mean(all_distances)
            dtw_confidence = max(0, 1 - (best_dist / (avg_dist + 1)))
        else:
            dtw_confidence = max(0, 1 - (best_dist / 50.0))
        final_confidence = 0.3 * rf_confidence + 0.7 * dtw_confidence
        return best_letter, final_confidence
    except Exception as e:
        log.error(f"Prediction error: {e}")
        return None, 0.0

# ==================== GESTURE DETECTION ====================

def count_fingers(landmarks):
    if not landmarks:
        return -1
    thumb_tip = landmarks[4]
    thumb_ip = landmarks[2]
    wrist = landmarks[0]
    index_tip = landmarks[8]
    index_pip = landmarks[6]
    index_mcp = landmarks[5]
    middle_tip = landmarks[12]
    middle_pip = landmarks[10]
    ring_tip = landmarks[16]
    ring_pip = landmarks[14]
    pinky_tip = landmarks[20]
    pinky_pip = landmarks[18]
    count = 0
    if index_tip.y < index_pip.y - 0.02:
        count += 1
    if middle_tip.y < middle_pip.y - 0.02:
        count += 1
    if ring_tip.y < ring_pip.y - 0.02:
        count += 1
    if pinky_tip.y < pinky_pip.y - 0.02:
        count += 1
    thumb_side_extended = abs(thumb_tip.x - thumb_ip.x) > 0.06
    if count == 4:
        if thumb_side_extended:
            count += 1
    else:
        if thumb_side_extended and abs(thumb_tip.x - wrist.x) > 0.12:
            count += 1
    if (index_tip.y > index_mcp.y and middle_tip.y > middle_pip.y and
        ring_tip.y > ring_pip.y and pinky_tip.y > pinky_pip.y and
        not thumb_side_extended):
        count = 0
    return count

def detect_named_gesture(landmarks):
    if not landmarks:
        return "unknown"
    thumb_tip = landmarks[4]
    thumb_ip = landmarks[2]
    index_tip = landmarks[8]
    index_pip = landmarks[6]
    index_mcp = landmarks[5]
    middle_tip = landmarks[12]
    middle_pip = landmarks[10]
    ring_tip = landmarks[16]
    ring_pip = landmarks[14]
    pinky_tip = landmarks[20]
    pinky_pip = landmarks[18]
    wrist = landmarks[0]

    index_up = index_tip.y < index_pip.y - 0.02
    middle_up = middle_tip.y < middle_pip.y - 0.02
    ring_up = ring_tip.y < ring_pip.y - 0.02
    pinky_up = pinky_tip.y < pinky_pip.y - 0.02
    fingers_up = index_up + middle_up + ring_up + pinky_up

    thumb_side_extended = abs(thumb_tip.x - thumb_ip.x) > 0.06
    thumb_palm_extended = abs(thumb_tip.x - thumb_ip.x) > 0.05
    thumb_up_clear = thumb_tip.y < thumb_ip.y - 0.02
    thumb_above_wrist = thumb_tip.y < wrist.y - 0.05
    thumb_tucked = abs(thumb_tip.x - thumb_ip.x) < 0.03 and not thumb_above_wrist

    # PALM
    if fingers_up == 4 and thumb_palm_extended and not thumb_above_wrist:
        return "palm"

    # THUMBS UP
    if thumb_above_wrist and fingers_up == 0 and not thumb_side_extended:
        max_finger_y = max(index_tip.y, middle_tip.y, ring_tip.y, pinky_tip.y)
        if thumb_tip.y < max_finger_y - 0.08:
            return "thumbs_up"

    # FIST
    if (index_tip.y > index_mcp.y + 0.02 and middle_tip.y > middle_pip.y + 0.02 and
        ring_tip.y > ring_pip.y + 0.02 and pinky_tip.y > pinky_pip.y + 0.02 and
        not thumb_side_extended and not thumb_up_clear and not thumb_above_wrist):
        return "fist"

    # OK SIGN
    def dist(p1, p2):
        return np.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)
    thumb_index_dist = dist(thumb_tip, index_tip)
    if thumb_index_dist < 0.08 and middle_up and ring_up and not index_up:
        return "ok"

    # PINKY
    if pinky_up and not index_up and not middle_up and not ring_up:
        return "pinky"

    # RING ONLY
    if ring_up and not index_up and not middle_up and not pinky_up:
        return "ring_only"

    # FOUR FINGERS (no thumb)
    if fingers_up == 4 and thumb_tucked:
        return "four_fingers"

    # ILY
    if thumb_side_extended and index_up and pinky_up and not middle_up and not ring_up:
        return "iloveyou"

    return "unknown"

def detect_mouse_gesture(landmarks):
    if not landmarks:
        return "none"
    lm = landmarks
    i_up = lm[8].y < lm[6].y
    m_up = lm[12].y < lm[10].y
    r_up = lm[16].y < lm[14].y
    p_up = lm[20].y < lm[18].y
    fingers = i_up + m_up + r_up + p_up
    if fingers == 1 and i_up and not m_up and not r_up and not p_up:
        return "index"
    elif fingers == 1 and r_up and not i_up and not m_up and not p_up:
        return "ring"
    elif fingers == 1 and p_up and not i_up and not m_up and not r_up:
        return "pinky"
    elif fingers == 0:
        return "fist"
    elif fingers == 2 and i_up and m_up:
        return "two"
    elif fingers == 3 and i_up and m_up and r_up:
        return "three"
    elif fingers == 4:
        return "palm"
    return "none"

# ==================== HANDOVER PROTOCOL ====================

class UserIdentifier:
    ROI_X1,ROI_X2=0.25,0.75
    ROI_Y1,ROI_Y2=0.45,0.82
    HUE_TOL=22; SAT_MIN=50; VAL_TOL=45; CALIB_SECS=3.0; HANDOVER_SECS=3.0
    def __init__(self):
        self.calibrated=False; self.authorized=False; self.locked=False
        self._hue=0.0; self._sat=0.0; self._val=0.0; self._achromatic=False
        self._fail_streak=0; self._pass_streak=0
        self._LOCK_AT=15; self._UNLOCK_AT=10
        self.handover_start=None; self.handover_active=False
    def _sample(self,frame):
        h,w=frame.shape[:2]
        x1,x2=int(w*self.ROI_X1),int(w*self.ROI_X2)
        y1,y2=int(h*self.ROI_Y1),int(h*self.ROI_Y2)
        roi=frame[y1:y2,x1:x2]
        if roi.size==0: return 0.0,0.0,0.0
        hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV).astype(np.float32)
        return float(np.mean(hsv[:,:,0])),float(np.mean(hsv[:,:,1])),float(np.mean(hsv[:,:,2]))
    def _roi_rect(self,frame):
        h,w=frame.shape[:2]
        return int(w*self.ROI_X1),int(h*self.ROI_Y1),int(w*self.ROI_X2),int(h*self.ROI_Y2)
    def calibrate(self,frame):
        h,s,v=self._sample(frame)
        self._hue,self._sat,self._val=h,s,v
        self._achromatic=(s<self.SAT_MIN)
        self.calibrated=True; self.authorized=True; self.locked=False
        self._fail_streak=0; self._pass_streak=self._UNLOCK_AT
        kind="achromatic" if self._achromatic else f"hue={h:.0f}"
        log.info(f"User locked in ({kind}, sat={s:.0f}, val={v:.0f})")
    def verify(self,frame):
        if not self.calibrated: return
        h,s,v=self._sample(frame)
        if self._achromatic:
            match=abs(v-self._val)<self.VAL_TOL
        else:
            diff=abs(h-self._hue)
            diff=min(diff,180.0-diff)
            match=(diff<self.HUE_TOL and s>=self.SAT_MIN*0.6)
        if match:
            self._fail_streak=0
            self._pass_streak=min(self._pass_streak+1,self._UNLOCK_AT+5)
            if self._pass_streak>=self._UNLOCK_AT:
                if self.locked: log.info("Original user recognised - unlocked")
                self.authorized=True; self.locked=False
        else:
            self._pass_streak=0
            self._fail_streak=min(self._fail_streak+1,self._LOCK_AT+5)
            if self._fail_streak>=self._LOCK_AT:
                if self.authorized: log.info("Unauthorized user - system locked")
                self.authorized=False; self.locked=True
    def update_handover_gesture(self,gesture_name,current_time):
        if gesture_name=="fist":
            if self.handover_start is None:
                self.handover_start=current_time
                self.handover_active=True
            return current_time-self.handover_start
        else:
            self.handover_start=None
            self.handover_active=False
            return 0.0
    def draw_roi(self,frame):
        if not self.calibrated:
            x1,y1,x2,y2=self._roi_rect(frame)
            cv2.rectangle(frame,(x1,y1),(x2,y2),(0,220,255),2)
            cv2.putText(frame,"SCAN ZONE",(x1+4,y1-8),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,220,255),1)
        else:
            label="READY" if self.authorized else "LOCKED"
            col=(0,200,80) if self.authorized else (0,0,220)
            cv2.putText(frame,label,(14,36),cv2.FONT_HERSHEY_DUPLEX,1.0,col,2)
    def draw_calibration_screen(self,frame,elapsed):
        h,w=frame.shape[:2]
        remaining=max(0.0,self.CALIB_SECS-elapsed)
        ov=frame.copy()
        cv2.rectangle(ov,(0,0),(w,h),(0,0,0),-1)
        cv2.addWeighted(ov,0.55,frame,0.45,0,frame)
        self.draw_roi(frame)
        cv2.putText(frame,"HANDOVER PROTOCOL",(w//2-195,h//2-110),cv2.FONT_HERSHEY_DUPLEX,1.2,(0,220,255),3)
        cv2.putText(frame,"Stand so your top fills the green box",(w//2-260,h//2-55),cv2.FONT_HERSHEY_SIMPLEX,0.78,(200,200,200),2)
        cv2.putText(frame,"Scanning colour signature...",(w//2-200,h//2-18),cv2.FONT_HERSHEY_SIMPLEX,0.70,(170,170,170),1)
        cv2.putText(frame,f"{remaining:.1f}",(w//2-38,h//2+80),cv2.FONT_HERSHEY_DUPLEX,3.5,(0,255,180),6)
        prog=min(1.0,elapsed/self.CALIB_SECS)
        bx1,bx2=120,w-120
        bw=int((bx2-bx1)*prog)
        cv2.rectangle(frame,(bx1,h//2+115),(bx2,h//2+135),(50,50,50),-1)
        cv2.rectangle(frame,(bx1,h//2+115),(bx1+bw,h//2+135),(0,255,180),-1)
    def draw_locked_screen(self,frame):
        h,w=frame.shape[:2]
        ov=frame.copy()
        cv2.rectangle(ov,(0,0),(w,h),(60,0,0),-1)
        cv2.addWeighted(ov,0.60,frame,0.40,0,frame)
        self.draw_roi(frame)
        cv2.putText(frame,"ACCESS LOCKED",(w//2-175,h//2-55),cv2.FONT_HERSHEY_DUPLEX,1.8,(0,0,255),4)
        cv2.putText(frame,"Unauthorized user detected",(w//2-205,h//2),cv2.FONT_HERSHEY_SIMPLEX,0.88,(100,100,255),2)
        cv2.putText(frame,"Original user: return to unlock automatically",(w//2-300,h//2+42),cv2.FONT_HERSHEY_SIMPLEX,0.72,(140,140,220),1)
        cv2.putText(frame,"Or: hold FIST for 3s to hand over to new user",(w//2-305,h//2+72),cv2.FONT_HERSHEY_SIMPLEX,0.68,(120,120,180),1)
        cv2.putText(frame,"U key = force recalibrate now",(w//2-175,h//2+102),cv2.FONT_HERSHEY_SIMPLEX,0.60,(90,90,140),1)
    def draw_handover_progress(self,frame,elapsed):
        h,w=frame.shape[:2]
        remaining=max(0.0,self.HANDOVER_SECS-elapsed)
        prog=min(1.0,elapsed/self.HANDOVER_SECS)
        cx=w//2
        bw=int(380*prog)
        cv2.rectangle(frame,(cx-190,h-78),(cx+190,h-54),(40,40,40),-1)
        cv2.rectangle(frame,(cx-190,h-78),(cx-190+bw,h-54),(0,200,255),-1)
        cv2.putText(frame,f"HANDOVER: hold FIST  {remaining:.1f}s remaining",(cx-230,h-84),cv2.FONT_HERSHEY_SIMPLEX,0.62,(0,200,255),2)

# ==================== 3D STL EXPORT (REAL MESH) - FIXED ====================

def save_drawing_as_stl(img, filepath, height=2.0, downsample=4):
    """
    Convert a binary drawing (non‑black pixels) into an STL mesh.
    img: 3‑channel BGR image (background black, drawing in any colour).
    height: extrusion height in model units.
    downsample: scale factor (1 = original resolution, 4 = 1/4 size).
    FIX: Uses any non‑zero pixel in grayscale, not a fixed threshold of 10.
    """
    if img is None or img.size == 0:
        return False
    # Convert to grayscale and threshold – any pixel > 0 is part of the drawing
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = (gray > 0).astype(np.uint8)   # FIXED: used to be threshold 10
    
    # Downsample to reduce vertex count
    h, w = binary.shape
    new_w = w // downsample
    new_h = h // downsample
    if new_w < 2 or new_h < 2:
        new_w, new_h = w, h
    binary_small = cv2.resize(binary, (new_w, new_h), interpolation=cv2.INTER_AREA)
    binary_small = (binary_small > 0.5).astype(np.uint8)

    # Build vertex and face lists
    vertices = []
    faces = []
    vertex_map = {}  # (x, y, z) -> index
    vertex_list = []
    def add_vertex(x, y, z):
        key = (x, y, z)
        if key not in vertex_map:
            vertex_map[key] = len(vertex_list)
            vertex_list.append((x, y, z))
        return vertex_map[key]

    # For each drawn pixel, create a small cube (8 vertices, 12 triangles)
    step_x = 1.0
    step_y = 1.0
    offset_x = - (new_w - 1) / 2.0
    offset_y = - (new_h - 1) / 2.0

    for i in range(new_h):
        for j in range(new_w):
            if binary_small[i, j] == 0:
                continue
            x0 = (j + 0) * step_x + offset_x
            x1 = (j + 1) * step_x + offset_x
            y0 = (i + 0) * step_y + offset_y
            y1 = (i + 1) * step_y + offset_y
            z0 = 0.0
            z1 = height
            # 8 vertices
            v0 = add_vertex(x0, y0, z0)
            v1 = add_vertex(x1, y0, z0)
            v2 = add_vertex(x1, y1, z0)
            v3 = add_vertex(x0, y1, z0)
            v4 = add_vertex(x0, y0, z1)
            v5 = add_vertex(x1, y0, z1)
            v6 = add_vertex(x1, y1, z1)
            v7 = add_vertex(x0, y1, z1)
            # Bottom face (z=0)
            faces.append([v0, v1, v2])
            faces.append([v0, v2, v3])
            # Top face (z=height)
            faces.append([v4, v6, v5])
            faces.append([v4, v7, v6])
            # Front face (y=y0)
            faces.append([v0, v4, v5])
            faces.append([v0, v5, v1])
            # Back face (y=y1)
            faces.append([v3, v2, v6])
            faces.append([v3, v6, v7])
            # Left face (x=x0)
            faces.append([v0, v3, v7])
            faces.append([v0, v7, v4])
            # Right face (x=x1)
            faces.append([v1, v5, v6])
            faces.append([v1, v6, v2])

    # Write STL (binary for compactness)
    with open(filepath, 'wb') as f:
        # Write 80‑byte header
        f.write(b"3D model of drawing\x00" * 4)
        # Number of triangles (uint32)
        num_tri = len(faces)
        f.write(num_tri.to_bytes(4, byteorder='little'))
        # For each triangle, write normal (ignored) + 3 vertices + attribute (0)
        for tri in faces:
            # Calculate normal (simple average of vertices)
            v0 = vertex_list[tri[0]]
            v1 = vertex_list[tri[1]]
            v2 = vertex_list[tri[2]]
            # Compute face normal (cross product of edges)
            u = (v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2])
            v = (v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2])
            nx = u[1]*v[2] - u[2]*v[1]
            ny = u[2]*v[0] - u[0]*v[2]
            nz = u[0]*v[1] - u[1]*v[0]
            # Normalise
            norm = math.sqrt(nx*nx + ny*ny + nz*nz)
            if norm > 0:
                nx /= norm; ny /= norm; nz /= norm
            # Write normal as 4 floats (little endian)
            f.write(np.array([nx, ny, nz], dtype=np.float32).tobytes())
            # Write vertices
            for vtx in (v0, v1, v2):
                f.write(np.array([vtx[0], vtx[1], vtx[2]], dtype=np.float32).tobytes())
            # Write attribute byte count (0)
            f.write(b"\x00\x00")
    return True

# ==================== 3D TEXTURED OBJ EXPORT (COLOURED) ====================

def save_drawing_as_textured_obj(img, base_filepath_no_ext, height=2.0, downsample=4):
    """
    Exports the drawing as a textured 3D model using OBJ+MTL+PNG.
    - base_filepath_no_ext: path without extension (e.g. "data/drawings/drawing_20250101_120000")
    - height: extrusion height (z)
    - downsample: resolution reduction factor (4 = 1/4 size)
    Generates three files:
        .obj (geometry with UVs)
        .mtl (material referencing texture)
        .png (texture image of the drawing)
    """
    if img is None or img.size == 0:
        return False
    h, w = img.shape[:2]
    new_w = w // downsample
    new_h = h // downsample
    if new_w < 2 or new_h < 2:
        new_w, new_h = w, h
    img_small = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    # Save texture PNG (colour image of the drawing)
    tex_path = f"{base_filepath_no_ext}.png"
    cv2.imwrite(tex_path, img_small)
    
    # Create binary mask for extruded pixels (any non‑black pixel)
    gray = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
    binary = (gray > 0).astype(np.uint8)
    
    step_x = 1.0
    step_y = 1.0
    offset_x = - (new_w - 1) / 2.0
    offset_y = - (new_h - 1) / 2.0
    
    vertices = []          # list of (x,y,z)
    uvs = []               # list of (u,v)
    faces = []             # each face = (v1,v2,v3, uv1,uv2,uv3)
    vertex_index_map = {}  # (x,y,z) -> index
    uv_index_map = {}      # (u,v) -> index
    
    def get_vertex_index(x, y, z):
        key = (round(x,6), round(y,6), round(z,6))
        if key not in vertex_index_map:
            vertex_index_map[key] = len(vertices)
            vertices.append((x, y, z))
        return vertex_index_map[key]
    
    def get_uv_index(u, v):
        key = (round(u,6), round(v,6))
        if key not in uv_index_map:
            uv_index_map[key] = len(uvs)
            uvs.append((u, v))
        return uv_index_map[key]
    
    # For each drawn pixel, create two triangles on the top face (z=height) with UV mapping
    for i in range(new_h):
        for j in range(new_w):
            if binary[i, j] == 0:
                continue
            x0 = j * step_x + offset_x
            x1 = (j+1) * step_x + offset_x
            y0 = i * step_y + offset_y
            y1 = (i+1) * step_y + offset_y
            z = height
            # UV coordinates: u = j/(new_w-1), v = 1 - i/(new_h-1)
            u0 = j / (new_w - 1) if new_w > 1 else 0
            u1 = (j+1) / (new_w - 1) if new_w > 1 else 1
            v0 = 1.0 - (i / (new_h - 1)) if new_h > 1 else 0
            v1 = 1.0 - ((i+1) / (new_h - 1)) if new_h > 1 else 1
            # Four vertices of the top quad
            v00 = get_vertex_index(x0, y0, z)
            v10 = get_vertex_index(x1, y0, z)
            v11 = get_vertex_index(x1, y1, z)
            v01 = get_vertex_index(x0, y1, z)
            # UV indices
            uv00 = get_uv_index(u0, v0)
            uv10 = get_uv_index(u1, v0)
            uv11 = get_uv_index(u1, v1)
            uv01 = get_uv_index(u0, v1)
            # Two triangles
            faces.append((v00, v10, v11, uv00, uv10, uv11))
            faces.append((v00, v11, v01, uv00, uv11, uv01))
    
    # Write OBJ file
    obj_path = f"{base_filepath_no_ext}.obj"
    with open(obj_path, 'w') as f:
        f.write(f"mtllib {os.path.basename(base_filepath_no_ext)}.mtl\n")
        f.write("o DrawingExtruded\n")
        # Write vertices
        for v in vertices:
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")
        # Write UVs
        for uv in uvs:
            f.write(f"vt {uv[0]} {uv[1]}\n")
        # Write faces
        f.write("usemtl drawingTexture\n")
        for (v1,v2,v3, uv1,uv2,uv3) in faces:
            f.write(f"f {v1+1}/{uv1+1} {v2+1}/{uv2+1} {v3+1}/{uv3+1}\n")
    
    # Write MTL file
    mtl_path = f"{base_filepath_no_ext}.mtl"
    with open(mtl_path, 'w') as f:
        f.write("newmtl drawingTexture\n")
        f.write("Ka 1.0 1.0 1.0\n")
        f.write("Kd 1.0 1.0 1.0\n")
        f.write("Ks 0.0 0.0 0.0\n")
        f.write(f"map_Kd {os.path.basename(base_filepath_no_ext)}.png\n")
    
    log.info(f"Textured OBJ saved: {obj_path} + {mtl_path} + {tex_path}")
    return True

# ==================== MAIN APPLICATION ====================

class App:
    def __init__(self):
        self.user_id = UserIdentifier()
        self.mode = "MAIN"
        self.paused = False
        self.pause_needs_palm = False
        self.canvas = np.zeros((CANVAS_SIZE[0], CANVAS_SIZE[1], 3), dtype=np.uint8)
        self.stroke = []
        self.colors = [
            (0,0,0), (255,255,255), (128,128,128), (192,192,192),
            (0,0,128), (0,0,255), (0,128,128), (0,255,255),
            (0,100,0), (0,255,0), (128,128,0), (255,255,0),
            (128,0,0), (255,0,0), (128,0,128), (255,0,255),
            (0,165,255), (0,247,255), (112,128,144), (70,139,34),
        ]
        self.color_names = ["Black","White","Grey","Silver","Maroon","Red","Olive","Yellow",
                            "Dark Green","Green","Teal","Cyan","Navy Blue","Blue","Purple","Magenta",
                            "Old Gold","Lemon Yellow","Slate Grey","Kelly Green"]
        self.color_index = 0
        self.typed = ""
        self.last_rec_time = 0
        self.last_motion_time = time.time()
        self.cursor_buffer = deque(maxlen=5)
        self.prev_mouse_x = SCREEN_W//2
        self.prev_mouse_y = SCREEN_H//2
        self.last_scroll_time = 0
        self.is_dragging = False
        self.osk = None
        if WIN32_AVAILABLE:
            try: self.osk = OSKKeyboard()
            except Exception as e: log.error(f"OSK init failed: {e}")
        self.osk_window_ready = False
        self.osk_finger_x = SCREEN_W//2
        self.osk_finger_y = SCREEN_H//2
        self.osk_finger_z = 0.5
        self.using_eraser = False
        self.draw_window_ready = False
        self.draw_overlay_canvas = None
        self.draw_prev_pt = None
        self.draw_finger_x = SCREEN_W//2
        self.draw_finger_y = SCREEN_H//2
        self.draw_buf = deque(maxlen=3)
        self.draw_smooth_x = SCREEN_W//2
        self.draw_smooth_y = SCREEN_H//2
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.5)
        
        # ---- TUNABLE STABILITY ----
        self.gesture_history = deque(maxlen=35)
        self.finger_history = deque(maxlen=35)
        self.stability_threshold = 0.8
        self.global_cooldown = 0.5
        self.last_action_global = 0
        
        self.last_action_time = 0
        self.music_mode_entered_time = 0
        self.music_grace_period = 1.5
        self.song_mode_entered_time = 0
        self.song_grace_period = 0.8
        self.key_buffer = ""
        self.last_easter_time = 0
        self.exit_start_time = None
        self.exit_program = False

        # Instrument / song selection state
        self.selected_instrument = None
        self.waiting_for_mode_choice = False
        self.song_select_instrument = None
        self.song_list = []
        self.song_index = 0
        self.last_swipe_time = 0
        self.swipe_cooldown = 0.3

        # UI settings
        self.ui_opacity = 0.6
        self.font_scale = 0.55
        self.show_skeleton = True
        self.mirror = True
        self.sound_feedback = True
        self.show_gesture_hints = True
        self.show_fps = False

        # FPS counter
        self.fps_timer = time.time()
        self.frame_count = 0
        self.current_fps = 0

        # Load saved settings
        self.load_settings()

        log.info("App initialized (DRAW: REAL 3D STL + textured OBJ export)")

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            self.ui_opacity = settings.get('ui_opacity', 0.6)
            self.font_scale = settings.get('font_scale', 0.55)
            self.show_skeleton = settings.get('show_skeleton', True)
            self.mirror = settings.get('mirror', True)
            self.sound_feedback = settings.get('sound_feedback', True)
            self.show_gesture_hints = settings.get('show_gesture_hints', True)
            self.stability_threshold = settings.get('stability_threshold', 0.8)
            self.global_cooldown = settings.get('global_cooldown', 0.5)
            log.info("Settings loaded")
        except:
            log.info("No saved settings, using defaults")

    def save_settings(self):
        settings = {
            'ui_opacity': self.ui_opacity,
            'font_scale': self.font_scale,
            'show_skeleton': self.show_skeleton,
            'mirror': self.mirror,
            'sound_feedback': self.sound_feedback,
            'show_gesture_hints': self.show_gesture_hints,
            'stability_threshold': self.stability_threshold,
            'global_cooldown': self.global_cooldown
        }
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            log.info("Settings saved")
        except Exception as e:
            log.error(f"Failed to save settings: {e}")

    def reset_calibrations(self):
        self.user_id.calibrated = False
        self.user_id.authorized = False
        self.user_id.locked = False
        self.user_id._fail_streak = 0
        self.user_id._pass_streak = 0
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    s = json.load(f)
                if 'custom_gesture_thresholds' in s:
                    del s['custom_gesture_thresholds']
                with open(SETTINGS_FILE, 'w') as f:
                    json.dump(s, f, indent=2)
        except:
            pass
        log.info("All calibrations reset.")
        if self.sound_feedback:
            beep()

    def get_stable(self, history, current_value):
        if current_value == -1 or current_value == "unknown":
            return None if isinstance(current_value, str) else -1
        history.append(current_value)
        if len(history) < history.maxlen:
            return None if isinstance(current_value, str) else -1
        count = sum(1 for v in history if v == current_value)
        if count / history.maxlen >= self.stability_threshold:
            return current_value
        return None if isinstance(current_value, str) else -1

    def can_act(self):
        return time.time() - self.last_action_global >= self.global_cooldown

    def move_mouse(self, hand_x, hand_y):
        if not PYAUTOGUI_AVAILABLE: return
        target_x = int(hand_x * SCREEN_W)
        target_y = int(hand_y * SCREEN_H)
        self.cursor_buffer.append((target_x, target_y))
        avg_x = sum(p[0] for p in self.cursor_buffer)/len(self.cursor_buffer)
        avg_y = sum(p[1] for p in self.cursor_buffer)/len(self.cursor_buffer)
        smooth_x = int(0.7*avg_x + 0.3*self.prev_mouse_x)
        smooth_y = int(0.7*avg_y + 0.3*self.prev_mouse_y)
        smooth_x = max(0, min(SCREEN_W-1, smooth_x))
        smooth_y = max(0, min(SCREEN_H-1, smooth_y))
        self.prev_mouse_x, self.prev_mouse_y = smooth_x, smooth_y
        pyautogui.moveTo(smooth_x, smooth_y)

    def _save_anaglyph_3d(self, img, path):
        if img is None or img.size == 0:
            return
        h, w = img.shape[:2]
        shift = 8
        red = img[:, :, 2].copy()
        red_shifted = np.zeros_like(red)
        if shift < w:
            red_shifted[:, :w-shift] = red[:, shift:]
        cyan = np.zeros((h, w, 2), dtype=np.uint8)
        cyan[:, :, 0] = img[:, :, 1]
        cyan[:, :, 1] = img[:, :, 0]
        cyan_shifted = np.zeros_like(cyan)
        if shift < w:
            cyan_shifted[:, shift:, :] = cyan[:, :w-shift, :]
        anaglyph = np.zeros((h, w, 3), dtype=np.uint8)
        anaglyph[:, :, 2] = red_shifted
        anaglyph[:, :, 1] = cyan_shifted[:, :, 0]
        anaglyph[:, :, 0] = cyan_shifted[:, :, 1]
        cv2.imwrite(path, anaglyph)

    def _launch_song_mode(self, song_data):
        if hasattr(self, 'camera_mgr'):
            self.camera_mgr.release_all()
        cv2.destroyAllWindows()
        time.sleep(0.5)
        instrument = song_data['instrument']
        temp_json = os.path.join(SONGS_DIR, "_temp_song.json")
        with open(temp_json, 'w') as f:
            json.dump({
                "title": song_data['title'],
                "bpm": song_data['bpm'],
                "tracks": [{"hand": "right", "notes": song_data['notes']}]
            }, f)
        if instrument == 'piano':
            from piano_FINALv4 import run_song_mode
            run_song_mode(temp_json)
        elif instrument == 'guitar':
            from guitar_FINALv4 import run_song_mode
            run_song_mode(temp_json)
        elif instrument == 'violin':
            from violin_REFACTOREDv2 import run_song_mode
            run_song_mode(temp_json)
        else:
            log.error(f"Unknown instrument: {instrument}")
        try: os.remove(temp_json)
        except: pass
        time.sleep(0.5)
        self.needs_camera_reinit = True

    def run(self):
        camera_mgr = CameraManager()
        self.camera_mgr = camera_mgr
        if not camera_mgr.detect_cameras(): log.error("No cameras found!"); return
        if not camera_mgr.select_cameras(): log.error("Camera selection failed!"); return
        if not camera_mgr.open_cameras(): log.error("Failed to open cameras!"); return

        print("\n"+"="*70)
        print("AIR GESTURE SYSTEM v3.8 - REAL 3D STL + COLORED OBJ Export")
        print("="*70)
        print("\nDRAW mode (3 fingers):")
        print("  Saves: 2D PNG + Anaglyph PNG + STL (monochrome) + OBJ/MTL/PNG (coloured)")
        print("  The OBJ+MTL+PNG model preserves the original drawing colours (texture).")
        print("  All files are saved in data/drawings/")
        print("\nMODES, shortcuts and all other features unchanged.\n")
        print("="*70+"\n")

        startup_sound = resource_path(os.path.join("assets","start.mp3"))
        if os.path.exists(startup_sound): play_sound(startup_sound)

        # Handover calibration
        log.info("Handover Protocol: stand so your top fills the green box...")
        calib_start = time.time()
        while True:
            frames = camera_mgr.read_frames()
            frame = camera_mgr.combine_frames(frames)
            if frame is None: continue
            if self.mirror:
                frame = cv2.flip(frame,1)
            elapsed = time.time() - calib_start
            self.user_id.draw_calibration_screen(frame, elapsed)
            cv2.imshow("Air Gesture System v3.1", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                camera_mgr.release_all(); cv2.destroyAllWindows(); return
            if elapsed >= UserIdentifier.CALIB_SECS:
                self.user_id.calibrate(frame)
                log.info("Handover Protocol: ready.")
                break

        self.needs_camera_reinit = False

        try:
            while True:
                if self.needs_camera_reinit:
                    camera_mgr.release_all()
                    time.sleep(0.5)
                    if not camera_mgr.open_cameras():
                        log.warning("Failed to reopen camera after song mode")
                    self.needs_camera_reinit = False

                # FPS calculation
                self.frame_count += 1
                if time.time() - self.fps_timer >= 1.0:
                    self.current_fps = self.frame_count
                    self.frame_count = 0
                    self.fps_timer = time.time()

                frames = camera_mgr.read_frames()
                frame = camera_mgr.combine_frames(frames)
                if frame is None: continue
                if self.mirror:
                    frame = cv2.flip(frame,1)
                h,w = frame.shape[:2]
                self.user_id.verify(frame)
                self.user_id.draw_roi(frame)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.hands.process(rgb)

                finger_count = -1
                named_gesture = "unknown"
                tip = None

                if results.multi_hand_landmarks:
                    for hand_landmarks in results.multi_hand_landmarks:
                        if self.show_skeleton:
                            self.mp_drawing.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                        raw_finger = count_fingers(hand_landmarks.landmark)
                        raw_gesture = detect_named_gesture(hand_landmarks.landmark)
                        tip = hand_landmarks.landmark[8]
                        stable_finger = self.get_stable(self.finger_history, raw_finger)
                        stable_gesture = self.get_stable(self.gesture_history, raw_gesture)
                        finger_count = stable_finger if stable_finger != -1 else raw_finger
                        named_gesture = stable_gesture if stable_gesture is not None else raw_gesture

                # Debug raw values on screen
                if tip is not None:
                    x = int(tip.x * w)
                    y = int(tip.y * h)
                    cx = int((x/w)*CANVAS_SIZE[1])
                    cy = int((y/h)*CANVAS_SIZE[0])
                    cx = np.clip(cx, 0, CANVAS_SIZE[1]-1)
                    cy = np.clip(cy, 0, CANVAS_SIZE[0]-1)
                    cv2.putText(frame, f"Raw fingers: {raw_finger}", (20, h-180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,255), 1)
                    cv2.putText(frame, f"Raw gesture: {raw_gesture}", (20, h-150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,255), 1)
                else:
                    x = y = cx = cy = 0

                current_time = time.time()

                # ---- DRAW mode eraser ----
                if self.mode == "DRAW" and named_gesture == "pinky":
                    self.using_eraser = True
                elif self.mode == "DRAW":
                    self.using_eraser = False

                # ---- Handover gesture tracking ----
                ho_elapsed = self.user_id.update_handover_gesture(named_gesture, current_time)

                # ---- Locked state ----
                if self.user_id.locked:
                    if ho_elapsed > 0:
                        self.user_id.draw_handover_progress(frame, ho_elapsed)
                        if ho_elapsed >= UserIdentifier.HANDOVER_SECS:
                            self.user_id.handover_start = None
                            self.user_id.handover_active = False
                            calib_s2 = time.time()
                            log.info("Handover Protocol: initiating handover calibration...")
                            while True:
                                f2 = camera_mgr.combine_frames(camera_mgr.read_frames())
                                if f2 is None: continue
                                if self.mirror: f2 = cv2.flip(f2,1)
                                e2 = time.time() - calib_s2
                                self.user_id.draw_calibration_screen(f2, e2)
                                cv2.imshow("Air Gesture System v3.1", f2)
                                cv2.waitKey(1)
                                if e2 >= UserIdentifier.CALIB_SECS:
                                    self.user_id.calibrate(f2)
                                    log.info("Handover Protocol: new user locked in")
                                    break
                    self.user_id.draw_locked_screen(frame)
                    cv2.imshow("Air Gesture System v3.1", frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27 or self.exit_program: break
                    elif key in (ord('u'), ord('U')): self.user_id.calibrate(frame); log.info("Force recalibrated")
                    # UI keys in locked state
                    if key in (ord('h'), ord('H')): self.show_skeleton = not self.show_skeleton
                    elif key in (ord('m'), ord('M')): self.mirror = not self.mirror
                    elif key in (ord('s'), ord('S')): self.sound_feedback = not self.sound_feedback
                    elif key in (ord('g'), ord('G')): self.show_gesture_hints = not self.show_gesture_hints
                    elif key == ord('=') or key == ord('+'): self.ui_opacity = min(1.0, self.ui_opacity + 0.05)
                    elif key == ord('-') or key == ord('_'): self.ui_opacity = max(0.2, self.ui_opacity - 0.05)
                    elif key == ord('f') or key == ord('F'): self.show_fps = not self.show_fps
                    elif key == ord('v') or key == ord('V'): self.reset_calibrations()
                    continue

                # ---- Voluntary handover from MAIN ----
                if self.mode == "MAIN" and ho_elapsed > 0:
                    self.user_id.draw_handover_progress(frame, ho_elapsed)
                    if ho_elapsed >= UserIdentifier.HANDOVER_SECS:
                        self.user_id.handover_start = None
                        self.user_id.handover_active = False
                        calib_s3 = time.time()
                        log.info("Handover Protocol: voluntary handover initiated...")
                        while True:
                            f3 = camera_mgr.combine_frames(camera_mgr.read_frames())
                            if f3 is None: continue
                            if self.mirror: f3 = cv2.flip(f3,1)
                            e3 = time.time() - calib_s3
                            self.user_id.draw_calibration_screen(f3, e3)
                            cv2.imshow("Air Gesture System v3.1", f3)
                            cv2.waitKey(1)
                            if e3 >= UserIdentifier.CALIB_SECS:
                                self.user_id.calibrate(f3)
                                log.info("Handover Protocol: new user locked in")
                                break

                # ---- ILY exit gesture ----
                if named_gesture == "iloveyou":
                    if self.exit_start_time is None:
                        self.exit_start_time = current_time
                    else:
                        elapsed = current_time - self.exit_start_time
                        remaining = EXIT_HOLD_TIME - elapsed
                        if remaining > 0 and tip is not None:
                            cx_hand = int(tip.x * w)
                            cy_hand = int(tip.y * h)
                            radius = 40
                            cv2.circle(frame, (cx_hand, cy_hand), radius, (0,0,255), 2)
                            angle = (1.0 - elapsed/EXIT_HOLD_TIME) * 360
                            start_angle = -90
                            end_angle = start_angle + angle
                            cv2.ellipse(frame, (cx_hand, cy_hand), (radius, radius), 0, start_angle, end_angle, (0,255,0), 4)
                            cv2.putText(frame, f"{int(remaining*10)/10}s", (cx_hand-20, cy_hand+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
                        if elapsed >= EXIT_HOLD_TIME:
                            exit_sound = resource_path(os.path.join("assets","exit.mp3"))
                            if os.path.exists(exit_sound): play_sound(exit_sound)
                            log.info("ILY exit gesture - Goodbye!")
                            self.exit_program = True
                elif named_gesture != "iloveyou" and not self.paused:
                    self.exit_start_time = None

                # ---- Global pause/unpause ----
                if (named_gesture == "fist" and not self.paused and self.mode != "MOUSE" and
                    self.can_act()):
                    if self.mode == "MUSIC":
                        time_in_music = current_time - self.music_mode_entered_time
                        if time_in_music < self.music_grace_period:
                            pass
                        else:
                            self.paused = True
                            self.pause_needs_palm = True
                            log.info("PAUSED")
                            if self.sound_feedback: beep()
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                    else:
                        self.paused = True
                        self.pause_needs_palm = True
                        log.info("PAUSED")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                elif self.paused and named_gesture == "palm":
                    self.paused = False
                    self.pause_needs_palm = False
                    log.info("RESUMED")
                    if self.sound_feedback: beep()
                    self.last_action_time = current_time
                    self.last_action_global = current_time

                # ---- Palm to MAIN ----
                if (named_gesture == "palm" and self.mode != "MAIN" and not self.paused and
                    self.can_act()):
                    if self.mode == "INSTRUMENT_CHOICE":
                        self.waiting_for_mode_choice = False
                        self.selected_instrument = None
                        self.mode = "MUSIC"
                        log.info("-> MUSIC (cancelled)")
                        if self.sound_feedback: beep()
                    elif self.mode == "SONG_SELECT":
                        self.mode = "INSTRUMENT_CHOICE"
                        log.info("-> Back to instrument choice")
                        if self.sound_feedback: beep()
                    else:
                        self.mode = "MAIN"
                        if self.sound_feedback: beep()
                    self.canvas.fill(0)
                    self.stroke = []
                    self.using_eraser = False
                    self.draw_prev_pt = None
                    self.draw_buf.clear()
                    if self.draw_window_ready:
                        try: cv2.destroyWindow("Air Gesture Draw")
                        except: pass
                        self.draw_window_ready = False
                        self.draw_overlay_canvas = None
                    if self.is_dragging and PYAUTOGUI_AVAILABLE:
                        pyautogui.mouseUp()
                        self.is_dragging = False
                    self.last_action_time = current_time
                    self.last_action_global = current_time

                # ---- Mode switching from MAIN (cooldown 1.5s) ----
                if (self.mode == "MAIN" and current_time - self.last_action_time > 1.5 and
                    not self.paused and self.can_act()):
                    if named_gesture == "thumbs_up":
                        self.mode = "MUSIC"
                        self.music_mode_entered_time = current_time
                        log.info("-> MUSIC")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                    elif named_gesture == "ok":
                        self.mode = "GESTURE"
                        log.info("-> GESTURE")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                    elif finger_count == 1:
                        self.mode = "DRAW"
                        self.canvas.fill(0)
                        log.info("-> DRAW")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                    elif finger_count == 2:
                        self.mode = "WRITE"
                        self.canvas.fill(0)
                        self.typed = ""
                        log.info("-> WRITE")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                    elif finger_count == 3:
                        self.mode = "MOUSE"
                        log.info("-> MOUSE")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                    elif finger_count == 4:
                        self.mode = "OSK"
                        log.info("-> OSK")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time

                # ---- MUSIC mode – choose instrument ----
                if (self.mode == "MUSIC" and finger_count != -1 and
                    current_time - self.last_action_time > 1.0 and not self.paused and self.can_act()):
                    if finger_count == 1:
                        self.selected_instrument = "piano"
                        self.waiting_for_mode_choice = True
                        self.mode = "INSTRUMENT_CHOICE"
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                        log.info("Chose Piano.")
                        if self.sound_feedback: beep()
                    elif finger_count == 2:
                        self.selected_instrument = "guitar"
                        self.waiting_for_mode_choice = True
                        self.mode = "INSTRUMENT_CHOICE"
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                        log.info("Chose Guitar.")
                        if self.sound_feedback: beep()
                    elif finger_count == 3:
                        self.selected_instrument = "violin"
                        self.waiting_for_mode_choice = True
                        self.mode = "INSTRUMENT_CHOICE"
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                        log.info("Chose Violin.")
                        if self.sound_feedback: beep()

                # ---- INSTRUMENT_CHOICE mode ----
                if (self.mode == "INSTRUMENT_CHOICE" and named_gesture != "unknown" and
                    not self.paused and self.can_act()):
                    if named_gesture == "thumbs_up":
                        camera_mgr.release_all()
                        cv2.destroyAllWindows()
                        launch_music(self.selected_instrument)
                        camera_mgr.open_cameras()
                        self.mode = "MAIN"
                        self.waiting_for_mode_choice = False
                        self.selected_instrument = None
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                    elif named_gesture == "ok":
                        self.song_select_instrument = self.selected_instrument
                        all_json = glob.glob(os.path.join(SONGS_DIR, "*.json"))
                        self.song_list = []
                        for path in all_json:
                            song_data = load_song_metadata(path, default_instrument=self.selected_instrument)
                            if song_data and song_data['instrument'] == self.selected_instrument:
                                self.song_list.append((path, song_data['title'], song_data))
                        if not self.song_list:
                            print(f"No playable songs for {self.selected_instrument}.")
                            self.mode = "INSTRUMENT_CHOICE"
                            continue
                        self.song_index = 0
                        self.mode = "SONG_SELECT"
                        self.song_mode_entered_time = current_time
                        log.info(f"Entered song selection for {self.selected_instrument}")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time
                    elif named_gesture == "palm":
                        self.waiting_for_mode_choice = False
                        self.selected_instrument = None
                        self.mode = "MUSIC"
                        log.info("Cancelled instrument choice")
                        if self.sound_feedback: beep()
                        self.last_action_time = current_time
                        self.last_action_global = current_time

                # ---- SONG SELECT mode ----
                if self.mode == "SONG_SELECT" and named_gesture != "unknown" and not self.paused:
                    in_grace = (current_time - self.song_mode_entered_time) < self.song_grace_period
                    if not in_grace and self.can_act():
                        if named_gesture == "ok":
                            if self.song_list:
                                _, _, song_data = self.song_list[self.song_index]
                                self._launch_song_mode(song_data)
                                self.mode = "MAIN"
                                self.needs_camera_reinit = True
                                self.last_action_time = current_time
                                self.last_action_global = current_time
                        elif named_gesture == "palm":
                            self.mode = "INSTRUMENT_CHOICE"
                            log.info("Back to instrument choice")
                            if self.sound_feedback: beep()
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif finger_count == 2:
                            if not hasattr(self, 'swipe_start_x'):
                                self.swipe_start_x = tip.x if tip else 0
                                self.swipe_start_time = current_time
                            else:
                                dx = (tip.x if tip else 0) - self.swipe_start_x
                                if dx > 0.1 and (current_time - self.swipe_start_time) < 0.5 and current_time - self.last_swipe_time > self.swipe_cooldown:
                                    self.song_index = (self.song_index + 1) % len(self.song_list)
                                    self.last_swipe_time = current_time
                                    print(f"Next: {self.song_list[self.song_index][1]}")
                                    self.swipe_start_x = None
                                else:
                                    self.swipe_start_x = None
                        elif finger_count == 3:
                            if not hasattr(self, 'swipe_start_x'):
                                self.swipe_start_x = tip.x if tip else 0
                                self.swipe_start_time = current_time
                            else:
                                dx = (tip.x if tip else 0) - self.swipe_start_x
                                if dx < -0.1 and (current_time - self.swipe_start_time) < 0.5 and current_time - self.last_swipe_time > self.swipe_cooldown:
                                    self.song_index = (self.song_index - 1) % len(self.song_list)
                                    self.last_swipe_time = current_time
                                    print(f"Previous: {self.song_list[self.song_index][1]}")
                                    self.swipe_start_x = None
                                else:
                                    self.swipe_start_x = None
                        else:
                            self.swipe_start_x = None
                    else:
                        if named_gesture == "palm":
                            self.mode = "INSTRUMENT_CHOICE"
                            log.info("Back to instrument choice (during grace)")
                            if self.sound_feedback: beep()
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        grace_remaining = self.song_grace_period - (current_time - self.song_mode_entered_time)
                        cv2.putText(frame, f"Grace: {grace_remaining:.1f}s", (20, h-50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,255), 2)

                # ---- OSK mode ----
                if self.mode == "OSK" and not self.paused and self.osk and WIN32_AVAILABLE and tip is not None:
                    self.osk_finger_x = int(tip.x * self.osk.screen_w)
                    self.osk_finger_y = int(tip.y * self.osk.screen_h)
                    self.osk_finger_z = tip.z
                    self.osk.update(self.osk_finger_x, self.osk_finger_y, self.osk_finger_z)

                # ---- DRAW mode (with 2D + Anaglyph + STL + textured OBJ) ----
                if self.mode == "DRAW" and not self.paused and tip is not None:
                    raw_x = int(tip.x * SCREEN_W)
                    raw_y = int(tip.y * SCREEN_H)
                    self.draw_buf.append((raw_x, raw_y))
                    avg_x = sum(p[0] for p in self.draw_buf)/len(self.draw_buf)
                    avg_y = sum(p[1] for p in self.draw_buf)/len(self.draw_buf)
                    scr_x = int(0.8*avg_x + 0.2*self.draw_smooth_x)
                    scr_y = int(0.8*avg_y + 0.2*self.draw_smooth_y)
                    scr_x = max(0, min(SCREEN_W-1, scr_x))
                    scr_y = max(0, min(SCREEN_H-1, scr_y))
                    self.draw_smooth_x, self.draw_smooth_y = scr_x, scr_y
                    self.draw_finger_x, self.draw_finger_y = scr_x, scr_y

                    if self.using_eraser:
                        if results.multi_hand_landmarks:
                            pk = results.multi_hand_landmarks[0].landmark[20]
                            pk_scr_x = int(np.clip(pk.x*SCREEN_W, 0, SCREEN_W-1))
                            pk_scr_y = int(np.clip(pk.y*SCREEN_H, 0, SCREEN_H-1))
                            pk_fr_x, pk_fr_y = int(pk.x*w), int(pk.y*h)
                            if self.draw_overlay_canvas is not None:
                                cv2.circle(self.draw_overlay_canvas, (pk_scr_x, pk_scr_y), 40, (0,0,0), -1)
                            self.draw_prev_pt = None
                            cv2.circle(frame, (pk_fr_x, pk_fr_y), 25, (255,0,255), 3)
                    elif finger_count == 1:
                        if self.draw_overlay_canvas is not None:
                            color = self.colors[self.color_index]
                            # FIX: If color is pure black, use a dark gray that will survive STL threshold
                            if color == (0,0,0):
                                color = (20,20,20)   # visible but still dark
                            if self.draw_prev_pt is not None:
                                px, py = self.draw_prev_pt
                                dist = ((scr_x-px)**2 + (scr_y-py)**2)**0.5
                                if dist > 60:
                                    steps = max(2, int(dist/20))
                                    for s in range(1, steps+1):
                                        ix = int(px + (scr_x-px)*s/steps)
                                        iy = int(py + (scr_y-py)*s/steps)
                                        cv2.circle(self.draw_overlay_canvas, (ix,iy), 3, color, -1)
                                cv2.line(self.draw_overlay_canvas, self.draw_prev_pt, (scr_x,scr_y), color, 6)
                            else:
                                cv2.circle(self.draw_overlay_canvas, (scr_x,scr_y), 3, color, -1)
                        self.draw_prev_pt = (scr_x, scr_y)
                        cv2.circle(frame, (x,y), 10, (0,255,0), -1)
                    else:
                        self.draw_prev_pt = None
                        self.draw_buf.clear()
                        if self.can_act():
                            # 2 fingers: change colour
                            if finger_count == 2 and current_time - self.last_action_time > 1.0:
                                self.color_index = (self.color_index + 1) % len(self.colors)
                                log.info(f"Color: {self.color_names[self.color_index]}")
                                self.last_action_time = current_time
                                self.last_action_global = current_time
                            # 3 fingers: save 2D + anaglyph + STL + textured OBJ (entire canvas)
                            elif finger_count == 3 and current_time - self.last_action_time > 1.0:
                                if self.draw_overlay_canvas is not None:
                                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    base_name = f"{SAVE_DIR_DRAW}/drawing_{ts}"
                                    filename_2d = f"{base_name}.png"
                                    filename_anaglyph = f"{base_name}_anaglyph.png"
                                    filename_stl = f"{base_name}.stl"
                                    # 2D PNG
                                    cv2.imwrite(filename_2d, self.draw_overlay_canvas)
                                    # Anaglyph PNG
                                    self._save_anaglyph_3d(self.draw_overlay_canvas, filename_anaglyph)
                                    # Monochrome STL
                                    if save_drawing_as_stl(self.draw_overlay_canvas, filename_stl, height=2.0, downsample=4):
                                        log.info(f"Saved 2D: {filename_2d}")
                                        log.info(f"Saved anaglyph: {filename_anaglyph}")
                                        log.info(f"Saved 3D STL: {filename_stl}")
                                    # Coloured textured OBJ+MTL+PNG
                                    save_drawing_as_textured_obj(self.draw_overlay_canvas, base_name, height=2.0, downsample=4)
                                self.last_action_time = current_time
                                self.last_action_global = current_time
                            # 4 fingers: clear canvas
                            elif finger_count == 4 and current_time - self.last_action_time > 1.0:
                                if self.draw_overlay_canvas is not None:
                                    self.draw_overlay_canvas.fill(0)
                                log.info("Canvas cleared")
                                self.last_action_time = current_time
                                self.last_action_global = current_time

                # ---- WRITE mode (with on‑screen typed text) ----
                if self.mode == "WRITE" and not self.paused and tip is not None:
                    if finger_count == 1:
                        cv2.circle(self.canvas, (cx,cy), 3, (0,255,255), -1)
                        self.stroke.append([cx,cy])
                        self.last_motion_time = current_time
                        cv2.circle(frame, (x,y), 10, (0,255,0), -1)
                    elif len(self.stroke) > 15:
                        still_time = current_time - self.last_motion_time
                        if still_time > 1.5 and current_time - self.last_rec_time > 0.8:
                            log.info("Recognizing...")
                            if self.stroke:
                                letter, conf = hybrid_predict(self.stroke)
                                if letter and conf > 0.40:
                                    if PYNPUT_AVAILABLE:
                                        keyboard.press(letter)
                                        keyboard.release(letter)
                                    self.typed += letter
                                    log.info(f"'{letter}' ({conf*100:.0f}%) -> Typed")
                                else:
                                    log.info(f"Low confidence ({conf*100:.0f}%)")
                            self.canvas.fill(0)
                            self.stroke = []
                            self.last_rec_time = current_time
                    elif finger_count == 2 and current_time - self.last_action_time > 1.0:
                        if PYNPUT_AVAILABLE:
                            keyboard.press(Key.space)
                            keyboard.release(Key.space)
                            self.typed += " "
                            log.info("SPACE")
                            self.last_action_time = current_time
                    elif finger_count == 3 and current_time - self.last_action_time > 1.0:
                        if self.typed and PYNPUT_AVAILABLE:
                            keyboard.press(Key.backspace)
                            keyboard.release(Key.backspace)
                            self.typed = self.typed[:-1]
                            log.info("Backspace")
                        self.last_action_time = current_time
                    elif finger_count == 4 and current_time - self.last_action_time > 1.0:
                        self.canvas.fill(0)
                        self.stroke = []
                        log.info("Stroke cleared")
                        self.last_action_time = current_time

                # ---- MOUSE mode ----
                if self.mode == "MOUSE" and not self.paused and PYAUTOGUI_AVAILABLE and tip is not None:
                    mouse_gesture = detect_mouse_gesture(results.multi_hand_landmarks[0].landmark if results.multi_hand_landmarks else None)
                    if mouse_gesture == "index":
                        self.move_mouse(tip.x, tip.y)
                        cv2.circle(frame, (x,y), 15, (255,0,255), 3)
                    elif current_time - self.last_action_time > 1.0 and self.can_act():
                        if mouse_gesture == "ring":
                            pyautogui.click()
                            log.info("Click")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif mouse_gesture == "pinky":
                            pyautogui.rightClick()
                            log.info("Right-click")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif mouse_gesture == "fist":
                            if not self.is_dragging:
                                pyautogui.mouseDown()
                                self.is_dragging = True
                                log.info("Drag START")
                            else:
                                pyautogui.mouseUp()
                                self.is_dragging = False
                                log.info("Drag END")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif mouse_gesture == "two":
                            if current_time - self.last_scroll_time > 0.08:
                                pyautogui.scroll(30)
                                self.last_scroll_time = current_time
                        elif mouse_gesture == "three":
                            if current_time - self.last_scroll_time > 0.08:
                                pyautogui.scroll(-30)
                                self.last_scroll_time = current_time

                # ---- GESTURE mode ----
                if self.mode == "GESTURE" and not self.paused and PYAUTOGUI_AVAILABLE:
                    mouse_gesture = detect_mouse_gesture(results.multi_hand_landmarks[0].landmark if results.multi_hand_landmarks else None)
                    if current_time - self.last_action_time > 1.5 and self.can_act():
                        if named_gesture == "thumbs_up":
                            pyautogui.hotkey('win','shift','s')
                            log.info("Screenshot")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif named_gesture == "ok":
                            pyautogui.hotkey('ctrl','s')
                            log.info("Save")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif named_gesture == "pinky":
                            pyautogui.hotkey('alt','left')
                            log.info("Navigate Back")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif named_gesture == "ring_only":
                            pyautogui.hotkey('ctrl','-')
                            log.info("Zoom Out")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif named_gesture == "four_fingers":
                            pyautogui.hotkey('ctrl','w')
                            log.info("Close Tab")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif mouse_gesture == "two":
                            pyautogui.hotkey('alt','tab')
                            log.info("App Switch")
                            self.last_action_time = current_time
                            self.last_action_global = current_time
                        elif mouse_gesture == "three":
                            pyautogui.hotkey('ctrl','+')
                            log.info("Zoom In")
                            self.last_action_time = current_time
                            self.last_action_global = current_time

                # ========== UI DISPLAY ==========
                def draw_panel(frame, x, y, w, h, text_lines, bg_color=(0,0,0,self.ui_opacity)):
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (x, y), (x+w, y+h), bg_color[:3], -1)
                    alpha = bg_color[3] if len(bg_color)>3 else self.ui_opacity
                    cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0, frame)
                    for i, line in enumerate(text_lines):
                        cv2.putText(frame, line, (x+10, y+25+i*int(22*self.font_scale/0.55)), cv2.FONT_HERSHEY_SIMPLEX, self.font_scale, (255,255,255), 1)

                # Status panel
                panel_x, panel_y = 20, 20
                panel_w = 300
                lines = []
                if self.paused:
                    lines = ["[PAUSED]", "Show PALM to unpause"]
                elif self.mode == "MAIN":
                    lines = ["MAIN MENU", "Palm -> mode selection",
                             "1->DRAW 2->WRITE 3->MOUSE 4->OSK",
                             "Thumbs up -> MUSIC    OK -> GESTURE"]
                elif self.mode == "DRAW":
                    lines = ["DRAW MODE", f"Color: {self.color_names[self.color_index]}",
                             "1:Draw  2:Color  3:Save (2D+Anaglyph+STL+OBJ)  4:Clear  Pinky:Eraser"]
                elif self.mode == "WRITE":
                    lines = ["WRITE MODE", "Draw letters, they auto-type"]
                elif self.mode == "MOUSE":
                    lines = ["MOUSE MODE", f"Gesture: {named_gesture.upper()}",
                             "Fist drag | 2=scroll up  3=scroll down"]
                elif self.mode == "GESTURE":
                    lines = ["GESTURE MODE",
                             "Thumbs up=Screenshot  OK=Save  Pinky=Back",
                             "Ring=Zoom out  4 fingers=Close tab  2=App switch  3=Zoom in"]
                elif self.mode == "MUSIC":
                    lines = ["MUSIC MODE", "1=Piano  2=Guitar  3=Violin", "OK = Song mode"]
                elif self.mode == "INSTRUMENT_CHOICE":
                    lines = [f"[{self.selected_instrument.upper()} selected]",
                             "Thumbs up = Free-play", "OK = Song mode", "Palm = Cancel"]
                elif self.mode == "SONG_SELECT":
                    if self.song_list:
                        lines = [f"SONG SELECTION - {self.song_select_instrument.upper()}",
                                 f"Song: {self.song_list[self.song_index][1]}",
                                 f"({self.song_index+1}/{len(self.song_list)})",
                                 "2=Next  3=Prev   OK=Play   Palm=Back"]
                    else:
                        lines = ["No songs found"]
                draw_panel(frame, panel_x, panel_y, panel_w, 30+len(lines)*22, lines)

                # WRITE mode extra display: show typed text
                if self.mode == "WRITE" and self.typed:
                    txt = f"Typed: {self.typed[-50:]}" if len(self.typed) > 50 else f"Typed: {self.typed}"
                    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                    panel_w2 = tw + 40
                    panel_h2 = th + 30
                    panel_x2 = (w - panel_w2) // 2
                    panel_y2 = 20
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (panel_x2, panel_y2), (panel_x2+panel_w2, panel_y2+panel_h2), (0,0,0), -1)
                    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
                    cv2.putText(frame, txt, (panel_x2+20, panel_y2+th+10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

                # FPS counter
                if self.show_fps:
                    cv2.putText(frame, f"FPS: {self.current_fps}", (w-100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)

                # Progress bar for stability
                if not self.paused and self.mode in ["MAIN","DRAW","WRITE","MUSIC","INSTRUMENT_CHOICE","SONG_SELECT"]:
                    confidence = 0
                    if len(self.finger_history) == self.finger_history.maxlen:
                        cnt = sum(1 for c in self.finger_history if c == finger_count)
                        confidence = int(100 * cnt / self.finger_history.maxlen)
                    bar_w = int(confidence * 3)
                    cv2.rectangle(frame, (20, h-100), (320, h-70), (50,50,50), -1)
                    cv2.rectangle(frame, (20, h-100), (20+bar_w, h-70), (0,255,0) if confidence >= self.stability_threshold*100 else (255,165,0), -1)
                    name_map = {0:"FIST",1:"1",2:"2",3:"3",4:"4",5:"PALM"}
                    name = name_map.get(finger_count, "?")
                    if self.mode == "INSTRUMENT_CHOICE" and named_gesture == "thumbs_up":
                        name = "THUMBS"
                    elif self.mode == "INSTRUMENT_CHOICE" and named_gesture == "ok":
                        name = "OK"
                    elif self.mode == "SONG_SELECT" and named_gesture == "ok":
                        name = "OK"
                    cv2.putText(frame, f"{name} {confidence}% (thresh:{int(self.stability_threshold*100)}%)", (30, h-78), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

                # Show current cooldown value
                cv2.putText(frame, f"Cooldown: {self.global_cooldown:.1f}s", (20, h-30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150,150,150), 1)

                # OSK overlay
                if self.mode == "OSK" and self.osk and WIN32_AVAILABLE:
                    OSK_WIN = "Air Gesture OSK"
                    if not self.osk_window_ready:
                        cv2.namedWindow(OSK_WIN, cv2.WINDOW_NORMAL)
                        cv2.setWindowProperty(OSK_WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                        cv2.waitKey(100)
                        hwnd = win32gui.FindWindow(None, OSK_WIN)
                        if hwnd:
                            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, 0)
                            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, self.osk.screen_w, self.osk.screen_h, win32con.SWP_SHOWWINDOW)
                            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) |
                                win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
                            win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(0,0,0), 0, win32con.LWA_COLORKEY)
                            log.info("OSK transparent overlay ready!")
                        self.osk_window_ready = True
                    if tip is not None:
                        self.osk_finger_x = int(tip.x * self.osk.screen_w)
                        self.osk_finger_y = int(tip.y * self.osk.screen_h)
                        self.osk_finger_z = tip.z
                    keyboard_overlay = self.osk.draw_overlay(self.osk_finger_x, self.osk_finger_y, self.osk_finger_z)
                    cv2.imshow(OSK_WIN, keyboard_overlay)
                else:
                    if self.osk_window_ready:
                        cv2.destroyWindow("Air Gesture OSK")
                        self.osk_window_ready = False

                # DRAW overlay
                if self.mode == "DRAW" and WIN32_AVAILABLE:
                    DRAW_WIN = "Air Gesture Draw"
                    if not self.draw_window_ready:
                        self.draw_overlay_canvas = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)
                        self.draw_prev_pt = None
                        self.draw_buf.clear()
                        cv2.namedWindow(DRAW_WIN, cv2.WINDOW_NORMAL)
                        cv2.setWindowProperty(DRAW_WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                        cv2.waitKey(100)
                        hwnd = win32gui.FindWindow(None, DRAW_WIN)
                        if hwnd:
                            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, 0)
                            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, SCREEN_W, SCREEN_H, win32con.SWP_SHOWWINDOW)
                            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) |
                                win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
                            win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(0,0,0), 0, win32con.LWA_COLORKEY)
                            log.info("Draw transparent overlay ready!")
                        self.draw_window_ready = True
                    if self.draw_overlay_canvas is not None:
                        display = self.draw_overlay_canvas.copy()
                        cur_color = self.colors[self.color_index]
                        # For preview circle, if color is black use the (20,20,20) replacement
                        disp_color = (20,20,20) if cur_color == (0,0,0) else cur_color
                        cv2.circle(display, (self.draw_finger_x, self.draw_finger_y), 14, (255,255,255), 3)
                        cv2.circle(display, (self.draw_finger_x, self.draw_finger_y), 10, disp_color, -1)
                        if self.using_eraser:
                            cv2.circle(display, (self.draw_finger_x, self.draw_finger_y), 40, (255,0,255), 3)
                        cv2.rectangle(display, (20,20), (80,80), disp_color, -1)
                        cv2.rectangle(display, (20,20), (80,80), (255,255,255), 3)
                        cv2.imshow(DRAW_WIN, display)
                else:
                    if self.draw_window_ready:
                        try: cv2.destroyWindow("Air Gesture Draw")
                        except: pass
                        self.draw_window_ready = False
                        self.draw_overlay_canvas = None
                        self.draw_prev_pt = None

                # WRITE small canvas (recognition preview)
                if self.mode == "WRITE":
                    if self.canvas is not None and np.any(self.canvas):
                        small_canvas = cv2.resize(self.canvas, (200,200))
                        frame[h-220:h-20, w-220:w-20] = small_canvas
                        cv2.rectangle(frame, (w-220, h-220), (w-20, h-20), (0,255,255), 2)
                        cv2.putText(frame, "Recognition", (w-210, h-230), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)

                cv2.imshow("Air Gesture System v3.1", frame)

                # Keyboard handling
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or self.exit_program: break
                elif key in (ord('u'), ord('U')): self.user_id.calibrate(frame); log.info("Force recalibrated")
                elif key in (ord('r'), ord('R')):
                    log.info("Manual camera reset")
                    camera_mgr.release_all()
                    time.sleep(0.5)
                    camera_mgr.open_cameras()
                    print("Camera reinitialised")
                elif key in (ord('h'), ord('H')):
                    self.show_skeleton = not self.show_skeleton
                    self.save_settings()
                elif key in (ord('m'), ord('M')):
                    self.mirror = not self.mirror
                    self.save_settings()
                elif key in (ord('s'), ord('S')):
                    self.sound_feedback = not self.sound_feedback
                    self.save_settings()
                elif key in (ord('g'), ord('G')):
                    self.show_gesture_hints = not self.show_gesture_hints
                    self.save_settings()
                elif key == ord('=') or key == ord('+'):
                    self.ui_opacity = min(1.0, self.ui_opacity + 0.05)
                    self.save_settings()
                elif key == ord('-') or key == ord('_'):
                    self.ui_opacity = max(0.2, self.ui_opacity - 0.05)
                    self.save_settings()
                elif key == ord('['):
                    self.font_scale = max(0.35, self.font_scale - 0.05)
                    self.save_settings()
                elif key == ord(']'):
                    self.font_scale = min(0.9, self.font_scale + 0.05)
                    self.save_settings()
                elif key == ord('t') or key == ord('T'):
                    self.stability_threshold = min(0.95, self.stability_threshold + 0.05)
                    self.save_settings()
                    log.info(f"Stability threshold: {self.stability_threshold:.2f}")
                elif key == ord('y') or key == ord('Y'):
                    self.stability_threshold = max(0.5, self.stability_threshold - 0.05)
                    self.save_settings()
                    log.info(f"Stability threshold: {self.stability_threshold:.2f}")
                elif key == ord('u') or key == ord('U'):
                    self.global_cooldown = min(2.0, self.global_cooldown + 0.1)
                    self.save_settings()
                    log.info(f"Global cooldown: {self.global_cooldown:.1f}s")
                elif key == ord('i') or key == ord('I'):
                    self.global_cooldown = max(0.2, self.global_cooldown - 0.1)
                    self.save_settings()
                    log.info(f"Global cooldown: {self.global_cooldown:.1f}s")
                elif key == ord('f') or key == ord('F'):
                    self.show_fps = not self.show_fps
                elif key == ord('v') or key == ord('V'):
                    self.reset_calibrations()

                # Easter egg typing
                if key != 255 and key not in [27, ord('u'), ord('U'), ord('r'), ord('R'), ord('h'), ord('H'),
                                               ord('m'), ord('M'), ord('s'), ord('S'), ord('g'), ord('G'),
                                               ord('='), ord('+'), ord('-'), ord('_'), ord('['), ord(']'),
                                               ord('t'), ord('T'), ord('y'), ord('Y'), ord('u'), ord('U'),
                                               ord('i'), ord('I'), ord('f'), ord('F'), ord('v'), ord('V')]:
                    now = time.time()
                    try:
                        char = chr(key).lower()
                        self.key_buffer += char
                        self.key_buffer = self.key_buffer[-len(EASTER_EGG_CODE):]
                        if self.key_buffer == EASTER_EGG_CODE:
                            if now - self.last_easter_time > EASTER_COOLDOWN:
                                trigger_easter_egg(self)
                                self.last_easter_time = now
                                self.key_buffer = ""
                    except: pass

        finally:
            self.save_settings()
            if self.is_dragging and PYAUTOGUI_AVAILABLE:
                try: pyautogui.mouseUp()
                except: pass
            if self.draw_window_ready:
                try: cv2.destroyWindow("Air Gesture Draw")
                except: pass
            if self.osk_window_ready:
                try: cv2.destroyWindow("Air Gesture OSK")
                except: pass
            camera_mgr.release_all()
            cv2.destroyAllWindows()
            self.hands.close()
            log.info(f"System exited. Typed: '{self.typed}'")

if __name__ == "__main__":
    app = App()
    app.run()