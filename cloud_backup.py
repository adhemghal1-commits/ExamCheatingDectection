import threading
from pathlib import Path

import settings as cfg


class CloudSyncService:
    def __init__(self, db):
        self.db = db
        self.enabled = False
        if not cfg.FIREBASE_ENABLED:
            print("Firebase disabled in settings.py: using SQLite + local screenshots only.")
            return
        if not Path(cfg.FIREBASE_KEY_PATH).exists() or not cfg.FIREBASE_STORAGE_BUCKET:
            print("Firebase key or bucket missing: using local storage only.")
            return
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore, storage
            if not firebase_admin._apps:
                firebase_admin.initialize_app(
                    credentials.Certificate(str(cfg.FIREBASE_KEY_PATH)),
                    {"storageBucket": cfg.FIREBASE_STORAGE_BUCKET},
                )
            self._firestore = firestore
            self.fs = firestore.client()
            self.bucket = storage.bucket()
            self.enabled = True
            print("Firebase connected: Firestore + Storage enabled.")
        except Exception as e:
            print("Firebase init failed, continuing with local storage:", e)

    def push(self, alert):
        if not self.enabled:
            return
        threading.Thread(target=self._push, args=(dict(alert),), daemon=True).start()

    def _push(self, alert):
        try:
            blob = self.bucket.blob("screenshots/" + Path(alert["screenshot_path"]).name)
            blob.upload_from_filename(alert["screenshot_path"])
            blob.make_public()
            url = blob.public_url
            self.db.set_url(alert["id"], url)
            self.fs.collection("alerts").add({
                "created_at": alert["created_at"],
                "behavior": alert["behavior"],
                "confidence": alert["confidence"],
                "student_id": alert["student_id"],
                "video_name": alert["video_name"],
                "video_time": alert["video_time"],
                "screenshot_path": alert["screenshot_path"],
                "firebase_url": url,
                "server_time": self._firestore.SERVER_TIMESTAMP,
            })
        except Exception as e:
            print("Firebase upload failed for alert", alert.get("id"), ":", e)


# Backward-compatible alias
FirebaseSync = CloudSyncService
