from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, 
                            QTextEdit, QListWidget, QListWidgetItem, QFrame,
                            QPushButton, QScrollArea, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QTextCharFormat, QTextCursor, QColor
from datetime import datetime
import json


class ChatBubbleWidget(QWidget):
    """Custom chat bubble widget for messages"""
    
    def __init__(self, message, is_user=True, metadata=None):
        super().__init__()
        self.message = message
        self.is_user = is_user
        self.metadata = metadata or {}
        self.init_ui()
    
    def init_ui(self):
        """Initialize the chat bubble UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        if self.is_user:
            # User message - right aligned
            layout.addStretch()
            bubble = self.create_user_bubble()
        else:
            # Bot message - left aligned
            bubble = self.create_bot_bubble()
            layout.addStretch()
        
        layout.addWidget(bubble)
        
        # Animate bubble appearance
        self.animate_appearance()
    
    def create_user_bubble(self):
        """Create user message bubble"""
        bubble_frame = QFrame()
        bubble_frame.setMaximumWidth(500)
        bubble_frame.setStyleSheet("""
            QFrame {
                background-color: #4a90e2;
                border-radius: 18px;
                padding: 12px 16px;
                margin: 2px;
            }
        """)
        
        layout = QVBoxLayout(bubble_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Message text
        message_label = QLabel(self.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("color: white; background: transparent;")
        message_label.setFont(QFont("Arial", 11))
        
        # Timestamp
        timestamp_label = QLabel(datetime.now().strftime("%H:%M"))
        timestamp_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 10px; background: transparent;")
        timestamp_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        layout.addWidget(message_label)
        layout.addWidget(timestamp_label)
        
        return bubble_frame
    
    def create_bot_bubble(self):
        """Create bot message bubble"""
        bubble_frame = QFrame()
        bubble_frame.setMaximumWidth(600)
        
        # Style based on message type
        msg_type = self.metadata.get("type", "normal")
        if msg_type == "error":
            bg_color = "#ff6b6b"
            text_color = "white"
        elif msg_type == "warning":
            bg_color = "#feca57"
            text_color = "#2f3542"
        elif msg_type == "success":
            bg_color = "#1dd1a1"
            text_color = "white"
        elif msg_type == "info":
            bg_color = "#54a0ff"
            text_color = "white"
        else:
            bg_color = "#f1f2f6"
            text_color = "#2f3542"
        
        bubble_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 18px;
                padding: 12px 16px;
                margin: 2px;
            }}
        """)
        
        layout = QVBoxLayout(bubble_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Bot avatar/indicator
        header_layout = QHBoxLayout()
        bot_indicator = QLabel("🤖")
        bot_indicator.setStyleSheet(f"color: {text_color}; background: transparent; font-size: 12px;")
        header_layout.addWidget(bot_indicator)
        header_layout.addStretch()
        
        # Message text
        message_label = QLabel(self.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(f"color: {text_color}; background: transparent;")
        message_label.setFont(QFont("Arial", 11))
        
        # Add special formatting for parameter names
        if "param_name" in self.metadata:
            param_name = self.metadata["param_name"]
            formatted_message = self.message.replace(param_name, f"<b>{param_name}</b>")
            message_label.setText(formatted_message)
        
        # Action buttons for parameter changes
        if msg_type == "change_request":
            self.add_action_buttons(layout, text_color)
        
        # Timestamp
        timestamp_label = QLabel(datetime.now().strftime("%H:%M"))
        timestamp_label.setStyleSheet(f"color: rgba({text_color}, 0.6); font-size: 10px; background: transparent;")
        timestamp_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        layout.addLayout(header_layout)
        layout.addWidget(message_label)
        layout.addWidget(timestamp_label)
        
        return bubble_frame
    
    def add_action_buttons(self, layout, text_color):
        """Add action buttons for parameter change requests"""
        button_layout = QHBoxLayout()
        
        confirm_btn = QPushButton("✓ Confirm")
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255,255,255,0.2);
                color: {text_color};
                border: 1px solid rgba(255,255,255,0.3);
                padding: 6px 12px;
                border-radius: 12px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.3);
            }}
        """)
        
        cancel_btn = QPushButton("✗ Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255,255,255,0.2);
                color: {text_color};
                border: 1px solid rgba(255,255,255,0.3);
                padding: 6px 12px;
                border-radius: 12px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.3);
            }}
        """)
        
        button_layout.addWidget(confirm_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
    
    def animate_appearance(self):
        """Animate bubble appearance"""
        self.setStyleSheet("QWidget { opacity: 0; }")
        
        # Fade in animation (simplified)
        QTimer.singleShot(50, lambda: self.setStyleSheet("QWidget { opacity: 1; }"))


class LogWidget(QWidget):
    """Widget for displaying system logs and activity"""
    
    def __init__(self):
        super().__init__()
        self.log_entries = []
        self.init_ui()
    
    def init_ui(self):
        """Initialize log widget UI"""
        layout = QVBoxLayout(self)
        
        # Log display
        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(200)
        self.log_list.setStyleSheet("""
            QListWidget {
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 5px;
                padding: 5px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 3px;
                border-bottom: 1px solid #e9ecef;
            }
            QListWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
        """)
        
        # Clear button
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.clear_log)
        clear_btn.setMaximumWidth(100)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        layout.addWidget(self.log_list)
        layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignRight)
    
    def add_entry(self, log_type, message):
        """Add a new log entry"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color coding by type
        colors = {
            "user_query": "#007bff",
            "bot_response": "#28a745", 
            "error": "#dc3545",
            "warning": "#ffc107",
            "connection": "#17a2b8",
            "param_change": "#6610f2",
            "system": "#6c757d"
        }
        
        color = colors.get(log_type, "#6c757d")
        
        entry = {
            "timestamp": timestamp,
            "type": log_type,
            "message": message,
            "color": color
        }
        
        self.log_entries.append(entry)
        
        # Create list item
        item = QListWidgetItem(f"[{timestamp}] {log_type.upper()}: {message}")
        item.setForeground(QColor(color))
        
        self.log_list.addItem(item)
        
        # Auto-scroll to bottom
        self.log_list.scrollToBottom()
        
        # Limit log entries (keep last 100)
        if len(self.log_entries) > 100:
            self.log_entries.pop(0)
            self.log_list.takeItem(0)
    
    def clear_log(self):
        """Clear all log entries"""
        self.log_entries.clear()
        self.log_list.clear()
        self.add_entry("system", "Log cleared")


class ConnectionStatusWidget(QWidget):
    """Widget showing connection status with visual indicator"""
    
    status_changed = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()
        self.is_connected = False
        self.init_ui()
        
        # Blinking timer for disconnected state
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.toggle_blink)
        self.blink_state = False
    
    def init_ui(self):
        """Initialize connection status UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Status indicator (colored circle)
        self.status_indicator = QLabel("●")
        self.status_indicator.setFont(QFont("Arial", 16))
        
        # Status text
        self.status_label = QLabel("Disconnected")
        self.status_label.setFont(QFont("Arial", 10))
        
        layout.addWidget(self.status_indicator)
        layout.addWidget(self.status_label)
        
        self.update_display()
        
    def update_status(self, connected):
        """Update connection status"""
        self.is_connected = connected
        self.update_display()
        self.status_changed.emit(connected)
        
        if connected:
            self.blink_timer.stop()
        else:
            self.blink_timer.start(1000)  # Blink every second
    
    def update_display(self):
        """Update visual display based on status"""
        if self.is_connected:
            self.status_indicator.setStyleSheet("color: #28a745;")  # Green
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: #28a745;")
        else:
            self.status_indicator.setStyleSheet("color: #dc3545;")  # Red
            self.status_label.setText("Disconnected") 
            self.status_label.setStyleSheet("color: #dc3545;")
    
    def toggle_blink(self):
        """Toggle blink state for disconnected indicator"""
        if not self.is_connected:
            self.blink_state = not self.blink_state
            opacity = "0.3" if self.blink_state else "1.0"
            self.status_indicator.setStyleSheet(f"color: #dc3545; opacity: {opacity};")


