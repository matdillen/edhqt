from PyQt5.QtWidgets import QDialog, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QMessageBox
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPixmap, QPainter

class DeckPlaneDialog(QDialog):
    def __init__(self, deck_cards, image_lookup, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deck Visualizer")
        self.resize(1000, 800)

        layout = QVBoxLayout(self)
        self.view = QGraphicsView()
        layout.addWidget(self.view)

        self.scene = QGraphicsScene(self.view)
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)

        # optional: allow zooming and panning
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)

        # load cards into the scene
        spacing = 80
        x, y = 0, 0
        for name, qty in deck_cards:
            img_path = image_lookup.get(name.lower())
            if not img_path:
                continue
            pix = QPixmap(img_path).scaledToHeight(120, Qt.SmoothTransformation)
            for i in range(qty):
                item = MovableCardItem(pix, name = name, img_path=img_path, plane_dialog=self)
                item.setPos(QPointF(x, y))
                self.scene.addItem(item)
                x += spacing
                if x > 800:
                    x = 0
                    y += 140

    def show_image_popup_on_path(self, img_path: str, max_w: int = 600, max_h: int = 900):
        if not img_path:
            return
        pix = QPixmap(img_path)
        if pix.isNull():
            return
        # scale nicely for screen
        scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        box = QMessageBox(self)
        box.setWindowTitle("Card Image")
        box.setIconPixmap(scaled)
        # Remove the default text space so only the pixmap shows
        box.setText("")
        box.exec_()

class MovableCardItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, name, img_path, plane_dialog):
        super().__init__(pixmap)

        self.name = name
        self.img_path = img_path
        self.plane_dialog = plane_dialog  # DeckPlaneDialog instance

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
        # default behavior (left click selects/drags)
        super().mousePressEvent(event)