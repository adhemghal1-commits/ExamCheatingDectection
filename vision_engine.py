import cv2
from ultralytics import YOLO

import settings as cfg


class ProctorVisionDetector:
    def __init__(self):
        self.pose = YOLO(cfg.POSE_MODEL)
        self.objects = YOLO(cfg.OBJECT_MODEL)
        self.custom = YOLO(str(cfg.CUSTOM_MODEL)) if cfg.CUSTOM_MODEL else None

    def reset(self):
        self.pose.predictor = None

    def detect(self, frame):
        res = self.pose.track(
            frame, persist=True, tracker=cfg.TRACKER, classes=[0],
            conf=cfg.PERSON_CONF, imgsz=cfg.IMG_SIZE, verbose=False,
        )[0]
        persons = []
        if res.boxes is not None and res.boxes.id is not None:
            ids = res.boxes.id.int().cpu().tolist()
            boxes = res.boxes.xyxy.cpu().numpy()
            confs = res.boxes.conf.cpu().numpy()
            kps = res.keypoints.data.cpu().numpy() if res.keypoints is not None else None
            for i, sid in enumerate(ids):
                persons.append({
                    "id": int(sid),
                    "box": [float(v) for v in boxes[i]],
                    "conf": float(confs[i]),
                    "kp": kps[i] if kps is not None else None,
                })

        phones = []
        det = self.objects.predict(
            frame, classes=[cfg.PHONE_CLASS_ID], conf=cfg.PHONE_CONF,
            imgsz=cfg.IMG_SIZE, verbose=False,
        )[0]
        for b in det.boxes:
            phones.append({"box": [float(v) for v in b.xyxy[0].cpu().numpy()], "conf": float(b.conf[0])})

        customs = []
        if self.custom is not None:
            cres = self.custom.predict(frame, conf=cfg.CUSTOM_CONF, imgsz=cfg.IMG_SIZE, verbose=False)[0]
            for b in cres.boxes:
                name = cres.names[int(b.cls[0])]
                if cfg.CUSTOM_CHEAT_CLASSES is None or name in cfg.CUSTOM_CHEAT_CLASSES:
                    customs.append({
                        "name": name,
                        "box": [float(v) for v in b.xyxy[0].cpu().numpy()],
                        "conf": float(b.conf[0]),
                    })
        return persons, phones, customs

    @staticmethod
    def draw(frame, persons, decisions):
        out = frame.copy()
        for p in persons:
            dec = decisions.get(p["id"], {})
            suspect = bool(dec.get("suspect"))
            color = cfg.RED if suspect else cfg.GREEN
            x1, y1, x2, y2 = [int(v) for v in p["box"]]
            label = "ID " + str(p["id"])
            if suspect and dec.get("label"):
                label += ": " + dec["label"]
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 3 if suspect else 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            top = max(y1 - th - 8, 0)
            cv2.rectangle(out, (x1, top), (x1 + tw + 6, top + th + 8), color, -1)
            cv2.putText(out, label, (x1 + 3, top + th + 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (255, 255, 255), 1, cv2.LINE_AA)
            if cfg.SHOW_DEBUG and dec.get("debug"):
                cv2.putText(out, dec["debug"], (x1 + 3, min(y2 + 16, out.shape[0] - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        return out


# Backward-compatible alias
Detector = ProctorVisionDetector
