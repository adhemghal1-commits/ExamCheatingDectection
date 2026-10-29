import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import settings as cfg


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else cfg.DEBUG_LOG_PATH
    if not path.exists():
        print("No debug log found at", path)
        print("Set SHOW_DEBUG = True in settings.py, run a video, then run this script again.")
        return
    per = defaultdict(lambda: {"yaw": [], "ratio": [], "gaze": [], "head": 0, "gaze_flag": 0, "n": 0})
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = per[row["student_id"]]
            s["n"] += 1
            for key, col in (("yaw", "yaw_dev"), ("ratio", "ratio_dev"), ("gaze", "gaze_dev")):
                v = to_float(row[col])
                if v is not None:
                    s[key].append(abs(v))
            s["head"] += int(row["head_flag"] or 0)
            s["gaze_flag"] += int(row["gaze_flag"] or 0)

    def pct(vals, q):
        return format(float(np.percentile(vals, q)), ".3f") if vals else "-"

    print("Student  frames  yaw|p50 p95 max|  gaze|p50 p95 max|  head%  gaze%")
    all_yaw, all_gaze = [], []
    for sid, s in sorted(per.items(), key=lambda kv: int(kv[0])):
        all_yaw += s["yaw"]
        all_gaze += s["gaze"]
        n = max(s["n"], 1)
        print(
            str(sid).rjust(7), str(s["n"]).rjust(7),
            pct(s["yaw"], 50).rjust(8), pct(s["yaw"], 95).rjust(6), pct(s["yaw"], 100).rjust(6),
            pct(s["gaze"], 50).rjust(8), pct(s["gaze"], 95).rjust(6), pct(s["gaze"], 100).rjust(6),
            format(100.0 * s["head"] / n, ".1f").rjust(7), format(100.0 * s["gaze_flag"] / n, ".1f").rjust(7),
        )
    print()
    print("Current YAW_THRESHOLD =", cfg.YAW_THRESHOLD, "| 95th percentile of all |yaw dev| =", pct(all_yaw, 95))
    print("Current GAZE_THRESHOLD =", cfg.GAZE_THRESHOLD, "| 95th percentile of all |gaze dev| =", pct(all_gaze, 95))
    print("If a threshold is below the 95th percentile, normal behavior is flagged too often: raise it.")


if __name__ == "__main__":
    main()
