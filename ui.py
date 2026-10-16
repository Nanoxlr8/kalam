"""Kalam UI: theme, logo, floating overlay, main window pages."""
import ctypes
import math
import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient, QTextOption)
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QTextEdit,
                               QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import core

C = {
    "bg": "#0E0F15", "side": "#12131B", "card": "#181A25", "card2": "#1E2130", "border": "#262A3B",
    "text": "#ECEDF5", "muted": "#8B90A8", "dim": "#5C6078",
    "accent": "#7C5CFF", "accent2": "#22D3EE", "good": "#34D399", "warn": "#FBBF24", "bad": "#F87171", "rec": "#FF4D6D",
}

QSS = f"""
* {{ font-family: 'Segoe UI', 'Segoe UI Variable Text', Tahoma; color: {C['text']}; }}
QMainWindow, #root {{ background: {C['bg']}; }}
#side {{ background: {C['side']}; border-right: 1px solid {C['border']}; }}
#nav {{ background: transparent; border: none; outline: none; font-size: 10.5pt; }}
#nav::item {{ padding: 10px 14px; margin: 2px 10px; border-radius: 9px; color: {C['muted']}; }}
#nav::item:hover {{ background: {C['card']}; color: {C['text']}; }}
#nav::item:selected {{ background: {C['card2']}; color: {C['text']}; border-left: 3px solid {C['accent']}; }}
#card {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 16px; }}
#h1 {{ font-size: 19pt; font-weight: 600; }}
#h2 {{ font-size: 11.5pt; font-weight: 600; }}
#cardTitle {{ font-size: 9pt; font-weight: 600; color: {C['muted']}; letter-spacing: 0.5px; }}
#big {{ font-size: 24pt; font-weight: 600; }}
#muted {{ color: {C['muted']}; }}
#dim {{ color: {C['dim']}; font-size: 8.5pt; }}
QPushButton {{ background: {C['card2']}; border: 1px solid {C['border']}; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {C['accent']}; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton#primary {{ background: {C['accent']}; border: none; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: #8F74FF; }}
QPushButton#seg {{ border-radius: 0; padding: 8px 18px; background: {C['card2']}; color: {C['muted']}; }}
QPushButton#seg:checked {{ background: {C['accent']}; color: white; border-color: {C['accent']}; font-weight: 600; }}
QPushButton#segL {{ border-top-left-radius: 9px; border-bottom-left-radius: 9px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{ background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 9px;
    padding: 7px 10px; selection-background-color: {C['accent']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {C['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {C['card2']}; border: 1px solid {C['border']}; selection-background-color: {C['accent']}; }}
QTableWidget {{ background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 10px; gridline-color: {C['border']};
    selection-background-color: #2C2560; }}
QHeaderView::section {{ background: {C['card2']}; color: {C['muted']}; border: none; border-bottom: 1px solid {C['border']};
    padding: 7px; font-weight: 600; }}
QTableCornerButton::section {{ background: {C['card2']}; border: none; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {C['border']}; background: {C['bg']}; }}
QCheckBox::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: {C['card2']}; border: 1px solid {C['border']}; padding: 6px; }}
"""


def lat_color(ms):
    if ms is None:
        return C["muted"]
    return C["good"] if ms < 2000 else C["warn"] if ms < 4000 else C["bad"]


def frac_color(f):
    return C["good"] if f < 0.6 else C["warn"] if f < 0.85 else C["bad"]


def fmt_ms(ms):
    if ms is None:
        return "—"
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms"


def fmt_n(n):
    return f"{n / 1_000_000:.1f}M" if n >= 1_000_000 else f"{n / 1000:.1f}k" if n >= 1000 else str(int(n))


def is_rtl(line):
    for ch in line:
        if "֐" <= ch <= "ࣿ" or "ﭐ" <= ch <= "ﻼ":
            return True
        if ch.isalpha():
            return False
    return False


def bidi_html(text, size_pt=None, color=None):
    """Render each line with its own direction: Arabic lines RTL/right, English lines LTR/left."""
    import html
    style = (f"font-size:{size_pt}pt;" if size_pt else "") + (f"color:{color};" if color else "")
    out = []
    for line in text.split("\n"):
        d = "rtl" if is_rtl(line) else "ltr"
        out.append(f'<p dir="{d}" align="{"right" if d == "rtl" else "left"}" style="margin:0 0 3px 0;{style}">'
                   f'{html.escape(line) or "&nbsp;"}</p>')
    return "".join(out)


def pct(values, p):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


# ---------------------------------------------------------------------------
# Logo: gradient squircle with a voice waveform
# ---------------------------------------------------------------------------
def make_logo(size=256, recording=False):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size
    g = QLinearGradient(0, 0, s, s)
    if recording:
        g.setColorAt(0, QColor("#FF4D6D"))
        g.setColorAt(1, QColor("#FF8A5C"))
    else:
        g.setColorAt(0, QColor("#7C5CFF"))
        g.setColorAt(1, QColor("#22D3EE"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92), s * 0.26, s * 0.26)
    p.fillPath(path, g)
    # soft top highlight
    hl = QLinearGradient(0, 0, 0, s)
    hl.setColorAt(0, QColor(255, 255, 255, 60))
    hl.setColorAt(0.5, QColor(255, 255, 255, 0))
    p.fillPath(path, hl)
    heights = [0.22, 0.42, 0.62, 0.42, 0.22] if not recording else [0.3, 0.55, 0.7, 0.5, 0.3]
    bw = s * 0.085
    gap = s * 0.05
    total = len(heights) * bw + (len(heights) - 1) * gap
    x = (s - total) / 2
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 245))
    for h in heights:
        bh = s * h
        p.drawRoundedRect(QRectF(x, (s - bh) / 2, bw, bh), bw / 2, bw / 2)
        x += bw + gap
    p.end()
    return pm


def make_icon(recording=False):
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(make_logo(sz, recording))
    return ic


