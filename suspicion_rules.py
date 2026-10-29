from collections import deque

import numpy as np

import settings as cfg


def center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def inside(box, pt, margin):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    return (x1 - margin * w <= pt[0] <= x2 + margin * w) and (y1 - margin * h <= pt[1] <= y2 + margin * h)


def select_monitored(persons):
    if not persons:
        return []
    tallest = max(p["box"][3] - p["box"][1] for p in persons)
    return [p for p in persons if (p["box"][3] - p["box"][1]) >= cfg.MIN_RELATIVE_HEIGHT * tallest]


def owner_of(det_box, monitored):
    pt = center(det_box)
    best, best_d = None, None
    for p in monitored:
        if not inside(p["box"], pt, cfg.PHONE_MARGIN):
            continue
        c = center(p["box"])
        d = (c[0] - pt[0]) ** 2 + (c[1] - pt[1]) ** 2
        if best is None or d < best_d:
            best, best_d = p["id"], d
    return best


def head_signals(kp):
    if kp is None:
        return None, None, 0.0
    k = cfg.KEYPOINT_CONF
    nose, eye_a, eye_b, sh_a, sh_b = kp[0], kp[1], kp[2], kp[5], kp[6]
    if nose[2] < k:
        return None, None, 0.0
    yaw, ratio = None, None
    confs = [float(nose[2])]
    if eye_a[2] >= k and eye_b[2] >= k:
        d = abs(eye_a[0] - eye_b[0])
        if d >= 4:
            yaw = float((nose[0] - (eye_a[0] + eye_b[0]) / 2.0) / d)
            confs += [float(eye_a[2]), float(eye_b[2])]
    if sh_a[2] >= k and sh_b[2] >= k:
        w = abs(sh_a[0] - sh_b[0])
        if w >= 8:
            ratio = float((nose[0] - (sh_a[0] + sh_b[0]) / 2.0) / w)
            confs += [float(sh_a[2]), float(sh_b[2])]
    return yaw, ratio, float(np.mean(confs))


def has_neighbor(p, monitored, direction):
    if not cfg.REQUIRE_NEIGHBOR_DIRECTION:
        return True
    pc = center(p["box"])
    pw = p["box"][2] - p["box"][0]
    ph = p["box"][3] - p["box"][1]
    for q in monitored:
        if q["id"] == p["id"]:
            continue
        qc = center(q["box"])
        dx = qc[0] - pc[0]
        if dx * direction <= 0:
            continue
        if abs(dx) > cfg.NEIGHBOR_MAX_WIDTHS * pw:
            continue
        if abs(qc[1] - pc[1]) > cfg.NEIGHBOR_MAX_DY_HEIGHTS * ph:
            continue
        return True
    return False


def baseline_of(hist, t):
    while hist and t - hist[0][0] > cfg.BASELINE_SECONDS:
        hist.popleft()
    if len(hist) < cfg.BASELINE_MIN_SAMPLES:
        return None
    return float(np.median([v for _, v in hist]))


def window_sum(events, t):
    while events and t - events[0][0] > cfg.TURN_WINDOW_SECONDS:
        events.popleft()
    return sum(dt for _, dt, flag in events if flag)


class ExamineeTrackerState:
    def __init__(self, t):
        self.first_seen = t
        self.last_t = t
        self.yaw_hist = deque()
        self.ratio_hist = deque()
        self.gaze_hist = deque()
        self.head_events = deque()
        self.gaze_events = deque()
        self.phone_frames = 0
        self.phone_conf = 0.0
        self.custom_frames = {}
        self.last_alert = {}
        self.red_until = -1.0
        self.label = None


