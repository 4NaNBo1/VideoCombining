"""主窗口：素材三卡片 + 合成/画面双栏 + 状态日志。"""
from __future__ import annotations

import os
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, QPoint, Signal, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QGuiApplication,
    QMoveEvent,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QDialog,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.combo import (
    DATE_FORMAT_PRESETS,
    ComboLimitError,
    build_output_name,
    compose_date_format,
    max_combinations,
    plan_combos,
)
from app.ffmpeg_job import (
    COMPRESSION_PRESETS,
    DEFAULT_COMPRESSION_INDEX,
    BuildCancelled,
    EncodeSettings,
    build_output,
)
from app.ffmpeg_util import verify_ffmpeg

# ponytail: 纯 QSS 美化，无第三方依赖；卡片白底 + 灰底分区。
# 下拉用 QComboBox 自带箭头。不要写 ::down-arrow / ::drop-down，这两条会把自带三角换掉。
_STYLESHEET_TEMPLATE = """
QWidget#central { background: #edf0f4; }
QWidget#header QLabel#title { font-size: 17px; font-weight: 700; color: #1f2329; }
QWidget#header QLabel#sub { font-size: 11px; color: #8a94a3; }
QGroupBox.card {
    background: #ffffff; border: 1px solid #e2e5ea; border-radius: 8px;
    margin-top: 14px; padding-top: 2px; font-size: 12px; font-weight: 600; color: #1f2329;
}
QGroupBox.card::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QGroupBox.card QLabel { font-weight: 400; color: #3a3f47; }
QGroupBox.card QLabel.dim { color: #8a94a3; font-size: 11px; }
QGroupBox.card QLabel#preview {
    background: #f4f6f9; border: 1px solid #e7ebf0; border-radius: 6px;
    padding: 4px 8px; color: #4a5261; font-size: 11px; font-weight: 400;
}
QGroupBox.card QLabel.count {
    background: #eef4ff; color: #1667ff; border-radius: 9px;
    padding: 1px 8px; font-size: 11px; font-weight: 600;
}
QListWidget { border: 1px solid #e5e8ed; border-radius: 6px; background: #fbfcfd;
    font-size: 11px; font-weight: 400; outline: 0; }
QListWidget[dragHighlight="true"] {
    border: 1px dashed #1667ff; background: #eef4ff;
}
QListWidget::item { padding: 2px 4px; }
QLineEdit, QSpinBox {
    border: 1px solid #dfe3e9; border-radius: 6px; background: #fff;
    min-height: 24px; max-height: 26px; font-size: 12px; font-weight: 400; padding: 0 6px;
}
QLineEdit:focus, QSpinBox:focus { border-color: #1667ff; }
QLineEdit:disabled, QSpinBox:disabled { background: #f2f4f7; color: #aab2c0; }
QComboBox {
    border: 1px solid #dfe3e9; border-radius: 6px; background: #fff;
    min-height: 26px; font-size: 12px; font-weight: 400;
    padding: 2px 8px 2px 10px; color: #3a3f47;
}
QComboBox:hover { border-color: #c8ced8; }
QComboBox:focus { border-color: #1667ff; }
QComboBox:disabled { background: #f2f4f7; color: #aab2c0; }
QComboBox QAbstractItemView {
    background: #ffffff; border: 1px solid #e2e5ea; border-radius: 8px;
    padding: 4px; outline: 0; font-size: 12px; color: #3a3f47;
    selection-background-color: #eef4ff; selection-color: #1667ff;
}
QComboBox QAbstractItemView::item {
    min-height: 28px; padding: 4px 10px; border-radius: 4px;
}
QComboBox QAbstractItemView::item:hover { background: #f4f6f9; color: #1f2329; }
QComboBox QAbstractItemView::item:selected { background: #eef4ff; color: #1667ff; }
QPushButton {
    border: 1px solid #dfe3e9; border-radius: 6px; background: #fff;
    min-height: 26px; padding: 0 12px; font-size: 12px; color: #333;
}
QPushButton:hover { border-color: #1667ff; color: #1667ff; }
QPushButton#primary {
    background: #1667ff; border: none; color: #fff; font-weight: 600;
    min-height: 32px; min-width: 116px; font-size: 13px;
}
QPushButton#primary:hover { background: #0f55d9; color: #fff; }
QPushButton#primary:disabled { background: #a9c4fb; color: #fff; }
QPushButton.mini { min-height: 22px; max-height: 22px; padding: 0 8px; font-size: 11px; }
QTextEdit#log {
    border: 1px solid #e5e8ed; border-radius: 6px; background: #1e2430;
    color: #c9d4e3; font-family: Consolas, Menlo, monospace; font-size: 11px;
}
QProgressBar { border: none; background: #e3e8ef; border-radius: 4px;
    min-height: 8px; max-height: 8px; text-align: center; font-size: 10px; }
QProgressBar::chunk { background: #1667ff; border-radius: 4px; }
QLabel#status { font-size: 11px; color: #5b6472; font-weight: 400; }
QFrame#line { color: #eef0f3; }
"""


