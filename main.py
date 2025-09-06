import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QLineEdit, QPushButton, QTextEdit
)

from backend.orchestrator import BackendOrchestrator


class MainWindow(QMainWindow):
    def __init__(self, orchestrator):
        super().__init__()
        self.orchestrator = orchestrator
        self.setWindowTitle("Pegasus - Drone Parameter Assistant")

        # --- Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # --- Widgets ---
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        layout.addWidget(self.chat_log)

        self.input_box = QLineEdit()
        layout.addWidget(self.input_box)

        self.send_button = QPushButton("Send")
        layout.addWidget(self.send_button)

        # --- Connect button ---
        self.send_button.clicked.connect(self.handle_send)

    def handle_send(self):
        user_message = self.input_box.text()
        if not user_message.strip():
            return

        # Show user message
        self.chat_log.append(f"You: {user_message}")
        self.input_box.clear()

        # Process with backend
        result = self.orchestrator.process_user_message(user_message)

        # Show AI response
        self.chat_log.append(f"Assistant: {result['response']}\n")


def main():
    # 🔑 Define your API key directly here
    api_key = "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"

    # --- Init backend orchestrator ---
    orchestrator = BackendOrchestrator({
        "openai_api_key": api_key,
        "llm_model": "gpt-4o-mini",
        "px4_params_path": "data/px4_params.json"
    })

    # --- Start Qt app ---
    app = QApplication(sys.argv)
    window = MainWindow(orchestrator)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
