"""The queue as a table model (decision D5): five columns, one row per queued job.

``QueueItem`` keeps what the tkinter app kept in its ``items`` dicts: the job, the row id, the plain status word
(«done (3 files)» is stored as «done») and the files a finished job made. The model shows what the Status column
showed: the text with an icon in front. Row ids are strings like ``I001``; a number is never used twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from core.status import FINISHED, STATUS_COLOURS, queue_summary, status_label, status_word

COLUMNS = (  # key, heading, width, alignment, stretches
    ("n", "#", 40, "center", False),
    ("video", "Video", 420, "w", True),
    ("parts", "Parts", 70, "center", False),
    ("mode", "Strategy", 140, "center", False),
    ("status", "Status", 200, "w", False),
)
STATUS_ROLE = Qt.ItemDataRole.UserRole + 1  # the plain status word of the row («done»)
IID_ROLE = Qt.ItemDataRole.UserRole + 2  # the row id


def _alignment(kind: str) -> Qt.AlignmentFlag:
    return (Qt.AlignmentFlag.AlignHCenter if kind == "center" else Qt.AlignmentFlag.AlignLeft) | \
        Qt.AlignmentFlag.AlignVCenter


@dataclass
class QueueItem:
    job: object
    iid: str
    n: int  # the number shown in the «#» column when the row was added (not renumbered afterwards)
    label: str
    parts: int
    strategy: str
    status: str = "queued"  # the plain word: queued | running | done | failed | cancelled
    shown_status: str = "queued"  # the full text the job reported, e.g. «done (3 files)»
    files: list[str] = field(default_factory=list)


class QueueModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[QueueItem] = []
        self._counter = 0

    # ---- model interface ---- #
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal or not 0 <= section < len(COLUMNS):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][1]
        if role == Qt.ItemDataRole.TextAlignmentRole:  # the heading lines up with its column
            return int(_alignment(COLUMNS[section][3]))
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.items):
            return None
        it, col = self.items[index.row()], index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (str(it.n), it.label, str(it.parts), it.strategy, status_label(it.shown_status))[col]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(_alignment(COLUMNS[col][3]))
        if role == Qt.ItemDataRole.ForegroundRole:  # each row is coloured by how its job is doing
            colour = STATUS_COLOURS.get(it.status)
            return QColor(colour) if colour else None
        if role == STATUS_ROLE:
            return it.status
        if role == IID_ROLE:
            return it.iid
        return None

    # ---- the queue ---- #
    def add(self, job: object, label: str, n_parts: int, strategy: str) -> QueueItem:
        self._counter += 1
        item = QueueItem(job, f"I{self._counter:03d}", len(self.items) + 1, label, n_parts, strategy)
        row = len(self.items)
        self.beginInsertRows(QModelIndex(), row, row)
        self.items.append(item)
        self.endInsertRows()
        return item

    def find(self, iid: str) -> QueueItem | None:
        return next((i for i in self.items if i.iid == iid), None)

    def row_of(self, iid: str) -> int:
        return next((r for r, i in enumerate(self.items) if i.iid == iid), -1)

    def set_status(self, iid: str, status: str) -> bool:
        """«done (3 files)» -> the row says that, the stored status is «done». False when the row is gone."""
        row = self.row_of(iid)
        if row < 0:
            return False
        item = self.items[row]
        item.status = status_word(status)
        item.shown_status = status
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))
        return True

    def remove(self, iid: str) -> None:
        row = self.row_of(iid)
        if row >= 0:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.items[row]
            self.endRemoveRows()

    def clear_finished(self) -> None:
        for item in [i for i in self.items if i.status in FINISHED]:
            self.remove(item.iid)

    def summary(self) -> str:
        return queue_summary([i.status for i in self.items])
