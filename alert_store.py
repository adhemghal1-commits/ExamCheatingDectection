import csv
import sqlite3
import threading
from pathlib import Path

COLUMNS = (
    "id", "created_at", "behavior", "confidence", "student_id",
    "screenshot_path", "firebase_url", "video_name", "video_time",
)


class IncidentDatabaseManager:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS alerts ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "created_at TEXT NOT NULL,"
                "behavior TEXT NOT NULL,"
                "confidence REAL NOT NULL,"
                "student_id INTEGER,"
                "screenshot_path TEXT,"
                "firebase_url TEXT,"
                "video_name TEXT,"
                "video_time REAL)"
            )
            self.conn.commit()

    def insert(self, a):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO alerts (created_at, behavior, confidence, student_id, "
                "screenshot_path, firebase_url, video_name, video_time) VALUES (?,?,?,?,?,?,?,?)",
                (a["created_at"], a["behavior"], a["confidence"], a["student_id"],
                 a["screenshot_path"], a.get("firebase_url", ""), a["video_name"], a["video_time"]),
            )
            self.conn.commit()
            return cur.lastrowid

    def set_url(self, alert_id, url):
        with self.lock:
            self.conn.execute("UPDATE alerts SET firebase_url=? WHERE id=?", (url, alert_id))
            self.conn.commit()

    def all(self):
        with self.lock:
            cur = self.conn.execute("SELECT " + ", ".join(COLUMNS) + " FROM alerts ORDER BY id DESC")
            return cur.fetchall()

    def get(self, alert_id):
        with self.lock:
            cur = self.conn.execute(
                "SELECT " + ", ".join(COLUMNS) + " FROM alerts WHERE id=?", (alert_id,)
            )
            return cur.fetchone()

    def delete(self, ids):
        with self.lock:
            self.conn.executemany("DELETE FROM alerts WHERE id=?", [(int(i),) for i in ids])
            self.conn.commit()

    def export_csv(self, path):
        rows = self.all()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            w.writerows(rows)
        return len(rows)


# Backward-compatible alias
AlertDB = IncidentDatabaseManager
