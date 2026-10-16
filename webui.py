"""Kalam main window: a QWebEngine page (web/index.html) talking to Python over QWebChannel."""
import ctypes
import json
import os
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

import core
import ui

HERE = os.path.dirname(os.path.abspath(__file__))


def pct(values, p):
    return ui.pct(values, p)


class Bridge(QObject):
    push = Signal(str)  # JSON events → page

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.ctl = win.ctl
        self.s = win.ctl.settings

    def emit(self, kind, **data):
        self.push.emit(json.dumps({"type": kind, **data}, ensure_ascii=False))

    # ---------------------------------------------------------------- reads
    @Slot(result=str)
    def init(self):
        s = self.s
        return json.dumps({
            "settings": {k: s[k] for k in core.DEFAULT_SETTINGS if k not in ("learned", "limits", "prices")},
            "models": [{"id": k, "label": m["label"], "note": m["note"]} for k, m in core.MODELS.items()],
            "modes": {k: {"label": m["label"], "desc": m["desc"], "example": m["example"]} for k, m in core.MODES.items()},
            "dialects": [{"id": k, "label": v[0]} for k, v in core.DIALECTS.items()],
            "hotkeys": core.HOTKEYS,
            "mics": [{"id": i, "label": n} for i, n in core.list_mics()],
            "data_dir": core.DATA_DIR,
            "state": self.ctl.state,
        }, ensure_ascii=False)

    @Slot(result=str)
    def live(self):
        db, s = self.ctl.db, self.s
        model = s["model"]
        L = db.latencies(30)
        tv = [x["total_ms"] for x in L]
        lim = s.limits(model)
        u = db.rate_usage(model)
        fb = s["fallback_model"] if s["use_fallback"] and s["fallback_model"] != model else None
        fbi = None
        if fb:
            fu = db.rate_usage(fb)
            fbi = {"model": fb, "label": core.MODELS.get(fb, {}).get("label", fb), "rpd": [fu["rpd"], s.limits(fb)["rpd"]]}
        rows = db.summary(core.local_day_start())
        words = sum(r["words"] or 0 for r in rows)
        audio = sum(r["audio_sec"] or 0 for r in rows)
        return json.dumps({
            "state": self.ctl.state,
            "latency": {"last": L[-1] if L else None, "spark": tv[-24:], "p50": pct(tv, .5), "p90": pct(tv, .9),
                        "rtt": self.ctl.gemini.last_rtt_ms},
            "limits": {"model": model, "label": core.MODELS.get(model, {}).get("label", model),
                       "learned": bool(s["learned"].get(model)),
                       "rpm": [u["rpm"], lim["rpm"]], "rpd": [u["rpd"], lim["rpd"]], "tpm": [u["tpm"], lim["tpm"]],
                       "reset_in": max(0, u["reset_ts"] - time.time()), "cooldown": self.ctl.cooldown_left(model),
                       "fallback": fbi},
            "today": {"n": sum(r["ok"] or 0 for r in rows), "words": words, "audio_min": audio / 60,
                      "saved_min": max(0.0, words / 40 - audio / 60), "limited": sum(r["limited"] or 0 for r in rows)},
            "last": self.win.last,
        }, ensure_ascii=False)

    @Slot(str, result=str)
    def history(self, search):
        return json.dumps(self.ctl.db.history(search.strip()), ensure_ascii=False)

    @Slot(int, result=str)
    def usage(self, period):
        s, db = self.s, self.ctl.db
        since = core.quota_day_window()[0] if period == 0 else time.time() - (7 if period == 1 else 30) * 86400
        days = 1 if period == 0 else (7 if period == 1 else 30)
        rows = db.summary(since)
        for r in rows:
            pr = s.price(r["model"])
            r["cost"] = (r["audio_tokens"] * pr["audio"] + r["text_tokens"] * pr["text"] + r["out_tokens"] * pr["out"]) / 1e6
        lat = []
        for m in core.MODELS:
            Lm = db.latencies(50, m)
            tv = [x["total_ms"] for x in Lm]
            lat.append({"model": m, "n": len(Lm), "p50": pct(tv, .5), "p90": pct(tv, .9),
                        "ttft": pct([x["ttft_ms"] for x in Lm], .5),
                        "audio": (sum(x["audio_sec"] or 0 for x in Lm) / len(Lm)) if Lm else None})
        limits = [{"model": m, **s.limits(m), "learned": s["learned"].get(m, {})} for m in core.MODELS]
        total_cost = sum(r["cost"] for r in rows)
        return json.dumps({"rows": rows, "days": days, "monthly": total_cost / days * 30, "lat": lat, "limits": limits})

    # ---------------------------------------------------------------- actions
    @Slot()
    def toggle(self):
        self.ctl.toggle()

    @Slot(str)
    def setMode(self, mode):
        self.ctl.set_mode(mode)

    @Slot(str, result=str)
    def saveSettings(self, payload):
        d = json.loads(payload)
        for k, v in d.items():
            if k in core.DEFAULT_SETTINGS:
                self.s[k] = v
        self.s.save()
        if set(d) & {"hotkey", "overlay_idle", "mode", "model", "use_fallback", "fallback_model", "dialect"}:
            self.ctl.apply_settings()
        return "ok"

    @Slot(str)
    def saveLimits(self, payload):
        out = {}
        for m, vals in json.loads(payload).items():
            base = {k: core.MODELS[m][k] for k in ("rpm", "rpd", "tpm")}
            base.update(self.s["learned"].get(m, {}))
            d = {k: int(v) for k, v in vals.items() if str(v).isdigit() and int(v) != base.get(k)}
            if d:
                out[m] = d
        self.s["limits"] = out
        self.s.save()

    @Slot(str, str)
    def testConnection(self, key, model):
        self.ctl.test_connection(key, model)

    @Slot()
    def ping(self):
        self.ctl.ping()

    @Slot(int)
    def deleteItem(self, rid):
        self.ctl.db.delete(rid)

    @Slot()
    def clearHistory(self):
        self.ctl.db.clear_history()

    @Slot(str)
    def copy(self, text):
        self.ctl.copy_text(text)

    @Slot(str)
    def openUrl(self, url):
        os.startfile(url)