class CheatingAnalysisEngine:
    def __init__(self):
        self.states = {}

    def reset(self):
        self.states.clear()

    def _flag(self, st, dec, t, name, conf):
        st.red_until = t + cfg.RED_HOLD_SECONDS
        st.label = name
        if t - st.last_alert.get(name, -1e9) >= cfg.ALERT_COOLDOWN_SECONDS:
            st.last_alert[name] = t
            dec["alerts"].append({"behavior": name, "confidence": round(float(min(max(conf, 0.0), 1.0)), 3)})

    def update(self, t, persons, phones, customs, gaze):
        decisions = {}
        monitored = select_monitored(persons)
        mon_ids = set(p["id"] for p in monitored)

        phone_conf = {}
        for ph in phones:
            oid = owner_of(ph["box"], monitored)
            if oid is not None:
                phone_conf[oid] = max(phone_conf.get(oid, 0.0), ph["conf"])

        custom_conf = {}
        for cd in customs:
            oid = owner_of(cd["box"], monitored)
            if oid is not None:
                d = custom_conf.setdefault(oid, {})
                d[cd["name"]] = max(d.get(cd["name"], 0.0), cd["conf"])

        for p in persons:
            sid = p["id"]
            st = self.states.get(sid)
            if st is None:
                st = ExamineeTrackerState(t)
                self.states[sid] = st
            dec = {"suspect": False, "label": None, "alerts": [], "debug": "", "debug_row": None}
            decisions[sid] = dec

            dt = min(max(t - st.last_t, 0.0), 1.0)
            st.last_t = t
            if sid not in mon_ids:
                continue
            warm = (t - st.first_seen) < cfg.WARMUP_SECONDS

            pc = phone_conf.get(sid)
            if pc is not None:
                st.phone_frames += 1
                st.phone_conf = pc
            else:
                st.phone_frames = 0
            if st.phone_frames >= cfg.PHONE_CONFIRM_FRAMES:
                self._flag(st, dec, t, "Phone detected", st.phone_conf)

            seen = custom_conf.get(sid, {})
            for name in list(st.custom_frames.keys()):
                if name not in seen:
                    st.custom_frames[name] = 0
            for name, conf in seen.items():
                st.custom_frames[name] = st.custom_frames.get(name, 0) + 1
                if st.custom_frames[name] >= cfg.PHONE_CONFIRM_FRAMES:
                    self._flag(st, dec, t, name, conf)

            yaw, ratio, kconf = head_signals(p["kp"])
            yaw_dev, ratio_dev = None, None
            if yaw is not None:
                st.yaw_hist.append((t, yaw))
                b = baseline_of(st.yaw_hist, t)
                if b is not None:
                    yaw_dev = yaw - b
            if ratio is not None:
                st.ratio_hist.append((t, ratio))
                b = baseline_of(st.ratio_hist, t)
                if b is not None:
                    ratio_dev = ratio - b

            dev, thr = None, None
            if yaw_dev is not None:
                dev, thr = yaw_dev, cfg.YAW_THRESHOLD
            elif ratio_dev is not None:
                dev, thr = ratio_dev, cfg.HEAD_TURN_RATIO
            head_flag = False
            if dev is not None and abs(dev) >= thr:
                head_flag = has_neighbor(p, monitored, 1 if dev > 0 else -1)
            st.head_events.append((t, dt, head_flag))
            if not warm and window_sum(st.head_events, t) >= cfg.HEAD_TURN_SECONDS:
                self._flag(st, dec, t, "Looking away (head turned)", kconf)

            gaze_dev = None
            gaze_flag = False
            g = gaze.get(sid)
            if g is not None:
                st.gaze_hist.append((t, g))
                b = baseline_of(st.gaze_hist, t)
                if b is not None:
                    gaze_dev = g - b
                    if abs(gaze_dev) >= cfg.GAZE_THRESHOLD:
                        gaze_flag = has_neighbor(p, monitored, 1 if gaze_dev > 0 else -1)
            st.gaze_events.append((t, dt, gaze_flag))
            if not warm and window_sum(st.gaze_events, t) >= cfg.HEAD_TURN_SECONDS:
                score = min(1.0, abs(gaze_dev or 0.0) / (2.0 * cfg.GAZE_THRESHOLD))
                self._flag(st, dec, t, "Suspicious gaze direction", score)

            dec["suspect"] = t < st.red_until
            dec["label"] = st.label if dec["suspect"] else None
            dec["debug_row"] = (yaw_dev, ratio_dev, gaze_dev, head_flag, gaze_flag)
            if cfg.SHOW_DEBUG:
                yd = "-" if dev is None else format(dev, "+.2f")
                gd = "-" if gaze_dev is None else format(gaze_dev, "+.2f")
                dec["debug"] = "head " + yd + " gaze " + gd

        for sid in [k for k, s in self.states.items() if t - s.last_t > 120.0]:
            del self.states[sid]
        return decisions


# Backward-compatible aliases
StudentState = ExamineeTrackerState
BehaviorEngine = CheatingAnalysisEngine