# ---------------------------------------------------------------------------
# Floating overlay (never takes focus, so the paste lands in your app)
# ---------------------------------------------------------------------------
class Overlay(QWidget):
    clicked = Signal()
    moved = Signal(int, int)   # user dragged the pill → new top-left position
    W, H = 380, 64

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)
        self.state = "hidden"
        self.idle_visible = False
        self.levels = deque([0.0] * 36, maxlen=36)
        self.level = 0.0
        self.t0 = time.monotonic()
        self.msg = ""
        self.sub = ""
        self.preview = ""
        self.cur_w = 60.0
        self.phase = 0.0
        self.anim = QTimer(self, interval=16, timeout=self._tick)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self._auto_hide)
        self._styled = False
        self.saved_pos = None      # (x, y) the user dragged it to
        self._press = None
        self._dragging = False
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Click to dictate · drag to move")
        self.guard = QTimer(self, interval=4000, timeout=self._keep_on_top)
        self.guard.start()

    # -- public API ---------------------------------------------------------
    def place(self):
        from PySide6.QtGui import QCursor, QGuiApplication
        if self.saved_pos:
            x, y = self.saved_pos
            from PySide6.QtCore import QPoint
            if QGuiApplication.screenAt(QPoint(x + self.W // 2, y + self.H - 20)):
                self.move(x, y)
                return
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        self.move(g.center().x() - self.W // 2, g.bottom() - self.H - 18)

    def reset_position(self):
        self.saved_pos = None
        self.place()
        if not self.isVisible() and self.idle_visible:
            self._go("idle")

    def _keep_on_top(self):
        """Windows sometimes drops 'always on top' (Win+D, full-screen apps, display changes) — re-assert it."""
        if self.state == "hidden":
            if self.idle_visible:
                self._go("idle")
            return
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication
        if not QGuiApplication.screenAt(self.geometry().center() + QPoint(0, 12)):
            self.saved_pos = None
            self.place()  # screen was unplugged → bring it back
        if not self.isVisible():
            self.show()
        try:
            ctypes.windll.user32.SetWindowPos(int(self.winId()), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
        except Exception:
            pass

    def set_level(self, v):
        self.level = v

    def recording(self):
        if not self.saved_pos:
            self.place()  # follow the screen you're working on
        self._go("recording")
        self.levels.extend([0.0] * 36)
        self.t0 = time.monotonic()

    def processing(self):
        self._go("processing")
        self.preview = ""
        self.status = ""
        self.t0 = time.monotonic()

    def set_preview(self, text):
        self.preview = " ".join(text.split())

    def set_status(self, text):
        self.status = text

    def done(self, msg, sub=""):
        self._go("done", msg, sub)
        self.hide_timer.start(1600)

    def error(self, msg):
        self._go("error", msg)
        self.hide_timer.start(3500)

    def cancelled(self):
        self._go("done", "Cancelled", "")
        self.hide_timer.start(900)

    def set_idle_visible(self, on):
        self.idle_visible = on
        if self.state in ("hidden", "idle"):
            self._auto_hide()

    # -- internals ----------------------------------------------------------
    def _go(self, state, msg="", sub=""):
        self.hide_timer.stop()
        self.state, self.msg, self.sub = state, msg, sub
        if not self.isVisible():
            self.place()
            self.show()
            self._no_activate()
        if not self.anim.isActive():
            self.anim.start()

    def _auto_hide(self):
        if self.idle_visible:
            self._go("idle")
        else:
            self.state = "hidden"
            self.anim.stop()
            self.hide()

    def _no_activate(self):
        if self._styled:
            return
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = -20, 0x08000000, 0x80, 0x8
            u = ctypes.windll.user32
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, u.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
            self._styled = True
        except Exception:
            pass

    def _target_w(self):
        return {"idle": 74, "recording": 250, "processing": 330, "done": 230, "error": 360}.get(self.state, 60)

    def _tick(self):
        self.phase += 0.016
        if self.state == "recording":
            self.levels.append(self.level)
        self.cur_w += (self._target_w() - self.cur_w) * 0.22
        self.update()
        if self.state == "idle" and abs(self._target_w() - self.cur_w) < 0.5:
            self.anim.stop()  # static when idle: no CPU use

    def mousePressEvent(self, e):
        self._press = (e.globalPosition().toPoint(), self.pos())
        self._dragging = False

    def mouseMoveEvent(self, e):
        if not self._press:
            return
        start, origin = self._press
        delta = e.globalPosition().toPoint() - start
        if not self._dragging and delta.manhattanLength() > 5:
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
        if self._dragging:
            self.move(origin + delta)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self.saved_pos = (self.x(), self.y())
            self.moved.emit(self.x(), self.y())
            self.setCursor(Qt.OpenHandCursor)
        elif self._press:
            self.clicked.emit()
        self._press = None
        self._dragging = False

    def paintEvent(self, _):
        if self.state == "hidden":
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = 18.0 if self.state == "idle" else 44.0
        w = self.cur_w
        r = QRectF((self.W - w) / 2, self.H - h - 6, w, h)
        # shadow
        for i, a in enumerate((28, 18, 10)):
            sh = r.adjusted(-2 - i * 2, -1 - i, 2 + i * 2, 3 + i * 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(sh, sh.height() / 2, sh.height() / 2)
        p.setBrush(QColor(18, 19, 27, 242))
        border = {"recording": QColor(255, 77, 109, 150), "error": QColor(248, 113, 113, 150),
                  "done": QColor(52, 211, 153, 120)}.get(self.state, QColor(124, 92, 255, 110))
        p.setPen(QPen(border, 1.2))
        p.drawRoundedRect(r, h / 2, h / 2)
        if self.state == "idle":
            # mini waveform in brand colors — click it to start dictating
            p.setPen(Qt.NoPen)
            heights = [4, 7, 10, 7, 4, 7, 10, 7, 4]
            x0 = r.center().x() - (len(heights) - 1) * 3.5
            for i, bh in enumerate(heights):
                c = QColor("#7C5CFF") if i < 4 else QColor("#22D3EE") if i > 4 else QColor("#5B7CFF")
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x0 + i * 7 - 1.25, r.center().y() - bh / 2, 2.5, bh), 1.2, 1.2)
            return
        if w < self._target_w() * 0.8:
            return  # still expanding: skip content so nothing overlaps
        f = QFont("Segoe UI", 9)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        cy = r.center().y()
        left, right = r.left() + 16, r.right() - 14

        if self.state == "recording":
            pulse = 0.55 + 0.45 * math.sin(self.phase * 6)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 77, 109, int(70 * pulse)))
            p.drawEllipse(QPointF(left + 5, cy), 9, 9)
            p.setBrush(QColor(C["rec"]))
            p.drawEllipse(QPointF(left + 5, cy), 5, 5)
            # timer (fixed slot on the right)
            secs = int(time.monotonic() - self.t0)
            p.setPen(QColor(C["muted"]))
            tr = QRectF(right - 40, r.top(), 40, h)
            p.drawText(tr, Qt.AlignVCenter | Qt.AlignRight, f"{secs // 60}:{secs % 60:02d}")
            # waveform (own slot, never overlaps the timer)
            wl, wr = left + 22, right - 48
            n = len(self.levels)
            bw = (wr - wl) / n
            vals = list(self.levels)
            for i, v in enumerate(vals):
                bh = max(3.0, v * (h - 16))
                x = wl + i * bw
                c = QColor(C["rec"])
                c.setAlpha(110 + int(145 * (i / n)))
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x, cy - bh / 2, max(1.5, bw * 0.55), bh), 1.2, 1.2)

        elif self.state == "processing":
            # spinner
            p.setPen(QPen(QColor(124, 92, 255, 60), 2.4))
            p.setBrush(Qt.NoBrush)
            sr = QRectF(left - 2, cy - 8, 16, 16)
            p.drawEllipse(sr)
            g = QPen(QColor(C["accent2"]), 2.4)
            g.setCapStyle(Qt.RoundCap)
            p.setPen(g)
            p.drawArc(sr, int(-self.phase * 360 * 16 * 1.4) % (360 * 16), 100 * 16)
            secs = time.monotonic() - self.t0
            p.setPen(QColor(C["dim"]))
            tr = QRectF(right - 40, r.top(), 40, h)
            p.drawText(tr, Qt.AlignVCenter | Qt.AlignRight, f"{secs:.1f}s")
            txt = self.preview or getattr(self, "status", "") or "Transcribing…"
            p.setPen(QColor(C["text"] if self.preview else C["muted"]))
            fm = QFontMetrics(f)
            area = QRectF(left + 24, r.top(), right - 48 - (left + 24), h)
            # show the *end* of the streamed text
            el = fm.elidedText(txt, Qt.ElideLeft, int(area.width()))
            p.drawText(area, Qt.AlignVCenter | Qt.AlignLeft, el)

        else:
            ok = self.state == "done"
            col = QColor(C["good"] if ok else C["bad"])
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(left + 6, cy), 8, 8)
            p.setPen(QPen(QColor(C["bg"]), 2.0, Qt.SolidLine, Qt.RoundCap))
            if ok:
                p.drawPolyline([QPointF(left + 2.5, cy), QPointF(left + 5, cy + 3), QPointF(left + 10, cy - 3)])
            else:
                p.drawLine(QPointF(left + 6, cy - 4), QPointF(left + 6, cy + 1))
                p.drawPoint(QPointF(left + 6, cy + 4))
            fm = QFontMetrics(f)
            area = QRectF(left + 24, r.top(), right - (left + 24), h)
            p.setPen(QColor(C["text"]))
            main = fm.elidedText(self.msg, Qt.ElideRight, int(area.width() - (fm.horizontalAdvance(self.sub) + 12 if self.sub else 0)))
            p.drawText(area, Qt.AlignVCenter | Qt.AlignLeft, main)
            if self.sub:
                p.setPen(QColor(lat_color(None) if not ok else C["muted"]))
                p.drawText(area, Qt.AlignVCenter | Qt.AlignRight, self.sub)


