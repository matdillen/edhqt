from collections import defaultdict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QLabel, QPushButton, QComboBox, QMessageBox, QCheckBox
)
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtCore import Qt, QPointF
from app.services.images import safe_stem
import re

# DeckPlaneDialog: A dialog to visualize deck cards in a 2D plane with clustering options.
class DeckPlaneDialog(QDialog):
    def __init__(self, deck_cards, image_lookup, get_card_meta, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deck Visualizer")
        self.resize(1200, 900)
        
        # data of cards in the deck
        self.deck_cards = deck_cards

        # dict of card name stem → image path
        self.image_lookup = image_lookup

        # function to retrieve card metadata
        self.get_card_meta = get_card_meta

        # z-order counter for raise-on-select
        self._z = 10  

        root = QVBoxLayout(self)

        # Top controls: clustering
        ctl = QHBoxLayout()
        ctl.addWidget(QLabel("Cluster by:"))
        self.cluster_combo = QComboBox()
        self.cluster_combo.addItems(["None", "Color Identity", "Type", "Mana Value"])
        ctl.addWidget(self.cluster_combo)
        self.check_supertype = QCheckBox("Include Supertype")
        ctl.addWidget(self.check_supertype)
        apply_btn = QPushButton("Apply layout")
        apply_btn.clicked.connect(self.apply_layout)
        ctl.addWidget(apply_btn)
        ctl.addStretch(1)
        root.addLayout(ctl)

        # Scene + view
        self.view = QGraphicsView()
        self.scene = QGraphicsScene(self.view)
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        root.addWidget(self.view)

        # Build the items
        self.card_items = []  # list[MovableCardItem]
        self._populate_scene()

        # Raise on select
        self.scene.selectionChanged.connect(self._bring_selected_to_front)

    def _next_z(self):
        # increment and return next z-order value to raise selected item above all others
        self._z += 1
        return self._z

    def _populate_scene(self):
        # load all cards as images into the scene
        spacing_x, spacing_y = 90, 130
        x, y = 0, 0
        max_row = 10

        for name, qty in self.deck_cards:
            key = safe_stem(name)
            img_path = self.image_lookup.get(key)
            if not img_path:
                continue

            # Small thumbnail pixmap for the plane
            pix = QPixmap(img_path)
            if pix.isNull():
                continue
            pix = pix.scaledToHeight(120, Qt.SmoothTransformation)

            # Cache metadata once
            meta = self.get_card_meta(name)

            for _ in range(qty):
                it = MovableCardItem(pix, name=name, img_path=img_path, plane_dialog=self, meta=meta)
                it.setPos(QPointF(x * spacing_x, y * spacing_y))
                it.setZValue(self._next_z())
                self.scene.addItem(it)
                self.card_items.append(it)
                x += 1
                if x >= max_row:
                    x = 0
                    y += 1

    def show_image_popup_on_path(self, img_path: str, max_w: int = 600, max_h: int = 900):
        # show higher res image in popup
        if not img_path:
            return
        pix = QPixmap(img_path)
        if pix.isNull():
            return
        scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        box = QMessageBox(self)
        box.setWindowTitle("Card Image")
        box.setIconPixmap(scaled)
        box.setText("")
        box.exec_()

    def _bring_selected_to_front(self):
        for it in self.scene.selectedItems():
            it.setZValue(self._next_z())

    def apply_layout(self):
        # sort cards according to certain filter parameters
        mode = self.cluster_combo.currentText()
        if mode == "None":
            self._layout_grid(self.card_items)
            return

        groups = defaultdict(list)
        for it in self.card_items:
            meta = it.meta or {}
            if mode == "Color Identity":
                k = meta.get("colorIdentity", "") or ""
            elif mode == "Type":
                # Use the supertype/type portion before em-dash
                tl = (meta.get("type") or "")
                k = tl.split("—", 1)[0].strip()
                if not self.check_supertype.isChecked():
                    k = re.sub("^(Basic|Legendary|Snow|World) ", "", k)
            elif mode == "Mana Value":
                mv = meta.get("manaValue") or ""
                try:
                    mv = int(float(mv))
                except Exception:
                    mv = 0
                k = f"MV {mv}"
            else:
                k = "All"
            groups[k].append(it)

        # Place each group in its own block vertically
        x0, y0 = 0, 0
        col_w, row_h, per_row = 90, 130, 10
        for _, items in sorted(groups.items(), key=lambda kv: kv[0]):
            # grid within block
            for i, it in enumerate(items):
                cx = x0 + (i % per_row) * col_w
                cy = y0 + (i // per_row) * row_h
                it.setPos(QPointF(cx, cy))
            # advance y0 for next block
            rows = (len(items) + per_row - 1) // per_row
            y0 += rows * row_h + 40

    def _layout_grid(self, items):
        col_w, row_h, per_row = 90, 130, 10
        for i, it in enumerate(items):
            cx = (i % per_row) * col_w
            cy = (i // per_row) * row_h
            it.setPos(QPointF(cx, cy))

class MovableCardItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, name: str, img_path: str, plane_dialog: DeckPlaneDialog, meta: dict):
        super().__init__(pixmap)

        self.name = name
        self.img_path = img_path
        self.plane_dialog = plane_dialog  # DeckPlaneDialog instance
        self.meta = meta or {}

        self.setToolTip(name)
        self.setFlags(
            QGraphicsPixmapItem.ItemIsSelectable |
            QGraphicsPixmapItem.ItemIsMovable |
            QGraphicsPixmapItem.ItemSendsGeometryChanges
        )
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            # show popup on right click
            if self.plane_dialog and self.img_path:
                self.plane_dialog.show_image_popup_on_path(self.img_path)
            # don’t start a drag on right-click
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            # bring to front on selection/drag start
            if self.plane_dialog:
                self.setZValue(self.plane_dialog._next_z())
        # default behavior (left click selects/drags)
        super().mousePressEvent(event)