def build_stylesheet() -> str:
    return _STYLESHEET_TEMPLATE


class _ClearFocusOnBlankFilter(QObject):
    """点击非输入控件区域时取消 QLineEdit / QSpinBox 焦点。"""

    _INPUT_TYPES = (QLineEdit, QTextEdit, QSpinBox, QComboBox, QListWidget)

    @classmethod
    def _is_input(cls, w: QWidget | None) -> bool:
        while w is not None:
            if isinstance(w, cls._INPUT_TYPES):
                return True
            w = w.parentWidget()
        return False

    def eventFilter(self, obj: QObject, event) -> bool:
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.MouseButtonPress:
            target = QApplication.widgetAt(event.globalPosition().toPoint())
            if self._is_input(target):
                return False
            fw = QApplication.focusWidget()
            if isinstance(fw, (QLineEdit, QSpinBox)):
                fw.clearFocus()
        return False


def _fill_date_part_combo(combo: QComboBox, options: list[tuple[str, str]]) -> None:
    combo.clear()
    for label, token in options:
        combo.addItem(label, token)


def _set_date_part_combo(combo: QComboBox, token: str) -> None:
    idx = combo.findData(token)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


def _prepare_combo_popup(combo: QComboBox) -> None:
    view = combo.view()
    view.setFrameShape(QFrame.Shape.NoFrame)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v"})


def _is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in _VIDEO_SUFFIXES


def _paths_from_mime_urls(mime) -> list[str]:
    if not mime.hasUrls():
        return []
    out: list[str] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        p = url.toLocalFile()
        if os.path.isfile(p) and _is_video_file(p):
            out.append(p)
    return out