class ParameterInfoWidget(QWidget):
    """Widget for displaying detailed parameter information"""
    
    def __init__(self, param_name=None, param_data=None):
        super().__init__()
        self.param_name = param_name
        self.param_data = param_data or {}
        self.init_ui()
    
    def init_ui(self):
        """Initialize parameter info UI"""
        layout = QVBoxLayout(self)
        
        # Parameter name header
        if self.param_name:
            name_label = QLabel(self.param_name)
            name_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            name_label.setStyleSheet("color: #495057; margin-bottom: 5px;")
            layout.addWidget(name_label)
        
        # Parameter details
        self.details_frame = QFrame()
        self.details_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        self.details_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        
        details_layout = QVBoxLayout(self.details_frame)
        
        # Add parameter information
        if self.param_data:
            self.populate_details(details_layout)
        else:
            placeholder = QLabel("Select a parameter to view details")
            placeholder.setStyleSheet("color: #6c757d; font-style: italic;")
            details_layout.addWidget(placeholder)
        
        layout.addWidget(self.details_frame)
    
    def populate_details(self, layout):
        """Populate parameter details"""
        details = [
            ("Description", self.param_data.get("description", "N/A")),
            ("Type", self.param_data.get("type", "N/A")),
            ("Default Value", str(self.param_data.get("default", "N/A"))),
            ("Min Value", str(self.param_data.get("min", "N/A"))),
            ("Max Value", str(self.param_data.get("max", "N/A"))),
            ("Unit", self.param_data.get("unit", "N/A")),
            ("Group", self.param_data.get("group", "N/A"))
        ]
        
        for label_text, value in details:
            detail_layout = QHBoxLayout()
            
            label = QLabel(f"{label_text}:")
            label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            label.setMinimumWidth(100)
            
            value_label = QLabel(str(value))
            value_label.setWordWrap(True)
            value_label.setFont(QFont("Arial", 10))
            
            detail_layout.addWidget(label)
            detail_layout.addWidget(value_label)
            detail_layout.addStretch()
            
            layout.addLayout(detail_layout)
    
    def update_parameter(self, param_name, param_data):
        """Update displayed parameter information"""
        self.param_name = param_name
        self.param_data = param_data
        
        # Clear and rebuild UI
        self.deleteLater()
        self.__init__(param_name, param_data)