class WebWindow(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        h = ctl.db.q("SELECT ts, model, mode, total_ms, app, text FROM requests WHERE status='ok' AND text IS NOT NULL ORDER BY ts DESC LIMIT 1")
        self.last = h[0] if h else None
        self.setWindowTitle("Kalam — كلام")
        self.setWindowIcon(ui.make_icon())
        self.resize(1240, 820)
        self.setMinimumSize(1000, 680)
        self.view = QWebEngineView(self)
        self.view.page().setBackgroundColor(ui.QColor("#0B0C12"))
        st = self.view.settings()
        st.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        self.view.setContextMenuPolicy(ui.Qt.NoContextMenu)
        self.bridge = Bridge(self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.load(QUrl.fromLocalFile(os.path.join(HERE, "web", "index.html")))
        self.setCentralWidget(self.view)
        self._lvl_last = 0.0
        self.tick = QTimer(self, interval=2000, timeout=lambda: self.bridge.emit("tick"))
        self.tick.start()

    # ---- API used by the controller ----
    def on_state(self):
        self.bridge.emit("state", state=self.ctl.state)

    def on_mode(self):
        self.bridge.emit("mode", mode=self.ctl.settings["mode"])

    def on_result(self, text, meta, info=None):
        self.last = {"text": text, "meta": meta, **(info or {})}
        self.bridge.emit("result", **self.last)

    def preview(self, text):
        self.bridge.emit("preview", text=text)

    def set_level(self, v):
        now = time.monotonic()
        if now - self._lvl_last > 0.05:
            self._lvl_last = now
            self.bridge.emit("level", v=round(v, 3))

    def refresh_all(self):
        self.bridge.emit("reload_settings")

    def refresh_live(self):
        self.bridge.emit("tick")

    def flash(self, msg):
        self.bridge.emit("toast", msg=msg)

    def show_test(self, msg):
        self.bridge.emit("test", msg=msg)

    def ping_done(self, err=None):
        self.bridge.emit("ping", err=err)

    def goto(self, page):
        self.bridge.emit("goto", page=page)

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        try:  # Windows blocks focus stealing; a synthetic Alt tap lifts that restriction for us
            u = ctypes.windll.user32
            hwnd = int(self.winId())
            u.keybd_event(0x12, 0, 0, 0)
            u.keybd_event(0x12, 0, 2, 0)
            u.ShowWindow(hwnd, 9)
            u.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.ctl.notify_tray_once()
