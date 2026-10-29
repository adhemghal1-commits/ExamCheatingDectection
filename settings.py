from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ALERTS_DIR = BASE_DIR / "alerts"
SCREENSHOT_DIR = ALERTS_DIR / "screenshots"
DB_PATH = ALERTS_DIR / "alerts.db"
DEBUG_LOG_PATH = ALERTS_DIR / "debug_log.csv"
MODELS_DIR = BASE_DIR / "models"
ASSETS_DIR = BASE_DIR / "assets"
ICON_PNG = ASSETS_DIR / "app_icon.png"
ICON_ICO = ASSETS_DIR / "app_icon.ico"

for _d in (ALERTS_DIR, SCREENSHOT_DIR, MODELS_DIR, ASSETS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

POSE_MODEL = str(MODELS_DIR / "yolov8n-pose.pt") if (MODELS_DIR / "yolov8n-pose.pt").exists() else "yolov8n-pose.pt"
OBJECT_MODEL = str(MODELS_DIR / "yolov8n.pt") if (MODELS_DIR / "yolov8n.pt").exists() else "yolov8n.pt"
TRACKER = "botsort.yaml"
IMG_SIZE = 640
PROCESS_EVERY_N_FRAMES = 1
PERSON_CONF = 0.40
KEYPOINT_CONF = 0.40

PHONE_CLASS_ID = 67
PHONE_CONF = 0.30
PHONE_CONFIRM_FRAMES = 3
PHONE_MARGIN = 0.15

CUSTOM_MODEL = None
CUSTOM_CHEAT_CLASSES = None
CUSTOM_CONF = 0.40

MIN_RELATIVE_HEIGHT = 0.45

YAW_THRESHOLD = 0.25
HEAD_TURN_RATIO = 0.20
GAZE_ENABLED = True
GAZE_THRESHOLD = 0.08
GAZE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
GAZE_MODEL_PATH = MODELS_DIR / "face_landmarker.task"

HEAD_TURN_SECONDS = 1.0
TURN_WINDOW_SECONDS = 6.0
BASELINE_SECONDS = 30.0
BASELINE_MIN_SAMPLES = 8
WARMUP_SECONDS = 1.0
REQUIRE_NEIGHBOR_DIRECTION = True
NEIGHBOR_MAX_WIDTHS = 3.0
NEIGHBOR_MAX_DY_HEIGHTS = 1.0

ALERT_COOLDOWN_SECONDS = 10.0
RED_HOLD_SECONDS = 3.0

SHOW_DEBUG = False

FIREBASE_ENABLED = False
FIREBASE_KEY_PATH = BASE_DIR / "firebase_key.json"
FIREBASE_STORAGE_BUCKET = ""

GREEN = (0, 200, 0)
RED = (0, 0, 255)
