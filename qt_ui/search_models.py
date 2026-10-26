"""Models and the thumbnail painting of the Search tab (decision D5).

``ChannelModel``  a list of streamers (the search results, the recent streamers). The row text is the name, with
                  «● » in front of a streamer who is live (results only).
``VodModel``      the VOD table: thumbnail, title, date, length, views. One row per VOD; ``append`` adds a page.
``ThumbCache``    QPixmaps of the thumbnails, size-capped (least recently used goes first). Built on the GUI
                  thread only. A row whose pixmap was dropped is rebuilt from its file when it is painted again.
``ThumbDelegate`` paints the thumbnail column.

Nothing here touches the network. QPixmap is created on the GUI thread only (the rule of PLAN.md section 1).
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

from core.search import THUMB_GAP, THUMB_SIZE
from luckytwitch_engine import fmt_hms

CHANNEL_ROLE = Qt.ItemDataRole.UserRole + 1  # the streamer dict of a row: {id, login, name, live}
VIDEO_ROLE = Qt.ItemDataRole.UserRole + 1  # the VOD dict of a row
THUMB_ROLE = Qt.ItemDataRole.UserRole + 2  # the QPixmap of a row (or None)
THUMB_MARGIN = 6  # space to the left of a thumbnail
THUMB_COLUMN_WIDTH = THUMB_MARGIN + THUMB_SIZE[0] + THUMB_GAP
ROW_HEIGHT = THUMB_SIZE[1] + 8  # tall rows: room for the thumbnails
CHANNEL_ROW_HEIGHT = 26
MAX_CACHED_THUMBS = 300

VOD_COLUMNS = (  # key, heading, width, alignment, stretches
    ("thumb", "", THUMB_COLUMN_WIDTH, "w", False),
    ("title", "Title", 360, "w", True),
    ("date", "Date", 90, "center", False),
    ("dur", "Length", 80, "center", False),
    ("views", "Views", 70, "center", False),
)


def _alignment(kind: str) -> Qt.AlignmentFlag:
    return (Qt.AlignmentFlag.AlignHCenter if kind == "center" else Qt.AlignmentFlag.AlignLeft) | \
        Qt.AlignmentFlag.AlignVCenter


def load_thumb(path: str) -> QPixmap | None:
    """The file as a pixmap of exactly ``THUMB_SIZE`` (stretched like the tkinter ``resize``), or None when it
    cannot be read. GUI thread only."""
    image = QImage(path)
    if image.isNull():
        return None
    pix = QPixmap.fromImage(image.scaled(THUMB_SIZE[0], THUMB_SIZE[1], Qt.AspectRatioMode.IgnoreAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
    return None if pix.isNull() else pix


class ThumbCache:
    """Row id -> QPixmap, at most ``limit`` of them; the least recently used is dropped first."""

    def __init__(self, limit: int = MAX_CACHED_THUMBS):
        self.limit = limit
        self._pix: OrderedDict[str, QPixmap] = OrderedDict()

    def __len__(self) -> int:
        return len(self._pix)

    def __contains__(self, iid: str) -> bool:
        return iid in self._pix

    def put(self, iid: str, pix: QPixmap) -> None:
        self._pix[iid] = pix
        self._pix.move_to_end(iid)
        while len(self._pix) > self.limit:
            self._pix.popitem(last=False)

    def get(self, iid: str) -> QPixmap | None:
        pix = self._pix.get(iid)
        if pix is not None:
            self._pix.move_to_end(iid)
        return pix

    def clear(self) -> None:
        self._pix.clear()


class ChannelModel(QAbstractListModel):
    """Streamers as a list. ``live_marker=True`` (the search results) puts «● » before a live streamer."""

    def __init__(self, live_marker: bool = False, parent=None):
        super().__init__(parent)
        self.live_marker = live_marker
        self.channels: list[dict] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.channels)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.channels):
            return None
        ch = self.channels[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return ("● " if self.live_marker and ch.get("live") else "") + str(ch.get("name", ""))
        if role == CHANNEL_ROLE:
            return ch
        return None

    def set_channels(self, channels: list[dict]) -> None:
        self.beginResetModel()
        self.channels = list(channels)
        self.endResetModel()


class VodModel(QAbstractTableModel):
    """The VODs of the picked streamer. ``cache`` holds the thumbnails; ``paths`` the file each row's thumbnail
    was fetched to (so a pixmap the cache dropped can be made again)."""

    def __init__(self, cache: ThumbCache | None = None, parent=None):
        super().__init__(parent)
        self.cache = cache if cache is not None else ThumbCache()
        self.videos: list[dict] = []
        self.paths: dict[str, str] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.videos)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(VOD_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal or not 0 <= section < len(VOD_COLUMNS):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return VOD_COLUMNS[section][1]
        if role == Qt.ItemDataRole.TextAlignmentRole:  # the heading lines up with its column
            return int(_alignment(VOD_COLUMNS[section][3]))
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.videos):
            return None
        v, col = self.videos[index.row()], index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return ("", v["title"], v["date"], fmt_hms(v["duration"]), str(v["views"]))[col]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(_alignment(VOD_COLUMNS[col][3]))
        if role == VIDEO_ROLE:
            return v
        if role == THUMB_ROLE:
            return self.pixmap(str(index.row())) if col == 0 else None
        return None

    def pixmap(self, iid: str) -> QPixmap | None:
        """The thumbnail of row ``iid``: from the cache, or made again from its file (GUI thread)."""
        pix = self.cache.get(iid)
        if pix is None and iid in self.paths:
            pix = load_thumb(self.paths[iid])
            if pix is not None:
                self.cache.put(iid, pix)
        return pix

    def clear(self) -> None:
        self.beginResetModel()
        self.videos, self.paths = [], {}
        self.cache.clear()
        self.endResetModel()

    def append(self, videos: list[dict]) -> int:
        """Add a page; returns the row number of its first row (the row id of a VOD is its row number)."""
        start = len(self.videos)
        if videos:
            self.beginInsertRows(QModelIndex(), start, start + len(videos) - 1)
            self.videos.extend(videos)
            self.endInsertRows()
        return start

    def set_thumb(self, iid: str, path: str) -> bool:
        """A thumbnail arrived for row ``iid``. False when the row is gone or the file is not an image."""
        if not iid.isdigit() or int(iid) >= len(self.videos):
            return False
        pix = load_thumb(path)
        if pix is None:
            return False  # unreadable image: the row simply has none
        self.paths[iid] = path
        self.cache.put(iid, pix)
        index = self.index(int(iid), 0)
        self.dataChanged.emit(index, index, [THUMB_ROLE])
        return True


class ThumbDelegate(QStyledItemDelegate):
    """Paints the thumbnail column: the selection colour behind, the picture on the left, vertically centred."""

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        pix = index.data(THUMB_ROLE)
        if pix is not None:
            box = QRect(option.rect.left() + THUMB_MARGIN, option.rect.top() + (option.rect.height() - THUMB_SIZE[1]) // 2,
                        THUMB_SIZE[0], THUMB_SIZE[1])
            painter.drawPixmap(box, pix)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(THUMB_COLUMN_WIDTH, ROW_HEIGHT)
