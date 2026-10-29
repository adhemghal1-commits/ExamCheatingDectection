import csv
import re
import uuid
from datetime import datetime
from pathlib import Path

import cv2

import settings as cfg
from suspicion_rules import CheatingAnalysisEngine, select_monitored


class ExamVideoProcessor:
    def __init__(self, db, cloud):
        self.db = db
        self.cloud = cloud
        self.detector = None
        self.gaze = None
        self.engine = CheatingAnalysisEngine()

    def load(self, status=None):
        if self.detector is None:
            if status:
                status("Loading detection models (first run downloads weights)...")
            from vision_engine import ProctorVisionDetector
            self.detector = ProctorVisionDetector()
        if self.gaze is None:
            if status:
                status("Loading gaze model...")
            from eye_direction import IrisGazeAnalyzer
            self.gaze = IrisGazeAnalyzer()

    def _record(self, annotated, sid, alert, t, video_name):
        now = datetime.now()
        slug = re.sub(r"[^a-z0-9]+", "_", alert["behavior"].lower()).strip("_")
        fname = "alert_" + now.strftime("%Y%m%d_%H%M%S") + "_id" + str(sid) + "_" + slug + "_" + uuid.uuid4().hex[:4] + ".jpg"
        path = cfg.SCREENSHOT_DIR / fname
        shot = annotated.copy()
        banner = "ALERT  " + alert["behavior"] + "  |  Student " + str(sid) + "  |  " + now.strftime("%Y-%m-%d %H:%M:%S")
        cv2.rectangle(shot, (0, 0), (shot.shape[1], 30), (0, 0, 160), -1)
        cv2.putText(shot, banner, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imwrite(str(path), shot)
        rec = {
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "display_time": now.strftime("%I:%M %p"),
            "behavior": alert["behavior"],
            "confidence": alert["confidence"],
            "student_id": int(sid),
            "screenshot_path": str(path),
            "firebase_url": "",
            "video_name": video_name,
            "video_time": round(t, 2),
        }
        rec["id"] = self.db.insert(rec)
        self.cloud.push(rec)
        return rec

    @staticmethod
    def _fmt(v):
        return "" if v is None else format(v, ".4f")

    def run(self, video_path, on_frame=None, on_alert=None, on_progress=None, stop_event=None, max_frames=None):
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise IOError("Cannot open video: " + str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        video_name = Path(video_path).name
        step = max(1, int(cfg.PROCESS_EVERY_N_FRAMES))

        self.detector.reset()
        self.engine.reset()

        log_file, writer = None, None
        if cfg.SHOW_DEBUG:
            log_file = open(cfg.DEBUG_LOG_PATH, "w", newline="", encoding="utf-8")
            writer = csv.writer(log_file)
            writer.writerow(["time", "student_id", "yaw_dev", "ratio_dev", "gaze_dev", "head_flag", "gaze_flag"])

        idx, count = 0, 0
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                idx += 1
                if (idx - 1) % step:
                    if not cap.grab():
                        break
                    continue
                ok, frame = cap.read()
                if not ok:
                    break
                if max_frames and idx > max_frames:
                    break
                t = (idx - 1) / fps

                persons, phones, customs = self.detector.detect(frame)
                gaze = {}
                if self.gaze is not None and self.gaze.enabled:
                    for p in select_monitored(persons):
                        g = self.gaze.estimate(frame, p)
                        if g is not None:
                            gaze[p["id"]] = g
                decisions = self.engine.update(t, persons, phones, customs, gaze)
                annotated = self.detector.draw(frame, persons, decisions)

                for sid, dec in decisions.items():
                    for alert in dec["alerts"]:
                        rec = self._record(annotated, sid, alert, t, video_name)
                        count += 1
                        if on_alert:
                            on_alert(rec)
                    if writer is not None and dec["debug_row"] is not None:
                        yd, rd, gd, hf, gf = dec["debug_row"]
                        writer.writerow([round(t, 2), sid, self._fmt(yd), self._fmt(rd), self._fmt(gd), int(hf), int(gf)])

                if on_frame:
                    on_frame(annotated)
                if on_progress and total_frames and idx % 5 == 0:
                    on_progress(idx, total_frames)
        finally:
            cap.release()
            if log_file is not None:
                log_file.close()
        if on_progress and total_frames:
            on_progress(total_frames, total_frames)
        return count


# Backward-compatible alias
Pipeline = ExamVideoProcessor