class SessionHistoryWidget(QWidget):
    """Widget for displaying chat session history"""
    
    session_selected = pyqtSignal(list)  # Emit selected session data
    
    def __init__(self):
        super().__init__()
        self.sessions = []
        self.init_ui()
    
    def init_ui(self):
        """Initialize session history UI"""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Session History")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        
        # Session list
        self.session_list = QListWidget()
        self.session_list.setMaximumHeight(150)
        self.session_list.itemClicked.connect(self.on_session_selected)
        self.session_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #e9ecef;
                border-radius: 3px;
                margin: 1px;
            }
            QListWidget::item:hover {
                background-color: #e3f2fd;
            }
            QListWidget::item:selected {
                background-color: #2196f3;
                color: white;
            }
        """)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_selected_session)
        load_btn.setMaximumWidth(60)
        
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self.delete_selected_session)
        delete_btn.setMaximumWidth(60)
        delete_btn.setStyleSheet("QPushButton { background-color: #dc3545; }")
        
        button_layout.addWidget(load_btn)
        button_layout.addWidget(delete_btn)
        button_layout.addStretch()
        
        layout.addWidget(title)
        layout.addWidget(self.session_list)
        layout.addLayout(button_layout)
        
        # Load existing sessions
        self.refresh_sessions()
    
    def refresh_sessions(self):
        """Refresh session list from saved files"""
        # Placeholder - will integrate with actual file system
        self.session_list.clear()
        
        # Mock sessions for demonstration
        mock_sessions = [
            {"name": "Session 2024-01-15 10:30", "file": "session_20240115_1030.json", "message_count": 12},
            {"name": "Session 2024-01-15 14:22", "file": "session_20240115_1422.json", "message_count": 8},
            {"name": "Session 2024-01-14 16:45", "file": "session_20240114_1645.json", "message_count": 15}
        ]
        
        for session in mock_sessions:
            item_text = f"{session['name']} ({session['message_count']} messages)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, session)
            self.session_list.addItem(item)
    
    def on_session_selected(self, item):
        """Handle session selection"""
        session_data = item.data(Qt.ItemDataRole.UserRole)
        # Could emit signal or highlight selection
        pass
    
    def load_selected_session(self):
        """Load the selected session"""
        current_item = self.session_list.currentItem()
        if current_item:
            session_data = current_item.data(Qt.ItemDataRole.UserRole)
            # This would load actual session data
            self.session_selected.emit([])  # Emit loaded session messages
    
    def delete_selected_session(self):
        """Delete the selected session"""
        current_row = self.session_list.currentRow()
        if current_row >= 0:
            self.session_list.takeItem(current_row)
            # Would also delete the actual file


class QuickActionsWidget(QWidget):
    """Widget with quick action buttons for common tasks"""
    
    action_triggered = pyqtSignal(str, dict)  # action_name, parameters
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize quick actions UI"""
        layout = QVBoxLayout(self)
        
        title = QLabel("Quick Actions")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        
        # Action buttons
        actions = [
            ("📊 System Status", "get_status", "Get current system status and health"),
            ("🔧 Common Parameters", "show_common", "Show frequently used parameters"),
            ("⚠️ Check Warnings", "check_warnings", "Check for parameter warnings"),
            ("📋 Export Config", "export_config", "Export current configuration"),
            ("🔄 Reset to Defaults", "reset_defaults", "Reset parameters to default values")
        ]
        
        for icon_text, action_name, tooltip in actions:
            btn = QPushButton(icon_text)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda checked, name=action_name: self.trigger_action(name))
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 8px 12px;
                    margin: 2px;
                    background-color: white;
                    border: 1px solid #dee2e6;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #f8f9fa;
                    border-color: #4a90e2;
                }
                QPushButton:pressed {
                    background-color: #e9ecef;
                }
            """)
            layout.addWidget(btn)
        
        layout.addWidget(title)
        for i in range(1, layout.count()):
            layout.addWidget(layout.itemAt(i).widget())
        
        layout.addStretch()
    
    def trigger_action(self, action_name):
        """Trigger a quick action"""
        self.action_triggered.emit(action_name, {})


# Export all widgets for easy importing
__all__ = [
    'ChatBubbleWidget',
    'LogWidget', 
    'ConnectionStatusWidget',
    'ParameterInfoWidget',
    'SessionHistoryWidget',
    'QuickActionsWidget'
]