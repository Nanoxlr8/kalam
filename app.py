"""Kalam — local push-to-talk dictation for Windows (Arabic + English), powered by Gemini.

Run:  pythonw app.py      (or double-click Kalam.vbs)
"""
import ctypes
import os
import queue
import sys
import threading
import time
import wave

import keyboard
import numpy as np
import pyperclip
import requests
from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import core
import ui
import webui

MAX_RECORD_SEC = 6 * 60
HEDGE_AFTER = 4.0     # s without a first word before sending a duplicate request
HEDGE_GAP = 5.0       # s after that before also trying the fallback model
RACE_TIMEOUT = 45.0   # give up after this long
HOLD_THRESHOLD = 0.45  # held longer than this → push-to-talk (release stops)


def set_clipboard(text):
    """Another app can hold the clipboard for a moment; retry, then fall back to Qt's clipboard."""
    for _ in range(8):
        try:
            pyperclip.copy(text)
            return
        except Exception:
            time.sleep(0.04)
    QGuiApplication.clipboard().setText(text)


def make_sounds():
    """Tiny soft tones for start / stop / error, generated once into the data folder."""
    out = {}
    specs = {"start": [(660, .05), (880, .07)], "stop": [(880, .05), (620, .07)], "error": [(300, .12)]}
    for name, notes in specs.items():
        path = os.path.join(core.DATA_DIR, f"{name}.wav")
        out[name] = path
        if os.path.exists(path):
            continue
        sr = 22050
        parts = []
        for f, d in notes:
            t = np.arange(int(sr * d)) / sr
            env = np.minimum(1, np.minimum(t / 0.008, (d - t) / 0.02))
            parts.append(0.18 * np.sin(2 * np.pi * f * t) * env)
        data = (np.concatenate(parts) * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(data.tobytes())
    return out


class Controller(QObject):
    sig_hotkey = Signal(str)
    sig_level = Signal(float)
    sig_preview = Signal(int, str)
    sig_done = Signal(int, dict)
    sig_fail = Signal(int, str)
    sig_ping = Signal(str, str)
    sig_status = Signal(int, str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.settings = core.Settings()
        self.db = core.DB()
        self.gemini = core.Gemini()
        self.recorder = core.Recorder(on_level=self.sig_level.emit)
        self.state = "idle"
        self.job = 0
        self.cooldown = {}
        self.key_down = False
        self.down_at = 0.0
        self.started_by_press = False
        self.target = ("", 0)
        self.t_stop = 0.0
        self.rec_sec = 0.0
        self.hook = None
        self.esc_hook = None
        self.tray_hint_shown = False
        self.sounds = make_sounds()

        self.overlay = ui.Overlay()
        self.overlay.clicked.connect(self.toggle)
        self.overlay.moved.connect(self._save_pill_pos)
        if self.settings["pill_pos"]:
            self.overlay.saved_pos = tuple(self.settings["pill_pos"])
        self.win = webui.WebWindow(self)

        self.sig_hotkey.connect(self._on_hotkey)
        self.sig_level.connect(self._on_level)
        self.sig_preview.connect(self._on_preview)
        self.sig_done.connect(self._on_done)
        self.sig_fail.connect(self._on_fail)
        self.sig_ping.connect(self._on_ping)
        self.sig_status.connect(lambda j, msg: j == self.job and self.overlay.set_status(msg))
        self.max_timer = QTimer(self, singleShot=True, timeout=self.stop)

        self._make_tray()
        self.apply_settings()
        self.win.show()
        QTimer.singleShot(300, self.win.bring_to_front)
        if not self.settings["api_key"]:
            QTimer.singleShot(1500, lambda: self.win.goto("settings"))

    # ------------------------------------------------------------ setup
    def _make_tray(self):
        self.tray = QSystemTrayIcon(ui.make_icon(), self.app)
        self.tray.setToolTip("Kalam — dictation")
        m = QMenu()
        m.addAction("Open Kalam", self.show_window)
        self.tray_rec = m.addAction("Start dictation", self.toggle)
        mm = m.addMenu("Mode")
        self.mode_actions = QActionGroup(m)
        for k, md in core.MODES.items():
            a = QAction(md["label"], mm, checkable=True)
            a.setData(k)
            a.triggered.connect(lambda _=False, k=k: self.set_mode(k))
            self.mode_actions.addAction(a)
            mm.addAction(a)
        m.addAction("Reset pill position", self._reset_pill)
        m.addSeparator()
        m.addAction("Quit", self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) and self.show_window())
        self.tray.show()

    def apply_settings(self):
        s = self.settings
        try:
            if self.hook:
                keyboard.unhook(self.hook)
            if self.esc_hook:
                keyboard.unhook(self.esc_hook)
        except (KeyError, ValueError):
            pass

        def on_key(e):
            self.sig_hotkey.emit(e.event_type)
            return False  # swallow the hotkey so the focused app never sees it

        def on_esc(e):
            if e.event_type == "down" and self.state != "idle":
                self.sig_hotkey.emit("esc")

        self.hook = keyboard.hook_key(s["hotkey"], on_key, suppress=True)
        self.esc_hook = keyboard.hook_key("esc", on_esc, suppress=False)
        for a in self.mode_actions.actions():
            a.setChecked(a.data() == s["mode"])
        self.overlay.set_idle_visible(bool(s["overlay_idle"]))
        self.win.refresh_all()

    def _save_pill_pos(self, x, y):
        self.settings["pill_pos"] = [x, y]
        self.settings.save()

    def _reset_pill(self):
        self.settings["pill_pos"] = None
        self.settings.save()
        self.overlay.reset_position()

    def show_window(self):
        self.win.bring_to_front()

    def _on_preview(self, jid, text):
        if jid == self.job:
            self.overlay.set_preview(text)
            self.win.preview(text)

    def notify_tray_once(self):
        if not self.tray_hint_shown:
            self.tray_hint_shown = True
            self.tray.showMessage("Kalam is still running",
                                  f"Press {self.settings['hotkey'].upper()} anywhere to dictate. Right-click the tray icon to quit.",
                                  ui.make_icon(), 3500)

    def quit(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if self.state == "recording":
            self.recorder.stop()
        self.tray.hide()
        self.app.quit()

    def play(self, name):
        if self.settings["sounds"]:
            try:
                import winsound
                winsound.PlaySound(self.sounds[name], winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except Exception:
                pass

    # ------------------------------------------------------------ public actions
    def set_mode(self, mode):
        self.settings["mode"] = mode
        self.settings.save()
        for a in self.mode_actions.actions():
            a.setChecked(a.data() == mode)
        self.win.on_mode()

    def toggle(self):
        if self.state == "idle":
            self.start()
        elif self.state == "recording":
            self.stop()

    def copy_text(self, text):
        if text:
            set_clipboard(text)
            self.win.flash("Copied to clipboard")

    def cooldown_left(self, model):
        return max(0, self.cooldown.get(model, 0) - time.time())

    def ping(self):
        key, model = self.settings["api_key"], self.settings["model"]

        def run():
            try:
                ms, _ = self.gemini.ping(key, model)
                self.sig_ping.emit("ping", f"{ms:.0f}")
            except Exception as e:
                self.sig_ping.emit("ping_err", str(e)[:120])
        threading.Thread(target=run, daemon=True).start()

    def test_connection(self, key, model):

        def run():
            try:
                ms, name = self.gemini.ping(key, model)
                self.sig_ping.emit("test", f"✓ Connected to {name} · round-trip {ms:.0f} ms")
            except core.ApiError as e:
                self.sig_ping.emit("test", f"✗ {e.status}: {e.message}")
            except Exception as e:
                self.sig_ping.emit("test", f"✗ {e}")
        threading.Thread(target=run, daemon=True).start()

    def _on_ping(self, kind, msg):
        if kind == "test":
            self.win.show_test(msg)
        else:
            self.win.ping_done(msg if kind == "ping_err" else None)

    # ------------------------------------------------------------ hotkey state machine
    def _on_hotkey(self, ev):
        now = time.monotonic()
        if ev == "esc":
            self.cancel()
        elif ev == "down":
            if self.key_down:
                return  # key auto-repeat while holding
            self.key_down = True
            self.down_at = now
            if self.state == "idle":
                self.started_by_press = True
                self.start()
            elif self.state == "recording":
                self.started_by_press = False
                self.stop()
        elif ev == "up":
            self.key_down = False
            if self.state == "recording" and self.started_by_press and now - self.down_at > HOLD_THRESHOLD:
                self.stop()  # push-to-talk release
            self.started_by_press = False

    def _on_level(self, v):
        self.overlay.set_level(v)
        self.win.set_level(v)

    # ------------------------------------------------------------ recording
    def start(self):
        s = self.settings
        if not s["api_key"]:
            self.overlay.error("Add your Gemini API key in Settings first")
            self.show_window()
            self.win.goto("settings")
            return
        self.target = core.foreground_app()
        try:
            self.recorder.start(s["mic"])
        except Exception as e:
            self.play("error")
            self.overlay.error(f"Microphone error: {e}")
            return
        self.state = "recording"
        self.gemini.warm(s["api_key"], s["model"])  # TLS handshake happens while you talk
        self.overlay.recording()
        self.play("start")
        self.tray.setIcon(ui.make_icon(recording=True))
        self.tray_rec.setText("Stop dictation")
        self.max_timer.start(MAX_RECORD_SEC * 1000)
        self.win.on_state()

    def stop(self):
        if self.state != "recording":
            return
        self.max_timer.stop()
        self.t_stop = time.perf_counter()
        audio, encoded = self.recorder.stop()
        live_ms = (time.perf_counter() - self.t_stop) * 1000
        self.rec_sec = len(audio) / core.SR
        self.play("stop")
        self.tray.setIcon(ui.make_icon())
        self.tray_rec.setText("Start dictation")
        self.state = "processing"
        self.job += 1
        self.overlay.processing()
        self.win.on_state()
        s = self.settings
        job = dict(id=self.job, audio=audio, encoded=encoded, live_ms=live_ms, mode=s["mode"], key=s["api_key"], model=s["model"],
                   fallback=s["fallback_model"] if s["use_fallback"] else None, trim=s["trim_silence"],
                   vocab=list(s["vocabulary"]), dialect=s["dialect"], app=core.friendly_app(self.target[0]) if s["app_context"] else None,
                   snippets=list(s["snippets"]), replacements=list(s["replacements"]))
        threading.Thread(target=self._process, args=(job,), daemon=True).start()

    def cancel(self):
        if self.state == "recording":
            self.max_timer.stop()
            self.recorder.stop()
            self.tray.setIcon(ui.make_icon())
            self.tray_rec.setText("Start dictation")
        elif self.state != "processing":
            return
        self.job += 1  # any in-flight result is ignored
        self.state = "idle"
        self.overlay.cancelled()
        self.win.on_state()

    # ------------------------------------------------------------ worker thread
    def _process(self, job):
        jid = job["id"]
        audio = job["audio"]
        clip = core.trim_silence(audio) if job["trim"] else (audio if len(audio) > core.SR * 0.3 else None)
        if clip is None:
            self.sig_fail.emit(jid, "No speech detected")
            return
        if job["encoded"]:
            # Opus was encoded live while recording; send it whole (silence costs ~32 tokens/s, trivial)
            (data, mime), encode_ms, clip = job["encoded"], job["live_ms"], audio
        else:
            t = time.perf_counter()
            data, mime = core.encode(clip)
            encode_ms = (time.perf_counter() - t) * 1000
        prompt = core.build_prompt(job["mode"], job["vocab"], job["app"], job.get("dialect", "egyptian"))
        primary, fb = job["model"], job["fallback"] if job["fallback"] != job["model"] else None
        if fb and self.cooldown_left(primary) > 0 and self.cooldown_left(fb) == 0:
            primary, fb = fb, primary  # primary is cooling down after a 429 -> lead with the fallback
        base = dict(mode=job["mode"], rec_sec=self.rec_sec, audio_sec=len(clip) / core.SR, app=self.target[0])

        # Hedged requests: Google occasionally leaves a request queued for 30-70 s while an identical one
        # answers in ~1 s. If no word has arrived by the deadline, send the same audio again and take
        # whichever answers first.
        first_wait = HEDGE_AFTER + 0.15 * base["audio_sec"]
        plan = [(0.0, primary), (first_wait, primary), (first_wait + HEDGE_GAP, fb or primary)]
        q = queue.Queue()
        claimed = []          # index of the attempt that streamed the first word
        launched = []         # models, in launch order

        def attempt(idx, model):
            def on_text(txt):
                if not claimed:
                    claimed.append(idx)
                if claimed[0] == idx and jid == self.job:
                    self.sig_preview.emit(jid, txt)
            try:
                q.put(("ok", idx, model, self.gemini.transcribe(job["key"], model, prompt, data, mime, on_text=on_text)))
            except Exception as e:  # reported to the race loop
                q.put(("err", idx, model, e))

        def launch():
            idx = len(launched)
            model = plan[idx][1]
            launched.append(model)
            threading.Thread(target=attempt, args=(idx, model), daemon=True).start()
            if idx:
                label = core.MODELS.get(model, {}).get("label", model)
                self.sig_status.emit(jid, "Google is slow, asking again..." if model == primary else f"Trying {label}...")

        t0 = time.monotonic()
        launch()
        failed = set()
        while True:
            if jid != self.job:
                return  # cancelled with Esc
            elapsed = time.monotonic() - t0
            if elapsed > RACE_TIMEOUT:
                self.sig_fail.emit(jid, "Gemini is too slow right now, try again")
                return
            nxt = plan[len(launched)][0] if len(launched) < len(plan) and not claimed else None
            try:
                kind, idx, m, res = q.get(timeout=0.2)
            except queue.Empty:
                if nxt is not None and time.monotonic() - t0 >= nxt:
                    launch()
                continue
            if kind == "ok":
                for k, lm in enumerate(launched):  # abandoned duplicates still count toward Google's quota
                    if k != idx and k not in failed:
                        self.db.add(ts=time.time(), model=lm, status="hedged", **base)
                a_tok, t_tok, o_tok = core.split_usage(res["usage"])
                text = core.postprocess(res["text"], job["snippets"], job["replacements"], job["vocab"])
                self.sig_done.emit(jid, dict(base, model=m, text=text, audio_tokens=a_tok, text_tokens=t_tok, out_tokens=o_tok,
                                             encode_ms=encode_ms, ttft_ms=res["ttft_ms"], api_ms=res["api_ms"],
                                             fallback=m != job["model"], hedged=idx > 0))
                return
            failed.add(idx)
            e = res
            if isinstance(e, core.ApiError):
                self.db.add(ts=time.time(), model=m, status="rate_limited" if e.status == 429 else "error",
                            error=f"{e.status}: {e.message}"[:300], **base)
                if e.status == 429:
                    self.cooldown[m] = time.time() + (e.retry_after or 30)
                    if e.quota:
                        learned = dict(self.settings["learned"])
                        learned[m] = {**learned.get(m, {}), **e.quota}
                        self.settings["learned"] = learned
                        self.settings.save()
                retryable = e.status in (429, 500, 503, 504)
            else:
                retryable = isinstance(e, requests.RequestException)
            if retryable and len(launched) < len(plan):
                # rate-limited model: skip its duplicate and go straight to the fallback
                if isinstance(e, core.ApiError) and e.status == 429 and plan[len(launched)][1] == m and len(launched) + 1 < len(plan):
                    failed.add(len(launched))
                    launched.append(m)
                launch()
                continue
            if len(failed) < len(launched) and retryable:
                continue  # another attempt is still running
            if isinstance(e, core.ApiError):
                self.sig_fail.emit(jid, self._friendly_error(e, m))
            elif isinstance(e, requests.Timeout):
                self.sig_fail.emit(jid, "Gemini timed out")
            else:
                self.sig_fail.emit(jid, "Network problem, check your internet")
            return

    @staticmethod
    def _friendly_error(e, model):
        if e.status == 429:
            wait = f" — try again in {int(e.retry_after)}s" if e.retry_after else ""
            return f"Rate limit on {model}{wait}"
        if e.status in (401, 403) or "API key" in e.message:
            return "API key rejected — check Settings"
        if e.status == 503:
            return "Gemini is overloaded, try again"
        return f"Gemini error {e.status}: {e.message}"

    # ------------------------------------------------------------ results (UI thread)
    def _on_fail(self, jid, msg):
        if jid != self.job:
            return
        self.state = "idle"
        self.play("error")
        self.overlay.error(msg)
        self.win.on_state()
        self.win.refresh_live()

    def _on_done(self, jid, r):
        if jid != self.job:
            return
        self.state = "idle"
        text = r.pop("text")
        fallback = r.pop("fallback")
        hedged = r.pop("hedged", False)
        if not text.strip():
            self.db.add(ts=time.time(), status="empty", **r)
            self.overlay.error("Didn't catch that — try again")
            self.win.on_state()
            return
        t = time.perf_counter()
        own_window = self.target[1] == os.getpid()
        pasted = False
        if self.settings["auto_paste"] and not own_window:
            self.paste(text)
            pasted = True
        else:
            set_clipboard(text)
        paste_ms = (time.perf_counter() - t) * 1000
        total_ms = (time.perf_counter() - self.t_stop) * 1000
        self.db.add(ts=time.time(), status="ok", paste_ms=paste_ms, total_ms=total_ms, words=len(text.split()), text=text, **r)
        verb = "Pasted" if pasted else "Copied"
        self.overlay.done(f"{verb} · {len(text.split())} words", f"{total_ms / 1000:.1f}s")
        meta = f"{r['model']} · {core.MODES[r['mode']]['label']} · {r['audio_sec']:.1f}s audio · {total_ms / 1000:.1f}s"
        if fallback:
            meta += " · via fallback"
        if hedged:
            meta += " · re-sent (Google was slow)"
        if r["app"]:
            meta += f" · {r['app']}"
        self.win.on_result(text, meta, dict(ts=time.time(), model=r["model"], mode=r["mode"], total_ms=total_ms,
                                            app=r["app"], fallback=fallback))
        self.win.on_state()

    def paste(self, text):
        cb = QGuiApplication.clipboard()
        saved = None
        if self.settings["restore_clipboard"]:
            md = cb.mimeData()
            if md is not None and md.formats():
                saved = QMimeData()
                for f in md.formats():
                    saved.setData(f, md.data(f))
        set_clipboard(text)
        time.sleep(0.03)
        keyboard.send("ctrl+v")
        if saved is not None:
            QTimer.singleShot(700, lambda: cb.setMimeData(saved))


SERVER_NAME = "Kalam.Dictation.Instance"


def already_running():
    """If Kalam is already running, ask it to show its window and return True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def listen_for_show(ctl):
    QLocalServer.removeServer(SERVER_NAME)
    srv = QLocalServer(ctl)
    srv.newConnection.connect(lambda: (srv.nextPendingConnection(), ctl.show_window()))
    srv.listen(SERVER_NAME)
    return srv


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kalam.Dictation")
    except Exception:
        pass
    app = QApplication(sys.argv)
    if already_running():
        return
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(ui.QSS)
    f = app.font()
    f.setFamily("Segoe UI")
    f.setPointSizeF(10)
    app.setFont(f)
    app.setWindowIcon(ui.make_icon())
    ico = os.path.join(core.DATA_DIR, "kalam.ico")
    if not os.path.exists(ico):
        ui.make_logo(256).save(ico, "ICO")
    ctl = Controller(app)
    ctl._server = listen_for_show(ctl)
    sys.exit(app.exec())


if __name__ == "__main__":
    import traceback

    def log_exc(*a):
        with open(os.path.join(core.DATA_DIR, "error.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("\n[%Y-%m-%d %H:%M:%S]\n") + "".join(traceback.format_exception(*a)))

    sys.excepthook = log_exc
    threading.excepthook = lambda a: log_exc(a.exc_type, a.exc_value, a.exc_traceback)
    main()