# ---------------------------------------------------------------------------
# Small widgets
# ---------------------------------------------------------------------------
class RecordButton(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setFixedSize(132, 132)
        self.setCursor(Qt.PointingHandCursor)
        self.rec = False
        self.busy = False
        self.level = 0.0
        self.phase = 0.0
        self.t = QTimer(self, interval=16, timeout=self._tick)
        self.t.start()

    def _tick(self):
        self.phase += 0.016
        if self.rec or self.busy:
            self.update()

    def set_state(self, rec, busy):
        self.rec, self.busy = rec, busy
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        base = 44
        if self.rec:
            halo = base + 8 + self.level * 18
            g = QRadialGradient(c, halo + 10)
            g.setColorAt(0, QColor(255, 77, 109, 90))
            g.setColorAt(1, QColor(255, 77, 109, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, halo + 10, halo + 10)
        ring = QPen(QColor(C["border"]), 2)
        p.setPen(ring)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, base + 8, base + 8)
        if self.busy:
            pen = QPen(QColor(C["accent2"]), 3, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            rr = QRectF(c.x() - base - 8, c.y() - base - 8, 2 * base + 16, 2 * base + 16)
            p.drawArc(rr, int(-self.phase * 360 * 16) % (360 * 16), 90 * 16)
        g = QLinearGradient(c.x() - base, c.y() - base, c.x() + base, c.y() + base)
        if self.rec:
            g.setColorAt(0, QColor("#FF4D6D"))
            g.setColorAt(1, QColor("#FF8A5C"))
        else:
            g.setColorAt(0, QColor("#7C5CFF"))
            g.setColorAt(1, QColor("#22D3EE"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, base, base)
        p.setBrush(QColor(255, 255, 255))
        if self.rec:
            p.drawRoundedRect(QRectF(c.x() - 13, c.y() - 13, 26, 26), 6, 6)
        else:
            # microphone glyph
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 20, 16, 26), 8, 8)
            pen = QPen(QColor(255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(c.x() - 14, c.y() - 14, 28, 26), 200 * 16, 140 * 16)
            p.drawLine(QPointF(c.x(), c.y() + 12), QPointF(c.x(), c.y() + 19))
            p.drawLine(QPointF(c.x() - 7, c.y() + 19), QPointF(c.x() + 7, c.y() + 19))


class Gauge(QWidget):
    def __init__(self, label):
        super().__init__()
        self.label, self.used, self.limit, self.extra = label, 0, 0, ""
        self.setMinimumHeight(40)

    def set(self, used, limit, extra=""):
        self.used, self.limit, self.extra = used, limit, extra
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        f = QFont("Segoe UI", 9)
        p.setFont(f)
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(0, 0, w, 18), Qt.AlignLeft | Qt.AlignVCenter, self.label)
        frac = (self.used / self.limit) if self.limit else 0
        col = QColor(frac_color(frac))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        txt = f"{fmt_n(self.used)} / {fmt_n(self.limit) if self.limit else '?'}" + (f"  {self.extra}" if self.extra else "")
        p.drawText(QRectF(0, 0, w, 18), Qt.AlignRight | Qt.AlignVCenter, txt)
        bar = QRectF(0, 24, w, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["border"]))
        p.drawRoundedRect(bar, 4, 4)
        if frac > 0:
            fb = QRectF(0, 24, max(8, w * min(1, frac)), 8)
            p.setBrush(col)
            p.drawRoundedRect(fb, 4, 4)


