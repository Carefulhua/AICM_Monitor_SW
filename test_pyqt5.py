import sys
from PyQt5.QtWidgets import QApplication, QLabel, QWidget

app = QApplication(sys.argv)
win = QWidget()
win.setWindowTitle('PyQt5 GUI Test')
win.resize(300, 150)
label = QLabel('Hello from PyQt5!\nGUI pop-up works.', win)
label.move(50, 50)
win.move(100, 100)
win.show()
sys.exit(app.exec_())