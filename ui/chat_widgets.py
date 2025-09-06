# ui/chat_widgets.py
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout
from PyQt6.QtCore import Qt

class ChatBubble(QWidget):
    def __init__(self, text: str, is_user: bool = True):
        super().__init__()
        layout = QHBoxLayout()
        label = QLabel(text)
        label.setWordWrap(True)

        if is_user:
            label.setStyleSheet("background-color: #d1e7dd; padding: 6px; border-radius: 10px;")
            layout.addStretch()
            layout.addWidget(label)
        else:
            label.setStyleSheet("background-color: #f8d7da; padding: 6px; border-radius: 10px;")
            layout.addWidget(label)
            layout.addStretch()

        self.setLayout(layout)