class Sparkline(QWidget):
    def __init__(self):
        super().__init__()
        self.vals = []
        self.setMinimumHeight(46)

    def set(self, vals):
        self.vals = [v for v in vals if v is not None]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if not self.vals:
            p.setPen(QColor(C["dim"]))
            p.drawText(self.rect(), Qt.AlignCenter, "latency history appears here")
            return
        mx = max(max(self.vals), 4000)
        n = len(self.vals)
        bw = w / max(n, 20)
        for i, v in enumerate(self.vals):
            bh = max(2, (v / mx) * (h - 4))
            c = QColor(lat_color(v))
            c.setAlpha(200 if i == n - 1 else 120)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(i * bw + 1, h - bh, bw - 3, bh), 2, 2)
        # 2s target line
        y = h - (2000 / mx) * (h - 4)
        pen = QPen(QColor(C["dim"]), 1, Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(0, y), QPointF(w, y))


def card(title=None):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(8)
    if title:
        t = QLabel(title.upper())
        t.setObjectName("cardTitle")
        lay.addWidget(t)
    return f, lay


def label(text="", obj=None, wrap=False):
    l = QLabel(text)
    if obj:
        l.setObjectName(obj)
    l.setWordWrap(wrap)
    return l


def make_table(headers, stretch_last=True):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(stretch_last)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.setShowGrid(False)
    t.setAlternatingRowColors(False)
    return t


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.s = ctl.settings
        self.setWindowTitle("Kalam — كلام")
        self.setWindowIcon(make_icon())
        self.resize(1180, 780)
        self.setMinimumSize(980, 660)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 22, 0, 16)
        brand = QHBoxLayout()
        brand.setContentsMargins(20, 0, 16, 18)
        logo = QLabel()
        logo.setPixmap(make_logo(38))
        brand.addWidget(logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        n = label("Kalam", "h2")
        n.setStyleSheet("font-size: 14pt;")
        bt.addWidget(n)
        bt.addWidget(label("كلام · dictation", "dim"))
        brand.addLayout(bt)
        brand.addStretch()
        sv.addLayout(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for name in ["Home", "History", "Snippets", "Dictionary", "Usage & limits", "Settings"]:
            self.nav.addItem(QListWidgetItem(name))
        sv.addWidget(self.nav, 1)
        self.side_status = label("", "dim", wrap=True)
        self.side_status.setContentsMargins(20, 0, 16, 0)
        sv.addWidget(self.side_status)
        h.addWidget(side)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.stack.addWidget(self._home())
        self.stack.addWidget(self._history())
        self.stack.addWidget(self._snippets())
        self.stack.addWidget(self._dictionary())
        self.stack.addWidget(self._usage())
        self.stack.addWidget(self._settings())
        self.nav.currentRowChanged.connect(self._nav)
        self.nav.setCurrentRow(0)

        self.tick = QTimer(self, interval=2000, timeout=self.refresh_live)
        self.tick.start()
        self.refresh_all()

    def _page(self, title, subtitle=None):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(30, 26, 30, 24)
        v.setSpacing(16)
        v.addWidget(label(title, "h1"))
        if subtitle:
            v.addWidget(label(subtitle, "muted", wrap=True))
        return w, v

    def _nav(self, i):
        self.stack.setCurrentIndex(i)
        if i == 1:
            self.load_history()
        elif i == 4:
            self.load_usage()

    # ------------------------------------------------------------------ Home
    def _home(self):
        w, v = self._page("Dictate anywhere")
        top = QHBoxLayout()
        top.setSpacing(16)

        hero, hl = card()
        row = QHBoxLayout()
        row.setSpacing(22)
        self.rec_btn = RecordButton()
        self.rec_btn.clicked.connect(self.ctl.toggle)
        row.addWidget(self.rec_btn, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(6)
        self.status_title = label("Ready", "h1")
        self.status_title.setStyleSheet("font-size: 16pt;")
        info.addWidget(self.status_title)
        self.status_hint = label("", "muted", wrap=True)
        info.addWidget(self.status_hint)
        info.addSpacing(8)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.mode_group = QButtonGroup(self)
        for i, (k, m) in enumerate(core.MODES.items()):
            b = QPushButton(m["label"])
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            radius = "border-top-left-radius:9px;border-bottom-left-radius:9px;" if i == 0 else \
                "border-top-right-radius:9px;border-bottom-right-radius:9px;" if i == len(core.MODES) - 1 else ""
            b.setStyleSheet(radius)
            b.setProperty("mode", k)
            self.mode_group.addButton(b)
            seg.addWidget(b)
        self.mode_group.buttonClicked.connect(lambda b: self.ctl.set_mode(b.property("mode")))
        seg.addStretch()
        info.addLayout(seg)
        self.mode_desc = label("", "muted", wrap=True)
        info.addWidget(self.mode_desc)
        self.mode_example = label("", "dim", wrap=True)
        self.mode_example.setTextFormat(Qt.RichText)
        self.mode_example.setStyleSheet(f"background:{C['bg']}; border-radius:8px; padding:8px 10px; color:{C['muted']}; font-size:9pt;")
        info.addWidget(self.mode_example)
        info.addStretch()
        row.addLayout(info, 1)
        hl.addLayout(row)
        top.addWidget(hero, 3)

        last, ll = card("Last dictation")
        self.last_text = QTextEdit()
        self.last_text.setReadOnly(True)
        self.last_text.setAcceptRichText(False)
        self.last_text.setPlaceholderText("Your text shows up here. Press the hotkey in any app — it is typed where your cursor is.")
        self.last_text.setStyleSheet(f"font-size: 11pt; background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 9px; padding: 6px;")
        ll.addWidget(self.last_text, 1)
        lr = QHBoxLayout()
        self.last_meta = label("", "dim", wrap=True)
        lr.addWidget(self.last_meta, 1)
        cp = QPushButton("Copy")
        cp.clicked.connect(lambda: self.ctl.copy_text(getattr(self, "_last_plain", "")))
        lr.addWidget(cp)
        ll.addLayout(lr)
        top.addWidget(last, 2)
        v.addLayout(top, 5)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        # latency
        lat, la = card("Latency · stop → text in your app")
        r1 = QHBoxLayout()
        self.lat_big = label("—", "big")
        r1.addWidget(self.lat_big)
        r1.addStretch()
        self.ping_btn = QPushButton("Ping")
        self.ping_btn.setToolTip("Measure network round-trip to Gemini (free, uses no quota)")
        self.ping_btn.clicked.connect(self.ctl.ping)
        r1.addWidget(self.ping_btn, 0, Qt.AlignTop)
        la.addLayout(r1)
        self.lat_break = label("", "muted", wrap=True)
        la.addWidget(self.lat_break)
        self.spark = Sparkline()
        la.addWidget(self.spark)
        self.lat_stats = label("", "dim", wrap=True)
        la.addWidget(self.lat_stats)
        bottom.addWidget(lat, 1)
        # rate limits
        rl, rla = card("Free-tier rate limits")
        self.rl_model = label("", "muted")
        rla.addWidget(self.rl_model)
        self.g_rpm = Gauge("Requests / minute")
        self.g_rpd = Gauge("Requests / day")
        self.g_tpm = Gauge("Tokens / minute")
        for g in (self.g_rpm, self.g_rpd, self.g_tpm):
            rla.addWidget(g)
        self.rl_foot = label("", "dim", wrap=True)
        rla.addWidget(self.rl_foot)
        bottom.addWidget(rl, 1)
        # today
        td, tda = card("Today")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(2)
        self.today = {}
        for i, (k, t) in enumerate([("n", "dictations"), ("words", "words"), ("audio", "audio"), ("saved", "time saved")]):
            val = label("0", "big")
            val.setStyleSheet("font-size: 17pt;")
            grid.addWidget(val, (i // 2) * 2, i % 2)
            grid.addWidget(label(t, "dim"), (i // 2) * 2 + 1, i % 2)
            self.today[k] = val
        tda.addLayout(grid)
        tda.addStretch()
        self.today_foot = label("", "dim", wrap=True)
        tda.addWidget(self.today_foot)
        bottom.addWidget(td, 1)
        v.addLayout(bottom, 4)
        return w

    # --------------------------------------------------------------- History
    def _history(self):
        w, v = self._page("History", "Everything you dictated. Double-click a row to copy it. Stored only on this PC.")
        r = QHBoxLayout()
        self.h_search = QLineEdit()
        self.h_search.setPlaceholderText("Search…")
        self.h_search.textChanged.connect(self.load_history)
        r.addWidget(self.h_search, 1)
        b_copy = QPushButton("Copy")
        b_copy.clicked.connect(self._h_copy)
        b_del = QPushButton("Delete")
        b_del.clicked.connect(self._h_delete)
        b_clear = QPushButton("Clear all")
        b_clear.clicked.connect(self._h_clear)
        for b in (b_copy, b_del, b_clear):
            r.addWidget(b)
        v.addLayout(r)
        self.h_table = make_table(["Time", "App", "Mode", "Latency", "Words", "Text"])
        self.h_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.h_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.h_table.setWordWrap(True)
        for i, wd in enumerate([130, 110, 70, 70, 60]):
            self.h_table.setColumnWidth(i, wd)
        self.h_table.cellDoubleClicked.connect(lambda r, c: self._h_copy())
        v.addWidget(self.h_table, 1)
        return w

    def load_history(self):
        rows = self.ctl.db.history(self.h_search.text().strip())
        t = self.h_table
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [time.strftime("%b %d  %H:%M", time.localtime(r["ts"])), r["app"] or "", r["mode"] or "",
                    fmt_ms(r["total_ms"]), str(r["words"] or 0), r["text"]]
            for j, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if j == 5:
                    it.setToolTip(val)
                if j == 0:
                    it.setData(Qt.UserRole, r["id"])
                t.setItem(i, j, it)
        t.resizeRowsToContents()

    def _h_selected(self):
        return sorted({i.row() for i in self.h_table.selectedItems()})

    def _h_copy(self):
        rows = self._h_selected()
        if rows:
            self.ctl.copy_text("\n\n".join(self.h_table.item(r, 5).text() for r in rows))

    def _h_delete(self):
        for r in self._h_selected():
            self.ctl.db.delete(self.h_table.item(r, 0).data(Qt.UserRole))
        self.load_history()

    def _h_clear(self):
        if QMessageBox.question(self, "Clear history", "Delete all saved transcripts? Usage stats are kept.") == QMessageBox.Yes:
            self.ctl.db.clear_history()
            self.load_history()

    # -------------------------------------------------------------- Snippets
    def _snippets(self):
        w, v = self._page("Snippets", "Say a trigger phrase and Kalam types the saved text instead — use a frequently used phrase. "
                                      "Works alone or inside a sentence.")
        self.sn_table = make_table(["Trigger (what you say)", "Expands to"])
        self.sn_table.setColumnWidth(0, 260)
        v.addWidget(self.sn_table, 1)
        r = QHBoxLayout()
        add = QPushButton("+ Add snippet")
        add.clicked.connect(lambda: self._add_row(self.sn_table))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: self._rm_rows(self.sn_table))
        sv = QPushButton("Save")
        sv.setObjectName("primary")
        sv.clicked.connect(self._save_snippets)
        r.addWidget(add)
        r.addWidget(rm)
        r.addStretch()
        r.addWidget(sv)
        v.addLayout(r)
        return w

    def _add_row(self, t, vals=("", "")):
        i = t.rowCount()
        t.insertRow(i)
        for j, val in enumerate(vals):
            t.setItem(i, j, QTableWidgetItem(val))
        t.setCurrentCell(i, 0)
        return i

    def _rm_rows(self, t):
        for r in sorted({i.row() for i in t.selectedItems()} | ({t.currentRow()} if t.currentRow() >= 0 else set()), reverse=True):
            t.removeRow(r)

    def _rows(self, t, keys):
        out = []
        for i in range(t.rowCount()):
            vals = [(t.item(i, j).text() if t.item(i, j) else "").strip() for j in range(len(keys))]
            if vals[0]:
                out.append(dict(zip(keys, vals)))
        return out

    def _save_snippets(self):
        self.s["snippets"] = self._rows(self.sn_table, ["trigger", "text"])
        self.s.save()
        self.flash("Snippets saved")

    # ------------------------------------------------------------ Dictionary
    def _dictionary(self):
        w, v = self._page("Dictionary", "Teach Kalam names and terms it should spell exactly, and fix words it keeps getting wrong.")
        row = QHBoxLayout()
        row.setSpacing(16)
        c1, l1 = card("Vocabulary — one per line")
        self.vocab = QPlainTextEdit()
        self.vocab.setPlaceholderText("ZATCA\nVAT\nExample Name")
        l1.addWidget(self.vocab, 1)
        l1.addWidget(label("Sent to the model as spelling hints (costs a few tokens per request).", "dim", wrap=True))
        row.addWidget(c1, 1)
        c2, l2 = card("Replacements — applied after transcription")
        self.rep_table = make_table(["When it writes", "Replace with"])
        self.rep_table.setColumnWidth(0, 200)
        l2.addWidget(self.rep_table, 1)
        rr = QHBoxLayout()
        a = QPushButton("+ Add")
        a.clicked.connect(lambda: self._add_row(self.rep_table))
        d = QPushButton("Remove")
        d.clicked.connect(lambda: self._rm_rows(self.rep_table))
        rr.addWidget(a)
        rr.addWidget(d)
        rr.addStretch()
        l2.addLayout(rr)
        row.addWidget(c2, 1)
        v.addLayout(row, 1)
        b = QHBoxLayout()
        b.addStretch()
        sv = QPushButton("Save")
        sv.setObjectName("primary")
        sv.clicked.connect(self._save_dict)
        b.addWidget(sv)
        v.addLayout(b)
        return w

    def _save_dict(self):
        self.s["vocabulary"] = [x.strip() for x in self.vocab.toPlainText().splitlines() if x.strip()]
        self.s["replacements"] = self._rows(self.rep_table, ["from", "to"])
        self.s.save()
        self.flash("Dictionary saved")

    # ----------------------------------------------------------------- Usage
    def _usage(self):
        w, v = self._page("Usage & limits")
        r = QHBoxLayout()
        self.u_period = QComboBox()
        self.u_period.addItems(["Today (Pacific quota day)", "Last 7 days", "Last 30 days"])
        self.u_period.currentIndexChanged.connect(self.load_usage)
        r.addWidget(self.u_period)
        r.addStretch()
        v.addLayout(r)
        self.u_table = make_table(["Model", "Requests", "OK", "429s", "Audio", "Audio tok", "Text tok", "Out tok", "If paid (est.)"], False)
        self.u_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.u_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.u_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.u_table.setMaximumHeight(190)
        v.addWidget(self.u_table)
        self.u_proj = label("", "muted", wrap=True)
        v.addWidget(self.u_proj)

        row = QHBoxLayout()
        row.setSpacing(16)
        c1, l1 = card("Latency by model (last 50)")
        self.lat_table = make_table(["Model", "p50", "p90", "First word", "Avg audio"], False)
        self.lat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.lat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        l1.addWidget(self.lat_table)
        row.addWidget(c1, 1)
        c2, l2 = card("Free-tier limits (editable)")
        self.lim_table = make_table(["Model", "RPM", "RPD", "TPM"], False)
        self.lim_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lim_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        l2.addWidget(self.lim_table)
        l2.addWidget(label("Starting values are estimates. When Google returns a 429, Kalam reads the real quota from the "
                           "error and updates the value automatically. Check yours at aistudio.google.com/rate-limit.", "dim", wrap=True))
        b = QHBoxLayout()
        b.addStretch()
        sv = QPushButton("Save limits")
        sv.clicked.connect(self._save_limits)
        b.addWidget(sv)
        l2.addLayout(b)
        row.addWidget(c2, 1)
        v.addLayout(row, 1)
        return w

    def load_usage(self):
        idx = self.u_period.currentIndex()
        since = core.quota_day_window()[0] if idx == 0 else time.time() - (7 if idx == 1 else 30) * 86400
        days = 1 if idx == 0 else (7 if idx == 1 else 30)
        rows = self.ctl.db.summary(since)
        t = self.u_table
        t.setRowCount(len(rows) + (1 if rows else 0))
        tot = {"n": 0, "ok": 0, "limited": 0, "audio_sec": 0, "audio_tokens": 0, "text_tokens": 0, "out_tokens": 0, "cost": 0.0}
        for i, r in enumerate(rows):
            pr = self.s.price(r["model"])
            cost = (r["audio_tokens"] * pr["audio"] + r["text_tokens"] * pr["text"] + r["out_tokens"] * pr["out"]) / 1e6
            vals = [r["model"], r["n"], r["ok"], r["limited"], f"{r['audio_sec'] / 60:.1f} min", fmt_n(r["audio_tokens"]),
                    fmt_n(r["text_tokens"]), fmt_n(r["out_tokens"]), f"${cost:.4f}"]
            for j, val in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(str(val)))
            for k in tot:
                tot[k] += cost if k == "cost" else (r[k] or 0)
        if rows:
            vals = ["Total", tot["n"], tot["ok"], tot["limited"], f"{tot['audio_sec'] / 60:.1f} min", fmt_n(tot["audio_tokens"]),
                    fmt_n(tot["text_tokens"]), fmt_n(tot["out_tokens"]), f"${tot['cost']:.4f}"]
            for j, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                f = it.font()
                f.setBold(True)
                it.setFont(f)
                t.setItem(len(rows), j, it)
        per_day = tot["cost"] / days if days else 0
        self.u_proj.setText(
            f"You pay $0 on the free tier. If you were on the paid tier, this pace ≈ ${per_day * 30:.2f}/month "
            f"(Wispr Flow Pro is ~$15/month). {tot['n']} requests in this period."
            if rows else "No requests in this period yet.")

        models = list(core.MODELS)
        self.lat_table.setRowCount(len(models))
        for i, m in enumerate(models):
            L = self.ctl.db.latencies(50, m)
            tv = [x["total_ms"] for x in L]
            vals = [m, fmt_ms(pct(tv, .5)), fmt_ms(pct(tv, .9)), fmt_ms(pct([x["ttft_ms"] for x in L], .5)),
                    f"{sum(x['audio_sec'] or 0 for x in L) / len(L):.1f} s" if L else "—"]
            for j, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if j in (1, 2) and tv:
                    it.setForeground(QColor(lat_color(pct(tv, .5 if j == 1 else .9))))
                self.lat_table.setItem(i, j, it)

        self.lim_table.setRowCount(len(models))
        for i, m in enumerate(models):
            lim = self.s.limits(m)
            learned = self.s["learned"].get(m, {})
            it = QTableWidgetItem(m)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.lim_table.setItem(i, 0, it)
            for j, k in enumerate(("rpm", "rpd", "tpm"), 1):
                cell = QTableWidgetItem(str(lim[k]))
                if k in learned:
                    cell.setToolTip("Learned from Google's 429 response")
                    cell.setForeground(QColor(C["accent2"]))
                self.lim_table.setItem(i, j, cell)

    def _save_limits(self):
        out = {}
        for i in range(self.lim_table.rowCount()):
            m = self.lim_table.item(i, 0).text()
            d = {}
            for j, k in enumerate(("rpm", "rpd", "tpm"), 1):
                try:
                    val = int(self.lim_table.item(i, j).text().replace(",", ""))
                except (ValueError, AttributeError):
                    continue
                base = {kk: core.MODELS[m][kk] for kk in ("rpm", "rpd", "tpm")}
                base.update(self.s["learned"].get(m, {}))
                if val != base.get(k):
                    d[k] = val
            if d:
                out[m] = d
        self.s["limits"] = out
        self.s.save()
        self.refresh_live()
        self.flash("Limits saved")

    # -------------------------------------------------------------- Settings
    def _settings(self):
        w, v = self._page("Settings")
        row = QHBoxLayout()
        row.setSpacing(16)
        c1, l1 = card("Gemini API")
        l1.addWidget(label("Google AI Studio API key", "muted"))
        kr = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your key from aistudio.google.com/apikey")
        kr.addWidget(self.key_edit, 1)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        kr.addWidget(show)
        l1.addLayout(kr)
        tr = QHBoxLayout()
        test = QPushButton("Test connection")
        test.clicked.connect(lambda: self.ctl.test_connection(self.key_edit.text().strip(), self.model_combo.currentData()))
        tr.addWidget(test)
        self.test_result = label("", "muted", wrap=True)
        tr.addWidget(self.test_result, 1)
        l1.addLayout(tr)
        l1.addSpacing(8)
        l1.addWidget(label("Model", "muted"))
        self.model_combo = QComboBox()
        self.fb_combo = QComboBox()
        for k, m in core.MODELS.items():
            self.model_combo.addItem(m["label"], k)
            self.fb_combo.addItem(m["label"], k)
        l1.addWidget(self.model_combo)
        self.model_note = label("", "dim", wrap=True)
        self.model_combo.currentIndexChanged.connect(
            lambda _: self.model_note.setText(core.MODELS.get(self.model_combo.currentData(), {}).get("note", "")))
        l1.addWidget(self.model_note)
        self.fb_check = QCheckBox("If the model is rate-limited or busy, retry once with:")
        l1.addWidget(self.fb_check)
        l1.addWidget(self.fb_combo)
        l1.addWidget(label("Each model has its own free quota, so a fallback roughly doubles your daily headroom.", "dim", wrap=True))
        l1.addStretch()
        row.addWidget(c1, 1)

        c2, l2 = card("Dictation")
        g = QGridLayout()
        g.setVerticalSpacing(10)
        g.addWidget(label("Hotkey", "muted"), 0, 0)
        self.hk_combo = QComboBox()
        for k in core.HOTKEYS:
            self.hk_combo.addItem(k.upper() if len(k) <= 3 else k.title(), k)
        g.addWidget(self.hk_combo, 0, 1)
        g.addWidget(label("Arabic dialect", "muted"), 2, 0)
        self.dialect_combo = QComboBox()
        for k, (name, _) in core.DIALECTS.items():
            self.dialect_combo.addItem(name, k)
        g.addWidget(self.dialect_combo, 2, 1)
        g.addWidget(label("Microphone", "muted"), 1, 0)
        self.mic_combo = QComboBox()
        g.addWidget(self.mic_combo, 1, 1)
        g.setColumnStretch(1, 1)
        l2.addLayout(g)
        self.cb_paste = QCheckBox("Type the text into the app I'm using (auto-paste)")
        self.cb_restore = QCheckBox("Restore my clipboard after pasting")
        self.cb_ctx = QCheckBox("Adapt to the app I'm in (Outlook → email tone). Sends the app name only.")
        self.cb_trim = QCheckBox("Skip recordings with no speech (saves quota)")
        self.cb_overlay = QCheckBox("Keep a tiny pill on screen when idle")
        self.cb_sounds = QCheckBox("Play start/stop sounds")
        for cb in (self.cb_paste, self.cb_restore, self.cb_ctx, self.cb_trim, self.cb_overlay, self.cb_sounds):
            cb.setStyleSheet("padding: 2px 0;")
            l2.addWidget(cb)
        l2.addStretch()
        l2.addWidget(label(f"Data folder: {core.DATA_DIR}", "dim", wrap=True))
        row.addWidget(c2, 1)
        v.addLayout(row, 1)
        b = QHBoxLayout()
        b.addStretch()
        sv = QPushButton("Save settings")
        sv.setObjectName("primary")
        sv.clicked.connect(self._save_settings)
        b.addWidget(sv)
        v.addLayout(b)
        return w

    def _load_settings_page(self):
        s = self.s
        self.key_edit.setText(s["api_key"])
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(s["model"])))
        self.fb_combo.setCurrentIndex(max(0, self.fb_combo.findData(s["fallback_model"])))
        self.fb_check.setChecked(bool(s["use_fallback"]))
        self.hk_combo.setCurrentIndex(max(0, self.hk_combo.findData(s["hotkey"])))
        self.mic_combo.clear()
        self.mic_combo.addItem("System default", None)
        for i, name in core.list_mics():
            self.mic_combo.addItem(name, i)
        self.mic_combo.setCurrentIndex(max(0, self.mic_combo.findData(s["mic"])))
        self.dialect_combo.setCurrentIndex(max(0, self.dialect_combo.findData(s["dialect"])))
        self.cb_paste.setChecked(bool(s["auto_paste"]))
        self.cb_restore.setChecked(bool(s["restore_clipboard"]))
        self.cb_ctx.setChecked(bool(s["app_context"]))
        self.cb_trim.setChecked(bool(s["trim_silence"]))
        self.cb_overlay.setChecked(bool(s["overlay_idle"]))
        self.cb_sounds.setChecked(bool(s["sounds"]))
        self.sn_table.setRowCount(0)
        for sn in s["snippets"]:
            self._add_row(self.sn_table, (sn.get("trigger", ""), sn.get("text", "")))
        self.vocab.setPlainText("\n".join(s["vocabulary"]))
        self.rep_table.setRowCount(0)
        for r in s["replacements"]:
            self._add_row(self.rep_table, (r.get("from", ""), r.get("to", "")))

    def _save_settings(self):
        s = self.s
        s["api_key"] = self.key_edit.text().strip()
        s["model"] = self.model_combo.currentData()
        s["fallback_model"] = self.fb_combo.currentData()
        s["use_fallback"] = self.fb_check.isChecked()
        s["hotkey"] = self.hk_combo.currentData()
        s["mic"] = self.mic_combo.currentData()
        s["dialect"] = self.dialect_combo.currentData()
        s["auto_paste"] = self.cb_paste.isChecked()
        s["restore_clipboard"] = self.cb_restore.isChecked()
        s["app_context"] = self.cb_ctx.isChecked()
        s["trim_silence"] = self.cb_trim.isChecked()
        s["overlay_idle"] = self.cb_overlay.isChecked()
        s["sounds"] = self.cb_sounds.isChecked()
        s.save()
        self.ctl.apply_settings()
        self.flash("Settings saved")

    # --------------------------------------------------------------- refresh
    def flash(self, msg):
        self.side_status.setText(msg)
        QTimer.singleShot(3000, lambda: self.side_status.setText(self._side_default()))

    def _side_default(self):
        return f"{self.s['hotkey'].upper()} to dictate\n{core.MODELS.get(self.s['model'], {}).get('label', self.s['model'])}"

    def refresh_all(self):
        self._load_settings_page()
        self.on_mode()
        self.on_state()
        self.refresh_live()
        self.side_status.setText(self._side_default())

    def on_mode(self):
        m = self.s["mode"]
        for b in self.mode_group.buttons():
            b.setChecked(b.property("mode") == m)
        self.mode_desc.setText(core.MODES[m]["desc"])
        self.mode_example.setText(bidi_html(core.MODES[m]["example"]))

    def on_state(self):
        st = self.ctl.state
        hk = self.s["hotkey"].upper() if len(self.s["hotkey"]) <= 3 else self.s["hotkey"].title()
        self.rec_btn.set_state(st == "recording", st == "processing")
        if st == "recording":
            self.status_title.setText("Listening…")
            self.status_hint.setText(f"Press {hk} again (or release if holding) to finish · Esc to cancel")
        elif st == "processing":
            self.status_title.setText("Transcribing…")
            self.status_hint.setText("Streaming from Gemini")
        else:
            self.status_title.setText("Ready")
            self.status_hint.setText(f"Press {hk} in any app: tap to start/stop, or hold while you talk. Esc cancels.\n"
                                     f"Arabic, English and mixed speech are all fine.")

    def set_level(self, v):
        self.rec_btn.level = v

    def on_result(self, text, meta):
        self.last_text.setHtml(bidi_html(text))
        self._last_plain = text
        self.last_meta.setText(meta)
        self.refresh_live()

    def refresh_live(self):
        db, s = self.ctl.db, self.s
        model = s["model"]
        # latency
        L = db.latencies(30)
        if L:
            last = L[-1]
            self.lat_big.setText(fmt_ms(last["total_ms"]))
            self.lat_big.setStyleSheet(f"color: {lat_color(last['total_ms'])};")
            self.lat_break.setText(f"first word {fmt_ms(last['ttft_ms'])} · full answer {fmt_ms(last['api_ms'])} · "
                                   f"encode {fmt_ms(last['encode_ms'])} · paste {fmt_ms(last['paste_ms'])} · "
                                   f"{last['audio_sec']:.1f}s audio · {last['model']}")
        else:
            self.lat_break.setText("Dictate something to see timings.")
        tv = [x["total_ms"] for x in L]
        self.spark.set(tv[-24:])
        rtt = self.ctl.gemini.last_rtt_ms
        self.lat_stats.setText(f"p50 {fmt_ms(pct(tv, .5))} · p90 {fmt_ms(pct(tv, .9))} · network RTT {fmt_ms(rtt)} · "
                               f"green < 2s, amber < 4s")
        # rate limits
        lim = s.limits(model)
        u = db.rate_usage(model)
        self.rl_model.setText(core.MODELS.get(model, {}).get("label", model) + ("  · learned from Google" if s["learned"].get(model) else "  · estimated"))
        self.g_rpm.set(u["rpm"], lim["rpm"])
        self.g_rpd.set(u["rpd"], lim["rpd"])
        self.g_tpm.set(u["tpm"], lim["tpm"])
        left = max(0, u["reset_ts"] - time.time())
        cd = self.ctl.cooldown_left(model)
        daily_pct = 25 / lim["rpd"] * 100 if lim["rpd"] else 0
        foot = f"Daily quota resets in {int(left // 3600)}h {int(left % 3600 // 60)}m (midnight Pacific). "
        foot += f"25 dictations/day ≈ {daily_pct:.0f}% of the daily quota."
        if cd:
            foot = f"⏳ Rate-limited — cooling down {int(cd)}s. " + foot
        fb = s["fallback_model"] if s["use_fallback"] else None
        if fb and fb != model:
            fu = db.rate_usage(fb)
            foot += f"\nFallback {fb}: {fu['rpd']}/{s.limits(fb)['rpd']} today."
        self.rl_foot.setText(foot)
        # today
        rows = db.summary(core.local_day_start())
        n = sum(r["ok"] or 0 for r in rows)
        words = sum(r["words"] or 0 for r in rows)
        audio = sum(r["audio_sec"] or 0 for r in rows)
        saved = max(0.0, words / 40 * 60 - audio)  # vs typing at 40 wpm
        self.today["n"].setText(str(n))
        self.today["words"].setText(fmt_n(words))
        self.today["audio"].setText(f"{audio / 60:.1f}m")
        self.today["saved"].setText(f"{saved / 60:.0f}m")
        limited = sum(r["limited"] or 0 for r in rows)
        self.today_foot.setText(("Time saved assumes 40 wpm typing." + (f"  {limited} rate-limited request(s) today." if limited else "")))

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.ctl.notify_tray_once()