class _VideoDropListWidget(QListWidget):
    """支持从系统拖入视频文件。"""

    def __init__(self, on_drop: Callable[[list[str]], None], parent: QWidget | None = None):
        super().__init__(parent)
        self._on_drop = on_drop
        self.setAcceptDrops(True)
        self.setDragEnabled(False)

    def _set_drag_highlight(self, on: bool) -> None:
        self.setProperty("dragHighlight", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _paths_from_mime_urls(event.mimeData()):
            event.acceptProposedAction()
            self._set_drag_highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if _paths_from_mime_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_highlight(False)
        paths = _paths_from_mime_urls(event.mimeData())
        if paths:
            self._on_drop(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


def _mini_spin(value: int = 1, minimum: int = 0, maximum: int = 99, width: int = 62) -> QSpinBox:
    sp = QSpinBox()
    sp.setRange(minimum, maximum)
    sp.setValue(value)
    sp.setFixedWidth(width)
    sp.setAlignment(Qt.AlignCenter)
    return sp


class VideoListPanel(QGroupBox):
    """单个素材卡片：标题 + 计数 + 列表 + 小按钮。"""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self.setProperty("class", "card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.count_lbl = QLabel("0 个")
        self.count_lbl.setProperty("class", "count")
        head.addWidget(self.count_lbl)
        head.addStretch(1)
        add_btn = QPushButton("添加")
        add_btn.setProperty("class", "mini")
        add_btn.clicked.connect(self._add)
        clear_btn = QPushButton("清空")
        clear_btn.setProperty("class", "mini")
        clear_btn.clicked.connect(self.list_clear)
        head.addWidget(add_btn)
        head.addWidget(clear_btn)
        lay.addLayout(head)

        self.list = _VideoDropListWidget(self._add_paths)
        self.list.setMinimumHeight(108)
        self.list.setMaximumHeight(150)
        self.list.setAlternatingRowColors(True)
        lay.addWidget(self.list)

    def _add_paths(self, paths: list[str]) -> None:
        existing = {self.list.item(i).text() for i in range(self.list.count())}
        for p in paths:
            if p not in existing:
                self.list.addItem(p)
                existing.add(p)

    def _add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择视频",
            "",
            "视频 (*.mp4 *.mov *.mkv *.avi *.webm *.flv *.m4v);;全部 (*.*)",
        )
        self._add_paths(paths)

    def list_clear(self) -> None:
        self.list.clear()

    def paths(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def refresh_count(self) -> None:
        self.count_lbl.setText(f"{self.list.count()} 个")


class GenerateWorker(QThread):
    log_line = Signal(str)
    progress = Signal(int, str)
    finished_ok = Signal(int)
    finished_err = Signal(str)
    finished_cancelled = Signal(int)

    def __init__(
        self,
        heads: list[str],
        mids: list[str],
        tails: list[str],
        k_heads: int,
        k_mids: int,
        k_tails: int,
        count: int,
        out_dir: str,
        settings: EncodeSettings,
        prefix: str,
        suffix: str,
        include_date: bool,
        date_format: str,
        ext: str,
    ):
        super().__init__()
        self.heads = heads
        self.mids = mids
        self.tails = tails
        self.k_heads = k_heads
        self.k_mids = k_mids
        self.k_tails = k_tails
        self.count = count
        self.out_dir = out_dir
        self.settings = settings
        self.prefix = prefix
        self.suffix = suffix
        self.include_date = include_date
        self.date_format = date_format
        self.ext = ext
        self._log_file: Path | None = None
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def _finish_cancelled(self, done: int) -> None:
        self._log(f"=== 用户取消，已完成 {done} 个 ===")
        self.finished_cancelled.emit(done)

    @staticmethod
    def _remove_if_exists(path: str) -> None:
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def _log(self, msg: str) -> None:
        self.log_line.emit(msg)
        if self._log_file:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(msg + "\n")

    def run(self) -> None:
        try:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._log_file = Path(self.out_dir) / f"build_{stamp}.log"
            self._log(f"=== 开始 {stamp} ===")
            combos = plan_combos(
                self.heads,
                self.mids,
                self.tails,
                self.k_heads,
                self.k_mids,
                self.k_tails,
                self.count,
            )
            total = len(combos)
            done = 0

            def on_step(video_index: int, name: str, step: float, step_total: int, phase: str) -> None:
                overall = ((video_index - 1) + step / step_total) / total
                pct = min(99, int(overall * 100))
                self.progress.emit(pct, f"第 {video_index}/{total} 个 · {name} · {phase}")

            for i, combo in enumerate(combos, start=1):
                if self._cancel_requested:
                    self._finish_cancelled(done)
                    return
                name = build_output_name(
                    prefix=self.prefix,
                    suffix=self.suffix,
                    seq=i,
                    ext=self.ext,
                    include_date=self.include_date,
                    date_format=self.date_format,
                )
                out_path = os.path.join(self.out_dir, name)
                self._log(f"--- 输出 {i}/{total}: {name} ---")
                self.progress.emit(
                    int((i - 1) / total * 100) if total else 0,
                    f"第 {i}/{total} 个 · {name} · 准备",
                )

                def step_cb(s: int, st: int, phase: str, *, vi: int = i, nm: str = name) -> None:
                    on_step(vi, nm, s, st, phase)

                try:
                    build_output(
                        combo,
                        out_path,
                        self.settings,
                        log=self._log,
                        progress=step_cb,
                        should_cancel=lambda: self._cancel_requested,
                    )
                except BuildCancelled:
                    self._remove_if_exists(out_path)
                    self._finish_cancelled(done)
                    return
                if self._cancel_requested:
                    self._remove_if_exists(out_path)
                    self._finish_cancelled(done)
                    return
                done += 1
            self.progress.emit(100, f"完成，共 {done} 个")
            self._log(f"=== 完成，共 {done} 个 ===")
            self.finished_ok.emit(done)
        except ComboLimitError as e:
            self._log(str(e))
            self.finished_err.emit(str(e))
        except Exception as e:
            tb = traceback.format_exc()
            self._log(tb)
            self.finished_err.emit(str(e))


class _GenerateProgressDialog(QDialog):
    """系统标题栏关闭即取消；关闭请求后保持显示直至后台线程结束。"""

    close_cancel = Signal()

    def __init__(self, label: str, anchor: QWidget | None = None):
        super().__init__(None)
        self._anchor = anchor
        self._cancelling = False
        self._allow_close = False
        self._fixed_frame_size: tuple[int, int] | None = None
        self.setWindowTitle("生成进度")
        # ponytail: macOS 下 WindowModal + parent 会变成 sheet，无标题栏关闭钮
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedWidth(420)
        # ponytail: QProgressDialog 在 macOS 上常无标题栏；QDialog + 显式 flags 才有系统关闭钮
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        self._msg = QLabel(label)
        self._msg.setWordWrap(True)
        fm = self._msg.fontMetrics()
        self._msg.setFixedHeight(fm.lineSpacing() * 2)
        lay.addWidget(self._msg)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setFormat("%p%")
        lay.addWidget(self._bar)

    def setLabelText(self, text: str) -> None:
        self._msg.setText(text)

    def setValue(self, percent: int) -> None:
        self._bar.setValue(percent)

    def mark_cancelling(self) -> None:
        self._cancelling = True

    def allow_close(self) -> None:
        self._allow_close = True

    def _request_cancel_close(self) -> None:
        if self._cancelling:
            return
        self.close_cancel.emit()

    def reject(self) -> None:
        if self._allow_close:
            super().reject()
            return
        self._request_cancel_close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            super().closeEvent(event)
            return
        self._request_cancel_close()
        event.ignore()

    def _lock_frame_size(self) -> None:
        if self._fixed_frame_size is not None:
            return
        self.adjustSize()
        self.setFixedSize(self.size())
        fg = self.frameGeometry()
        self._fixed_frame_size = (fg.width(), fg.height())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._lock_frame_size()
        self._reposition_on_anchor()

    def _reposition_on_anchor(self) -> None:
        anchor = self._anchor
        if anchor is None:
            return
        align = getattr(anchor, "_align_progress_to_message_box", None)
        if align is not None:
            align(self)
            QTimer.singleShot(0, lambda: align(self))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("视频拼接")
        self.resize(1060, 780)
        self.setMinimumSize(920, 660)
        self._worker: GenerateWorker | None = None
        self._progress_dlg: _GenerateProgressDialog | None = None
        self._msg_box_center: QPoint | None = None

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ---- 顶栏：标题 + 生成按钮（信息独立，操作一眼可见） ----
        header = QWidget()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(2, 0, 2, 0)
        title = QLabel("视频拼接")
        title.setObjectName("title")
        sub = QLabel("头 · 中 · 尾素材混合生成")
        sub.setObjectName("sub")
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        tcol.addWidget(title)
        tcol.addWidget(sub)
        hl.addLayout(tcol)
        hl.addStretch(1)
        self.btn_gen = QPushButton("开始生成")
        self.btn_gen.setObjectName("primary")
        self.btn_gen.clicked.connect(self._start_generate)
        hl.addWidget(self.btn_gen, alignment=Qt.AlignVCenter)
        root.addWidget(header)

        # ---- 可滚动正文 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        bow = QVBoxLayout(body)
        bow.setContentsMargins(0, 0, 0, 0)
        bow.setSpacing(8)

        # ---- 素材三卡片 ----
        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        self.panel_heads = VideoListPanel("头部素材")
        self.panel_mids = VideoListPanel("中部素材")
        self.panel_tails = VideoListPanel("尾部素材")
        for p in (self.panel_heads, self.panel_mids, self.panel_tails):
            mrow.addWidget(p, stretch=1)
        bow.addLayout(mrow)

        mid = QHBoxLayout()
        mid.setSpacing(8)
        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(8)
        mid.addLayout(left, stretch=3)
        mid.addLayout(right, stretch=2)
        bow.addLayout(mid)

        # ---- 左：合成设置 ----
        params = QGroupBox("合成设置")
        params.setProperty("class", "card")
        pg = QGridLayout(params)
        pg.setContentsMargins(10, 8, 10, 8)
        pg.setHorizontalSpacing(6)
        pg.setVerticalSpacing(6)
        pg.addWidget(QLabel("中部/片"), 0, 0)
        self.spin_km = _mini_spin(1)
        pg.addWidget(self.spin_km, 0, 1)
        pg.addWidget(QLabel("尾部/片"), 0, 2)
        self.spin_kt = _mini_spin(1)
        pg.addWidget(self.spin_kt, 0, 3)
        pg.addWidget(QLabel("生成数量"), 0, 4)
        self.spin_count = _mini_spin(1, minimum=1, maximum=99999, width=70)
        pg.addWidget(self.spin_count, 0, 5)
        pg.setColumnStretch(6, 1)
        self.lbl_max = QLabel("最大不重复组合: -")
        self.lbl_max.setProperty("class", "dim")
        pg.addWidget(self.lbl_max, 1, 0, 1, 7)
        left.addWidget(params)

        # ---- 左：命名与输出 ----
        naming = QGroupBox("命名与输出")
        naming.setProperty("class", "card")
        ng = QGridLayout(naming)
        ng.setContentsMargins(10, 8, 10, 8)
        ng.setHorizontalSpacing(6)
        ng.setVerticalSpacing(6)
        ng.addWidget(QLabel("前缀"), 0, 0)
        self.edit_prefix = QLineEdit()
        self.edit_prefix.setPlaceholderText("可选")
        ng.addWidget(self.edit_prefix, 0, 1)
        ng.addWidget(QLabel("后缀"), 0, 2)
        self.edit_suffix = QLineEdit()
        self.edit_suffix.setPlaceholderText("可选")
        ng.addWidget(self.edit_suffix, 0, 3)
        self.chk_date = QCheckBox("含日期")
        self.chk_date.setChecked(True)
        ng.addWidget(self.chk_date, 0, 4)
        self.combo_date_preset = QComboBox()
        for preset in DATE_FORMAT_PRESETS:
            self.combo_date_preset.addItem(preset[0])
        self.combo_date_preset.setCurrentIndex(2)
        self.combo_date_preset.setMinimumWidth(170)
        ng.addWidget(self.combo_date_preset, 0, 5)
        self.edit_prefix.textChanged.connect(self._update_name_preview)
        self.edit_suffix.textChanged.connect(self._update_name_preview)

        # 日期明细：第二行紧凑排列
        drow = QHBoxLayout()
        drow.setSpacing(4)
        self.combo_date_y = QComboBox()
        _fill_date_part_combo(self.combo_date_y, [("无", ""), ("Y", "%Y"), ("y", "%y")])
        self.combo_date_m = QComboBox()
        _fill_date_part_combo(self.combo_date_m, [("无", ""), ("M", "%m")])
        self.combo_date_d = QComboBox()
        _fill_date_part_combo(self.combo_date_d, [("无", ""), ("D", "%d")])
        self.combo_date_h = QComboBox()
        _fill_date_part_combo(self.combo_date_h, [("无", ""), ("H", "%H"), ("h", "%I")])
        self.combo_date_min = QComboBox()
        _fill_date_part_combo(self.combo_date_min, [("无", ""), ("m", "%M")])
        self.combo_date_s = QComboBox()
        _fill_date_part_combo(self.combo_date_s, [("无", ""), ("S", "%S")])
        for lab, cb in (("年", self.combo_date_y), ("月", self.combo_date_m),
                        ("日", self.combo_date_d), ("时", self.combo_date_h),
                        ("分", self.combo_date_min), ("秒", self.combo_date_s)):
            lbl = QLabel(lab)
            lbl.setFixedWidth(16)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            drow.addWidget(lbl)
            cb.setFixedWidth(72)
            drow.addWidget(cb)
        sep_lbl = QLabel("分隔")
        sep_lbl.setFixedWidth(28)
        sep_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        drow.addWidget(sep_lbl)
        self.combo_date_sep = QComboBox()
        self.combo_date_sep.addItem("无", "")
        self.combo_date_sep.addItem("-", "-")
        self.combo_date_sep.addItem("_", "_")
        self.combo_date_sep.addItem(".", ".")
        self.combo_date_sep.setFixedWidth(72)
        drow.addWidget(self.combo_date_sep)
        drow.addStretch(1)
        ng.addLayout(drow, 1, 0, 1, 6)

        self.lbl_name_preview = QLabel()
        self.lbl_name_preview.setObjectName("preview")
        ng.addWidget(self.lbl_name_preview, 2, 0, 1, 6)

        ng.addWidget(QLabel("输出目录"), 3, 0)
        self.edit_out_dir = QLineEdit()
        self.edit_out_dir.setPlaceholderText("选择生成视频的保存位置")
        ng.addWidget(self.edit_out_dir, 3, 1, 1, 3)
        out_dir_btns = QHBoxLayout()
        out_dir_btns.setSpacing(4)
        browse_out = QPushButton("选择…")
        browse_out.setProperty("class", "mini")
        browse_out.clicked.connect(self._pick_out_dir)
        open_out = QPushButton("打开")
        open_out.setProperty("class", "mini")
        open_out.clicked.connect(self._open_out_dir)
        out_dir_btns.addWidget(browse_out)
        out_dir_btns.addWidget(open_out)
        ng.addLayout(out_dir_btns, 3, 4, 1, 2)
        left.addWidget(naming)

        self._date_part_combos = (
            self.combo_date_y, self.combo_date_m, self.combo_date_d,
            self.combo_date_h, self.combo_date_min, self.combo_date_s,
            self.combo_date_sep,
        )
        self.combo_date_preset.currentIndexChanged.connect(self._apply_date_preset)
        self.chk_date.toggled.connect(self._set_date_parts_enabled)
        for combo in self._date_part_combos:
            combo.currentIndexChanged.connect(self._update_name_preview)

        # ---- 右：画质与格式 ----
        encode = QGroupBox("画质与格式")
        encode.setProperty("class", "card")
        eg = QGridLayout(encode)
        eg.setContentsMargins(10, 8, 10, 8)
        eg.setHorizontalSpacing(6)
        eg.setVerticalSpacing(6)
        eg.addWidget(QLabel("分辨率"), 0, 0)
        self.combo_res = QComboBox()
        self.combo_res.addItems(["原分辨率", "720p 宽屏", "1080p 宽屏", "720p 竖屏", "1080p 竖屏"])
        eg.addWidget(self.combo_res, 0, 1, 1, 2)
        eg.addWidget(QLabel("压缩"), 1, 0)
        self.combo_compress = QComboBox()
        for label, crf in COMPRESSION_PRESETS:
            self.combo_compress.addItem(f"{label}(CRF {crf})", crf)
        self.combo_compress.setCurrentIndex(DEFAULT_COMPRESSION_INDEX)
        eg.addWidget(self.combo_compress, 1, 1, 1, 2)
        eg.addWidget(QLabel("输出格式"), 2, 0)
        self.combo_ext = QComboBox()
        self.combo_ext.addItems(["mp4", "mov", "mkv"])
        self.combo_ext.setFixedWidth(90)
        self.combo_ext.currentTextChanged.connect(self._update_name_preview)
        eg.addWidget(self.combo_ext, 2, 1)
        self.chk_dedup = QCheckBox("重复帧清理")
        self.chk_dedup.setToolTip("mpdecimate 自动丢弃重复帧")
        eg.addWidget(self.chk_dedup, 2, 2)
        right.addWidget(encode)

        # ---- 右：水印 ----
        wm = QGroupBox("水印")
        wm.setProperty("class", "card")
        wg = QGridLayout(wm)
        wg.setContentsMargins(10, 8, 10, 8)
        wg.setHorizontalSpacing(6)
        wg.setVerticalSpacing(6)
        wg.addWidget(QLabel("图片"), 0, 0)
        self.edit_wm = QLineEdit()
        self.edit_wm.setPlaceholderText("可选，不选则无水印")
        wg.addWidget(self.edit_wm, 0, 1, 1, 2)
        wm_btn = QPushButton("选择…")
        wm_btn.setProperty("class", "mini")
        wm_btn.clicked.connect(self._pick_watermark)
        wg.addWidget(wm_btn, 0, 3)
        wg.addWidget(QLabel("位置"), 1, 0)
        self.combo_wm_pos = QComboBox()
        self.combo_wm_pos.addItems(["右下", "左下", "右上", "左上", "居中"])
        self.combo_wm_pos.setMinimumWidth(96)
        wg.addWidget(self.combo_wm_pos, 1, 1, 1, 3)
        wg.addWidget(QLabel("边距X"), 2, 0)
        self.spin_wm_mx = QSpinBox()
        self.spin_wm_mx.setRange(0, 9999)
        self.spin_wm_mx.setValue(10)
        self.spin_wm_mx.setFixedWidth(76)
        wg.addWidget(self.spin_wm_mx, 2, 1)
        wg.addWidget(QLabel("边距Y"), 2, 2)
        self.spin_wm_my = QSpinBox()
        self.spin_wm_my.setRange(0, 9999)
        self.spin_wm_my.setValue(10)
        self.spin_wm_my.setFixedWidth(76)
        wg.addWidget(self.spin_wm_my, 2, 3)
        wg.addWidget(QLabel("透明度"), 3, 0)
        op_row = QHBoxLayout()
        op_row.setSpacing(6)
        self.slider_wm_op = QSlider(Qt.Horizontal)
        self.slider_wm_op.setMinimum(10)
        self.slider_wm_op.setMaximum(100)
        self.slider_wm_op.setValue(70)
        self.lbl_wm_op = QLabel("70%")
        self.lbl_wm_op.setFixedWidth(36)
        self.slider_wm_op.valueChanged.connect(lambda v: self.lbl_wm_op.setText(f"{v}%"))
        op_row.addWidget(self.slider_wm_op, stretch=1)
        op_row.addWidget(self.lbl_wm_op)
        wg.addLayout(op_row, 3, 1, 1, 3)
        wg.addWidget(QLabel("缩放"), 4, 0)
        scale_row = QHBoxLayout()
        scale_row.setSpacing(6)
        self.slider_wm_scale = QSlider(Qt.Horizontal)
        self.slider_wm_scale.setMinimum(0)
        self.slider_wm_scale.setMaximum(200)
        self.slider_wm_scale.setValue(100)
        self.slider_wm_scale.setToolTip("相对水印原图尺寸的百分比（0–200）")
        self.lbl_wm_scale = QLabel("100%")
        self.lbl_wm_scale.setFixedWidth(40)
        self.slider_wm_scale.valueChanged.connect(
            lambda v: self.lbl_wm_scale.setText(f"{v}%")
        )
        scale_row.addWidget(self.slider_wm_scale, stretch=1)
        scale_row.addWidget(self.lbl_wm_scale)
        wg.addLayout(scale_row, 4, 1, 1, 3)
        right.addWidget(wm)
        right.addStretch(1)

        # ---- 日志卡 ----
        log_card = QGroupBox("运行日志")
        log_card.setProperty("class", "card")
        llay = QVBoxLayout(log_card)
        llay.setContentsMargins(10, 8, 10, 8)
        llay.setSpacing(6)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        hint = QLabel("可复制发给开发定位问题")
        hint.setProperty("class", "dim")
        toolbar.addWidget(hint)
        toolbar.addStretch(1)
        self.btn_copy_log = QPushButton("复制日志")
        self.btn_copy_log.setProperty("class", "mini")
        self.btn_copy_log.clicked.connect(self._copy_log)
        toolbar.addWidget(self.btn_copy_log)
        llay.addLayout(toolbar)
        self.log_view = QTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("运行日志…")
        self.log_view.setMinimumHeight(120)
        llay.addWidget(self.log_view)
        bow.addWidget(log_card)

        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        # ---- 联动 ----
        self._apply_date_preset(self.combo_date_preset.currentIndex())
        self._set_date_parts_enabled(self.chk_date.isChecked())
        for sp in (self.spin_km, self.spin_kt, self.spin_count):
            sp.valueChanged.connect(self._update_max_label)
        for panel in (self.panel_heads, self.panel_mids, self.panel_tails):
            model = panel.list.model()
            model.rowsInserted.connect(lambda *_: self._update_max_label())
            model.rowsRemoved.connect(lambda *_: self._update_max_label())

        try:
            ver = verify_ffmpeg(log=self._append_log)
            self._append_log(f"ffmpeg: {ver}")
        except Exception as e:
            self._append_log(f"警告: {e}")

        self._update_max_label()
        for combo in self.findChildren(QComboBox):
            _prepare_combo_popup(combo)

        self._focus_filter = _ClearFocusOnBlankFilter(self)
        QApplication.instance().installEventFilter(self._focus_filter)

    def _append_log(self, text: str) -> None:
        self.log_view.append(text)

    def _pick_out_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "输出目录")
        if d:
            self.edit_out_dir.setText(d)

    def _open_out_dir(self) -> None:
        out = self.edit_out_dir.text().strip()
        if not out:
            QMessageBox.information(self, "提示", "请先选择输出目录")
            return
        if not os.path.isdir(out):
            QMessageBox.warning(self, "提示", "输出目录不存在")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(out))

    def _pick_watermark(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, "水印图片", "", "图片 (*.png *.jpg *.jpeg *.webp);;全部 (*.*)"
        )
        if p:
            self.edit_wm.setText(p)

    def _k_heads(self) -> int:
        # ponytail: 片头固定每次从列表取 1 个；无列表则不用片头
        return 1 if self.panel_heads.paths() else 0

    def _k_mids(self) -> int:
        # ponytail: 中部列表为空时不取中部，忽略「每片中数量」
        if not self.panel_mids.paths():
            return 0
        return self.spin_km.value()

    def _update_max_label(self) -> None:
        for p in (self.panel_heads, self.panel_mids, self.panel_tails):
            p.refresh_count()
        nh = len(self.panel_heads.paths())
        nm = len(self.panel_mids.paths())
        nt = len(self.panel_tails.paths())
        mx = max_combinations(
            nh, self._k_heads(),
            nm, self._k_mids(),
            nt, self.spin_kt.value(),
        )
        self.lbl_max.setText(f"最大不重复组合: {mx}")

    def _wm_pos_key(self) -> str:
        return {
            "右下": "br",
            "左下": "bl",
            "右上": "tr",
            "左上": "tl",
            "居中": "center",
        }[self.combo_wm_pos.currentText()]

    def _date_sep(self) -> str:
        return str(self.combo_date_sep.currentData() or "")

    def _date_format(self) -> str:
        return compose_date_format(
            year_token=str(self.combo_date_y.currentData() or ""),
            month_token=str(self.combo_date_m.currentData() or ""),
            day_token=str(self.combo_date_d.currentData() or ""),
            hour_token=str(self.combo_date_h.currentData() or ""),
            minute_token=str(self.combo_date_min.currentData() or ""),
            second_token=str(self.combo_date_s.currentData() or ""),
            separator=self._date_sep(),
        )

    def _apply_date_preset(self, index: int) -> None:
        if index < 0 or index >= len(DATE_FORMAT_PRESETS):
            return
        _name, y, m, d, h, mi, s, sep = DATE_FORMAT_PRESETS[index]
        _set_date_part_combo(self.combo_date_y, y)
        _set_date_part_combo(self.combo_date_m, m)
        _set_date_part_combo(self.combo_date_d, d)
        _set_date_part_combo(self.combo_date_h, h)
        _set_date_part_combo(self.combo_date_min, mi)
        _set_date_part_combo(self.combo_date_s, s)
        sep_idx = self.combo_date_sep.findData(sep)
        self.combo_date_sep.setCurrentIndex(sep_idx if sep_idx >= 0 else 0)
        self._update_name_preview()

    def _set_date_parts_enabled(self, enabled: bool) -> None:
        self.combo_date_preset.setEnabled(enabled)
        for combo in self._date_part_combos:
            combo.setEnabled(enabled)
        self._update_name_preview()

    def _update_name_preview(self) -> None:
        if self.chk_date.isChecked() and not self._date_format():
            self.lbl_name_preview.setText("预览: （日期请至少选择年/月/日/时/分/秒之一）")
            return
        try:
            name = build_output_name(
                prefix=self.edit_prefix.text(),
                suffix=self.edit_suffix.text(),
                seq=1,
                ext=self.combo_ext.currentText(),
                include_date=self.chk_date.isChecked(),
                date_format=self._date_format(),
            )
        except ValueError:
            self.lbl_name_preview.setText("预览: （日期格式无效）")
            return
        self.lbl_name_preview.setText(f"预览: {name}")

    def _res_key(self) -> str:
        return {
            "720p 宽屏": "720p",
            "1080p 宽屏": "1080p",
            "720p 竖屏": "720p_portrait",
            "1080p 竖屏": "1080p_portrait",
        }.get(self.combo_res.currentText(), "original")

    def _validate(self) -> str | None:
        heads = self.panel_heads.paths()
        mids = self.panel_mids.paths()
        tails = self.panel_tails.paths()
        kh, km, kt = self._k_heads(), self._k_mids(), self.spin_kt.value()
        if kh + km + kt < 1:
            return "头/中/尾至少有一段素材数量大于 0"
        if km > len(mids) or kt > len(tails):
            return "某类素材数量不足，无法满足每片取用数量"
        if not tails and kt > 0:
            return "未添加尾部视频"
        out = self.edit_out_dir.text().strip()
        if not out:
            return "请选择输出目录"
        if not os.path.isdir(out):
            return "输出目录不存在"
        if not os.access(out, os.W_OK):
            return "输出目录不可写"
        wm = self.edit_wm.text().strip()
        if wm and not os.path.isfile(wm):
            return "水印文件不存在"
        count = self.spin_count.value()
        mx = max_combinations(len(heads), kh, len(mids), km, len(tails), kt)
        if count > mx:
            return f"生成数量 {count} 超过最大不重复组合 {mx}，请减少数量或增加素材"
        if self.chk_date.isChecked() and not self._date_format():
            return "包含日期时请至少选择年、月、日、时、分、秒之一"
        return None

    def _start_generate(self) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在生成中，请稍候")
            return
        err = self._validate()
        if err:
            QMessageBox.warning(self, "校验失败", err)
            return

        settings = EncodeSettings(
            resolution=self._res_key(),
            crf=int(self.combo_compress.currentData()),
            out_ext=self.combo_ext.currentText(),
            watermark_path=self.edit_wm.text().strip() or None,
            watermark_pos=self._wm_pos_key(),
            watermark_opacity=self.slider_wm_op.value() / 100.0,
            watermark_margin_x=self.spin_wm_mx.value(),
            watermark_margin_y=self.spin_wm_my.value(),
            watermark_scale=self.slider_wm_scale.value() / 100.0,
            dedup_enabled=self.chk_dedup.isChecked(),
        )
        self.btn_gen.setEnabled(False)
        self._show_progress_dialog("准备中…", 0)
        self._worker = GenerateWorker(
            self.panel_heads.paths(),
            self.panel_mids.paths(),
            self.panel_tails.paths(),
            self._k_heads(),
            self._k_mids(),
            self.spin_kt.value(),
            self.spin_count.value(),
            self.edit_out_dir.text().strip(),
            settings,
            self.edit_prefix.text(),
            self.edit_suffix.text(),
            self.chk_date.isChecked(),
            self._date_format(),
            self.combo_ext.currentText(),
        )
        self._worker.log_line.connect(self._append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self._worker.finished_cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _show_progress_dialog(self, message: str, percent: int) -> None:
        if self._progress_dlg is None:
            dlg = _GenerateProgressDialog(message, self)
            dlg.close_cancel.connect(self._on_progress_cancel)
            self._progress_dlg = dlg
        self._progress_dlg.setLabelText(message)
        self._progress_dlg.setValue(max(0, min(100, percent)))
        if not self._progress_dlg.isVisible():
            self._progress_dlg.show()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._msg_box_center = None

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._msg_box_center = None

    def _align_progress_to_message_box(self, dlg: QWidget) -> None:
        center = self._message_box_screen_center()
        self._align_dialog_center_to_point(dlg, center)

    def _message_box_screen_center(self) -> QPoint:
        """QMessageBox(parent=self) 的 frame 中心（不闪屏）。"""
        if self._msg_box_center is not None:
            return self._msg_box_center
        probe = QMessageBox(
            QMessageBox.Icon.Information,
            "完成",
            " ",
            QMessageBox.StandardButton.NoButton,
            self,
        )
        probe.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        probe.show()
        center = probe.frameGeometry().center()
        probe.hide()
        probe.deleteLater()
        self._msg_box_center = center
        return center

    def _align_dialog_center_to_point(self, dlg: QWidget, center: QPoint) -> None:
        dlg.ensurePolished()
        fixed = getattr(dlg, "_fixed_frame_size", None)
        if fixed is not None:
            fw, fh = fixed
        else:
            dlg.adjustSize()
            fg = dlg.frameGeometry()
            fw, fh = fg.width(), fg.height()
        dlg.move(center.x() - fw // 2, center.y() - fh // 2)

    def _close_progress_dialog(self) -> None:
        if self._progress_dlg is not None:
            self._progress_dlg.allow_close()
            self._progress_dlg.blockSignals(True)
            self._progress_dlg.close()
            self._progress_dlg = None

    def _on_progress_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._append_log("收到取消请求，正在停止当前编码…")
            self._worker.request_cancel()
            if self._progress_dlg is not None:
                self._progress_dlg.setLabelText("正在取消，正在停止当前编码…")
                self._progress_dlg.mark_cancelling()

    def _on_progress(self, percent: int, message: str) -> None:
        self._show_progress_dialog(message, percent)

    def _on_ok(self, n: int) -> None:
        self._close_progress_dialog()
        self.btn_gen.setEnabled(True)
        QMessageBox.information(self, "完成", f"已成功生成 {n} 个视频")
        self._open_out_dir()

    def _on_cancelled(self, n: int) -> None:
        self._close_progress_dialog()
        self.btn_gen.setEnabled(True)
        if n:
            QMessageBox.information(self, "已取消", f"已停止生成，已完成 {n} 个视频")
        else:
            QMessageBox.information(self, "已取消", "已停止生成")

    def _on_err(self, msg: str) -> None:
        self._close_progress_dialog()
        self.btn_gen.setEnabled(True)
        QMessageBox.critical(self, "生成失败", msg)

    def _copy_log(self) -> None:
        QGuiApplication.clipboard().setText(self.log_view.toPlainText())


def run_app() -> None:
    app = QApplication([])
    # ponytail: Fusion 才能稳定应用 QComboBox 圆角与弹出列表样式（macOS 原生样式会忽略大部分 QSS）
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
    win = MainWindow()
    win.show()
    app.exec()
