from PyQt5.QtWidgets import QApplication
import sys
import qdarktheme
from app.ui.main_window import MainWindow

def run():
    app = QApplication(sys.argv)
    # Optional theme
    qdarktheme.setup_theme()


    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()