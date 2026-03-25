"""
Gesture Controller - Control your PC with hand gestures
Free 100% | Works on Windows, Mac, Linux

Required libraries (install once):
    pip install opencv-python mediapipe pyautogui numpy

Run:
    py -3.11 gesture_controller.py
"""

import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import time
import math

# ── General Settings ──────────────────────────────────────────────────────────
pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0

SCREEN_W, SCREEN_H = pyautogui.size()
CAM_W,    CAM_H    = 640, 480
FRAME_MARGIN       = 100

# ── MediaPipe ─────────────────────────────────────────────────────────────────
mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_styles  = mp.solutions.drawing_styles

# ── Gesture Constants ─────────────────────────────────────────────────────────
CLICK_THRESHOLD    = 40
SCROLL_THRESHOLD   = 50
DOUBLE_CLICK_DELAY = 0.35
SMOOTH_FACTOR      = 5
STARTUP_DELAY      = 2.0   # seconds to wait before activating gestures


# ══════════════════════════════════════════════════════════════════════════════
def distance(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def get_landmarks(hand_landmarks, w, h):
    lm = {}
    for idx, landmark in enumerate(hand_landmarks.landmark):
        lm[idx] = (int(landmark.x * w), int(landmark.y * h))
    return lm


def fingers_up(lm):
    fingers = {}

    # Thumb — compare with wrist x to handle both hands
    wrist_x = lm[0][0]
    thumb_tip_x = lm[4][0]
    thumb_mcp_x = lm[2][0]
    # If wrist is on left side, thumb points right when open
    if wrist_x < lm[9][0]:
        fingers['thumb'] = thumb_tip_x > thumb_mcp_x
    else:
        fingers['thumb'] = thumb_tip_x < thumb_mcp_x

    # Other fingers — compare tip y vs PIP joint y
    fingers['index']  = lm[8][1]  < lm[6][1]
    fingers['middle'] = lm[12][1] < lm[10][1]
    fingers['ring']   = lm[16][1] < lm[14][1]
    fingers['pinky']  = lm[20][1] < lm[18][1]

    return fingers


def detect_gesture(fingers, lm):
    i = fingers['index']
    m = fingers['middle']
    r = fingers['ring']
    p = fingers['pinky']
    t = fingers['thumb']

    # Move mouse: only index finger raised
    if i and not m and not r and not p:
        return "MOVE_MOUSE"

    # Left click: index + middle raised and close together
    if i and m and not r and not p:
        if distance(lm[8], lm[12]) < CLICK_THRESHOLD:
            return "CLICK"
        return "MOVE_MOUSE"

    # Right click: index + middle + ring raised
    if i and m and r and not p:
        return "RIGHT_CLICK"

    # Scroll: all fingers open
    if i and m and r and p and t:
        return "SCROLL"

    # Volume control: thumb + pinky only
    if t and p and not i and not m and not r:
        return "VOLUME"

    # Copy Ctrl+C: middle + ring + pinky only
    if not i and m and r and p and not t:
        return "COPY"

    # Paste Ctrl+V: thumb + index close together
    if t and i and not m and not r and not p:
        if distance(lm[4], lm[8]) < CLICK_THRESHOLD:
            return "PASTE"
        return "MOVE_MOUSE"

    # Fist
    if not i and not m and not r and not p:
        return "FIST"

    return "NONE"


# ══════════════════════════════════════════════════════════════════════════════
#  Volume Control (Windows only)
# ══════════════════════════════════════════════════════════════════════════════
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices    = AudioUtilities.GetSpeakers()
    interface  = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
    vol_range  = volume_ctrl.GetVolumeRange()
    VOLUME_SUPPORTED = True
    print("Volume control: available")
except Exception:
    volume_ctrl      = None
    VOLUME_SUPPORTED = False
    print("Volume control: not available (using keyboard keys)")


def set_volume_by_distance(d):
    if VOLUME_SUPPORTED:
        vol = np.interp(d, [30, 200], [vol_range[0], vol_range[1]])
        volume_ctrl.SetMasterVolumeLevel(float(vol), None)
    else:
        if d > 120:
            pyautogui.press('volumeup')
        elif d < 60:
            pyautogui.press('volumedown')


# ══════════════════════════════════════════════════════════════════════════════
#  Main Loop
# ══════════════════════════════════════════════════════════════════════════════
def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)

    prev_x, prev_y  = 0, 0
    curr_x, curr_y  = 0, 0
    last_click_time = 0
    scroll_start_y  = None
    click_holding   = False
    start_time      = time.time()   # for startup cooldown

    print("\n Gesture Controller is running!")
    print("=" * 45)
    print("Index finger only        -> Move mouse")
    print("Index + Middle (close)   -> Left click")
    print("Index + Middle + Ring    -> Right click")
    print("All fingers open         -> Scroll")
    print("Thumb + Pinky            -> Volume control")
    print("Middle + Ring + Pinky    -> Copy  Ctrl+C")
    print("Thumb + Index (close)    -> Paste Ctrl+V")
    print("=" * 45)
    print(f"Waiting {int(STARTUP_DELAY)}s before activating...")
    print("Press Q in camera window to exit\n")

    with mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.80,
        min_tracking_confidence=0.80,
    ) as hands:

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame  = cv2.flip(frame, 1)
            h, w   = frame.shape[:2]
            elapsed = time.time() - start_time

            # ── Startup countdown overlay ──────────────────────────────────
            if elapsed < STARTUP_DELAY:
                remaining = int(STARTUP_DELAY - elapsed) + 1
                cv2.rectangle(frame, (0, 0), (w, h), (30, 30, 30), -1)
                cv2.putText(frame, f"Starting in {remaining}...",
                            (w // 2 - 120, h // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 200, 255), 3)
                cv2.putText(frame, "Get your hand ready",
                            (w // 2 - 110, h // 2 + 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
                cv2.imshow("Gesture Controller", frame)
                cv2.waitKey(1)
                continue

            # ── Process frame ──────────────────────────────────────────────
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)
            rgb.flags.writeable = True

            gesture_text = "No hand detected"
            action_text  = ""

            if results.multi_hand_landmarks:
                hand = results.multi_hand_landmarks[0]

                mp_drawing.draw_landmarks(
                frame, hand,
                 mp_hands.HAND_CONNECTIONS,
)
                

                lm      = get_landmarks(hand, w, h)
                fingers = fingers_up(lm)
                gesture = detect_gesture(fingers, lm)
                gesture_text = gesture

                # Move mouse
                if gesture in ("MOVE_MOUSE", "CLICK", "PASTE"):
                    tip_x, tip_y = lm[8]
                    screen_x = np.interp(tip_x,
                                         [FRAME_MARGIN, w - FRAME_MARGIN],
                                         [0, SCREEN_W])
                    screen_y = np.interp(tip_y,
                                         [FRAME_MARGIN, h - FRAME_MARGIN],
                                         [0, SCREEN_H])
                    curr_x = prev_x + (screen_x - prev_x) / SMOOTH_FACTOR
                    curr_y = prev_y + (screen_y - prev_y) / SMOOTH_FACTOR
                    prev_x, prev_y = curr_x, curr_y
                    pyautogui.moveTo(int(curr_x), int(curr_y))

                # Left click
                # Left click / Hold / Release
                if gesture == "CLICK":
                   if not click_holding:
                      now = time.time()
                      if now - last_click_time < DOUBLE_CLICK_DELAY:
                          pyautogui.doubleClick()
                          action_text = "Double Click!"
                      else:
                          pyautogui.mouseDown()
                          action_text = "Holding..."
                      last_click_time = now
                      click_holding   = True
                   else:
                       action_text = "Holding..."
                else:
                   if click_holding:
                       pyautogui.mouseUp()
                       action_text = "Released!"
                   click_holding = False
               

                # Right click
                if gesture == "RIGHT_CLICK":
                    pyautogui.rightClick()
                    action_text = "Right Click!"
                    time.sleep(0.4)

                # Scroll
                if gesture == "SCROLL":
                    wrist_y = lm[0][1]
                    if scroll_start_y is None:
                        scroll_start_y = wrist_y
                    delta = scroll_start_y - wrist_y
                    if abs(delta) > SCROLL_THRESHOLD:
                        pyautogui.scroll(int(delta / 30))
                        action_text = f"Scroll {'UP' if delta > 0 else 'DOWN'}"
                else:
                    scroll_start_y = None

                # Volume
                if gesture == "VOLUME":
                   d = distance(lm[4], lm[20])
                   set_volume_by_distance(d)
                   vol_percent = int(np.interp(d, [30, 200], [0, 100]))
                   action_text = f"Volume: {vol_percent}%"

                # Copy
                if gesture == "COPY":
                    pyautogui.hotkey('ctrl', 'c')
                    action_text = "Copied!"
                    time.sleep(0.5)

                # Paste
                if gesture == "PASTE":
                    pyautogui.hotkey('ctrl', 'v')
                    action_text = "Pasted!"
                    time.sleep(0.5)

                # Fist
                if gesture == "FIST":
                    action_text = "Fist"

            # ── HUD overlay ────────────────────────────────────────────────
            cv2.rectangle(frame, (0, 0), (w, 55), (30, 30, 30), -1)
            cv2.putText(frame, f"Gesture: {gesture_text}",
                        (10, 22), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (100, 255, 100), 2)
            cv2.putText(frame, action_text,
                        (10, 46), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (255, 200, 0), 2)
            cv2.putText(frame, "Q = Quit",
                        (w - 90, 22), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (180, 180, 180), 1)

            cv2.imshow("Gesture Controller", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()
    print("\nClosed successfully")


if __name__ == "__main__":
    main()
