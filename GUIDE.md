# Exam Guard: Cheating Detection Desktop App

Tkinter desktop application that tracks students in an exam video, flags suspicious behavior, turns the suspect's bounding box **red** (normal students stay **green**), saves an annotated screenshot, stores the incident in a database and shows an immediate pop-up alert with sound.

## Quick start (Windows)

1. Install Python 3.10, 3.11 or 3.12 (tick "Add Python to PATH").
2. Double-click `install_and_start.bat` (internet needed, first time only; it installs everything and starts the app).
3. Next times, double-click `start.bat`.
4. In the app press **Upload Video** and choose an exam video.

Manual: `pip install -r libs_needed.txt` then `python exam_monitor_app.py` (on Ubuntu also `sudo apt install python3-tk`).

The first run downloads the YOLO weights and the face landmark model automatically.

## تشغيل سريع
1. نزّل Python 3.10 أو 3.11 أو 3.12 وفعّل Add Python to PATH.
2. دوس دبل كليك على `install_and_start.bat` أول مرة (محتاج نت).
3. بعد كده شغّل `start.bat`.
4. من البرنامج دوس **Upload Video** واختار فيديو الامتحان.

## Features

- **Detection and tracking:** YOLOv8 pose with the BoT-SORT tracker (switch with `TRACKER = "bytetrack.yaml"` in `settings.py`). Each student keeps an ID.
- **Behaviors:**
  - *Phone detected*: a phone near a student for several consecutive processed frames (YOLOv8 object detection).
  - *Looking away (head turned)*: head turned toward a neighbor, measured from nose, eye and shoulder keypoints.
  - *Suspicious gaze direction*: iris position (MediaPipe Face Landmarker) moves sideways toward a neighbor even when the head stays still.
  - *Custom behaviors*: optional custom YOLO weights.
- **Boxes:** red for the flagged student, green for everyone else.
- **Screenshot:** the annotated frame is saved to `alerts/screenshots/`.
- **Database:** every alert goes to SQLite (`alerts/alerts.db`) with date/time, student ID, behavior, confidence, screenshot path, video name and video time. Optional Firebase Firestore + Storage sync.
- **Desktop app:** Upload Video, live video with boxes, live alert list, pop-up notification with sound, Alert History tab (view screenshot, export CSV, delete records), custom app icon.

Example notification:

```
Cheating Alert Detected
Behavior: Phone detected
Student ID: 3
Time: 10:35 AM
Screenshot saved successfully
```

## How the head and gaze rules work

- Each student is compared with **their own normal position** over the last 30 seconds, so a student who naturally sits slightly turned is not flagged. The first second of a new track is a warm-up.
- A head turn or gaze counts only when it points **toward another monitored student** who is close by.
- An alert needs about 1 second of looking away inside a 6 second window, so repeated short glances are caught.
- Small background students (shorter than 45% of the tallest person) are not monitored.
- Confidence: detection confidence for phones, mean keypoint confidence for head turns, and a rule score (how far the offset passes the threshold, capped at 1.0) for gaze.

## Project structure & Classes

| File | Primary Class | Purpose |
|---|---|---|
| `exam_monitor_app.py` | `ExamProctorApp` (formerly `ExamApp`) | Modern Tkinter dashboard UI (entry point) |
| `vision_engine.py` | `ProctorVisionDetector` (formerly `Detector`) | YOLO pose + tracking + phone detection, bounding box drawing |
| `suspicion_rules.py` | `CheatingAnalysisEngine` & `ExamineeTrackerState` | Cheating detection heuristics and per-student temporal state |
| `eye_direction.py` | `IrisGazeAnalyzer` (formerly `GazeEstimator`) | MediaPipe iris gaze estimation |
| `video_processor.py` | `ExamVideoProcessor` (formerly `Pipeline`) | Video processing pipeline, alerts dispatch, screenshot saving |
| `alert_store.py` | `IncidentDatabaseManager` (formerly `AlertDB`) | SQLite incident database manager and CSV export |
| `cloud_backup.py` | `CloudSyncService` (formerly `FirebaseSync`) | Optional Firebase Firestore + Storage cloud synchronization |
| `settings.py` | — | Thresholds, paths, and model configs |
| `tuning_report.py` | — | Summarizes debug logs for parameter tuning |

## Tuning (`settings.py`)

| Setting | Meaning |
|---|---|
| `YAW_THRESHOLD` | Head-turn sensitivity from nose and eye keypoints (0.25). Lower = more sensitive. |
| `HEAD_TURN_RATIO` | Same idea using the shoulders (0.20), used when the eyes are not visible. |
| `GAZE_THRESHOLD` | Sideways iris offset (as a fraction of eye width) that counts as looking away (0.08). `GAZE_ENABLED = False` turns gaze off. |
| `HEAD_TURN_SECONDS`, `TURN_WINDOW_SECONDS` | Total time looking away inside a sliding window (1 s in 6 s). |
| `BASELINE_SECONDS`, `BASELINE_MIN_SAMPLES`, `WARMUP_SECONDS` | Window for each student's normal position and warm-up length. |
| `MIN_RELATIVE_HEIGHT` | Students shorter than this fraction of the tallest box are not monitored (0.45). |
| `REQUIRE_NEIGHBOR_DIRECTION` | Count head/gaze only when it points toward another student. |
| `PHONE_CONF`, `PHONE_CONFIRM_FRAMES` | Phone confidence and the processed frames that confirm it. |
| `ALERT_COOLDOWN_SECONDS` | Minimum time between two alerts of the same type for the same student. |
| `PROCESS_EVERY_N_FRAMES`, `IMG_SIZE` | Lower the load on slow computers. |
| `SHOW_DEBUG` | Shows head/gaze deviation under each box and writes `alerts/debug_log.csv`. Run `python tuning_report.py` to summarize it. |

The default thresholds are starting points. Turn on `SHOW_DEBUG`, run your own video, run `tuning_report.py`, and adjust.

## Use your own trained YOLO model

```
CUSTOM_MODEL = "weights/best.pt"
CUSTOM_CHEAT_CLASSES = ["cheating", "looking_away"]   # None = every class counts
```

Detections of those classes inside a tracked student's box raise an alert named after the class.

## Firebase (optional)

1. Create a Firebase project and enable **Firestore** and **Storage**.
2. Project settings > Service accounts > Generate new private key. Save it as `firebase_key.json` next to `exam_monitor_app.py`.
3. In `settings.py`:

```
FIREBASE_ENABLED = True
FIREBASE_STORAGE_BUCKET = "your-project-id.appspot.com"
```

Alerts are always saved locally first. The upload runs in the background and the cloud URL is written back to the local record. A Firebase failure never stops detection. Never share `firebase_key.json`.

## Limitations

- The rules are heuristics, not a trained cheating classifier. Results depend on camera angle, face size and video quality.
- Gaze from the iris is weak when faces are small or blurry.
- Scene cuts reset track IDs, which restarts each student's warm-up.
- Students seen from behind give no face keypoints, so only phone detection works for them.
- Alerts are suggestions for a human proctor, not proof of cheating. Get consent and follow your institution's privacy rules before recording students.
