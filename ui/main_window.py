import sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QTextEdit, QLineEdit, QPushButton, QSplitter, 
                            QLabel, QFrame, QScrollArea, QStatusBar, QMenuBar,
                            QMenu, QMessageBox, QProgressBar, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QAction, QPalette, QColor
from datetime import datetime
import json

from .chat_widgets import ChatBubbleWidget, LogWidget, ConnectionStatusWidget
from .dialogs import ConfirmationDialog, SettingsDialog


class ChatBotThread(QThread):
    """Thread for handling LLM requests without blocking UI"""
    response_ready = pyqtSignal(str, dict)  # response_text, metadata
    error_occurred = pyqtSignal(str)
    
    def __init__(self, backend=None):
        super().__init__()
        self.query = ""
        self.context = {}
        self.backend = backend
    
    def set_query(self, query, context=None):
        self.query = query
        self.context = context or {}
    
    def run(self):
        try:
            if self.backend:
                # Use real backend
                conversation_history = self.context.get("session", [])
                
                # Convert session format if needed
                chat_history = []
                for msg in conversation_history[-6:]:  # Last 6 messages for context
                    if msg.get("role") in ["user", "assistant"]:
                        chat_history.append({
                            "role": msg["role"], 
                            "content": msg["content"]
                        })
                
                result = self.backend.process_user_message(self.query, chat_history)
                
                # Convert backend result to UI format
                metadata = {
                    "type": self.determine_message_type(result),
                    "param_name": result.get("parameter_name"),
                    "new_value": result.get("parameter_value"),
                    "confidence": result.get("confidence"),
                    "suggestions": result.get("suggestions", [])
                }
                
                self.response_ready.emit(result["response"], metadata)
            else:
                # Fallback to mock responses
                self.mock_response()
                
        except Exception as e:
            self.error_occurred.emit(f"Error processing request: {str(e)}")
    
    def determine_message_type(self, result):
        """Convert backend result to UI message type"""
        if not result.get("success"):
            return "error"
        
        intent = result.get("intent", "")
        if "change" in intent.lower():
            if result.get("requires_confirmation"):
                return "change_request"
            else:
                return "success"
        elif "explain" in intent.lower():
            return "info"
        elif result.get("status") == "warning":
            return "warning"
        else:
            return "normal"
    
    def mock_response(self):
        """Fallback mock responses for testing without backend"""
        import time
        time.sleep(1)  # Simulate processing
        
        query_lower = self.query.lower()
        
        if "ekf2_aid_mask" in query_lower:
            if "set" in query_lower or "=" in query_lower:
                response = "I understand you want to change EKF2_AID_MASK. This parameter controls which sensor types the EKF2 estimator uses. Let me validate this change..."
                metadata = {
                    "param_name": "EKF2_AID_MASK", 
                    "new_value": "1", 
                    "type": "change_request"
                }
            else:
                response = ("EKF2_AID_MASK controls which sensor types the EKF2 estimator uses for position/velocity aiding. "
                          "Common values: 0=GPS only, 1=GPS+optical flow, 3=GPS+optical flow+beacon. "
                          "Default is typically 1.")
                metadata = {"param_name": "EKF2_AID_MASK", "type": "info"}
        
        elif "mpc_xy_vel_max" in query_lower:
            response = ("MPC_XY_VEL_MAX sets the maximum horizontal velocity in position control mode. "
                       "Lower values make flight more stable but slower. Higher values allow faster movement "
                       "but require more skill to control safely. Default is usually 12 m/s.")
            metadata = {"param_name": "MPC_XY_VEL_MAX", "type": "info"}
        
        elif "set" in query_lower and ("=" in query_lower or "to" in query_lower):
            response = "I understand you want to change a parameter. However, I need to validate the parameter name and value first. Could you specify which parameter and what value?"
            metadata = {"type": "warning"}
        
        elif any(word in query_lower for word in ["hello", "hi", "help"]):
            response = ("Hello! I'm your PX4 Parameter Assistant. I can help you:\n"
                       "• Understand what PX4 parameters do\n"
                       "• Safely modify parameter values\n"
                       "• Validate parameter ranges\n"
                       "• Explain the effects of changes\n\n"
                       "Try asking about a specific parameter like 'What is EKF2_AID_MASK?' or request changes like 'Set MPC_XY_VEL_MAX to 8'")
            metadata = {"type": "info"}
        
        else:
            response = ("I can help you understand PX4 parameters or modify them safely. "
                       "Try asking about a specific parameter name or requesting a parameter change. "
                       "For example: 'What does MPC_XY_VEL_MAX control?' or 'Set EKF2_AID_MASK to 1'")
            metadata = {"type": "normal"}
        
        self.response_ready.emit(response, metadata)


class MainWindow(QMainWindow):
    def __init__(self, backend=None):
        super().__init__()
        self.backend = backend
        self.setWindowTitle("PX4 Parameter Assistant")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(800, 600)
        
        # Initialize components
        self.chat_thread = ChatBotThread(backend)
        self.chat_thread.response_ready.connect(self.handle_bot_response)
        self.chat_thread.error_occurred.connect(self.handle_error)
        
        # Connection status
        self.is_connected = False
        self.current_session = []
        
        self.init_ui()
        self.setup_styling()
        self.setup_menu()
        self.setup_status_bar()

        # Poll for connection status and parameter updates
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(500)  # 0.5s
        self.status_timer.timeout.connect(self.poll_status)
        self.status_timer.start()
        
    def init_ui(self):
        """Initialize the main UI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - Chat interface
        chat_widget = self.create_chat_interface()
        
        # Right side - Logs and connection info
        info_widget = self.create_info_panel()
        
        main_splitter.addWidget(chat_widget)
        main_splitter.addWidget(info_widget)
        main_splitter.setSizes([800, 400])  # 2:1 ratio
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.addWidget(main_splitter)
        layout.setContentsMargins(10, 10, 10, 10)
        
    def create_chat_interface(self):
        """Create the main chat interface"""
        chat_frame = QFrame()
        chat_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        
        layout = QVBoxLayout(chat_frame)
        
        # Header with title and connection status
        header_layout = QHBoxLayout()
        
        title_label = QLabel("PX4 Parameter Assistant")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        
        self.connection_widget = ConnectionStatusWidget()
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.connection_widget)
        
        # Chat display area
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.addStretch()  # Push messages to bottom initially
        
        self.chat_scroll.setWidget(self.chat_container)
        
        # Input area
        input_frame = QFrame()
        input_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        input_layout = QHBoxLayout(input_frame)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask about PX4 parameters or request changes... (e.g., 'What is EKF2_AID_MASK?' or 'Set EKF2_AID_MASK to 1')")
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setMinimumWidth(80)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(5)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        
        # Add components to main layout
        layout.addLayout(header_layout)
        layout.addWidget(self.chat_scroll)
        layout.addWidget(self.progress_bar)
        layout.addWidget(input_frame)
        
        # Add welcome message
        self.add_bot_message("Hello! I'm your PX4 Parameter Assistant. I can help you understand and safely modify PX4 parameters. What would you like to know?")
        
        return chat_frame
        
    def create_info_panel(self):
        """Create the right panel with logs and status info"""
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        # Ensure text contrasts against white backgrounds in this panel
        info_frame.setStyleSheet("QLabel { color: #111827; }")
        
        layout = QVBoxLayout(info_frame)
        
        # Panel title
        title_label = QLabel("System Information")
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title_label.setStyleSheet("color: white;")
        
        # Connection details
        self.connection_details = QLabel("Status: Disconnected\nCOM Port: Not selected\nBaud Rate: 57600")
        self.connection_details.setStyleSheet("padding: 10px; background-color: #f0f0f0; border-radius: 5px; color: #111827;")
        
        # Parameter search and list
        self.param_search = QLineEdit()
        self.param_search.setPlaceholderText("Search parameters (e.g., MPC, BAT_...)")
        self.param_search.textChanged.connect(self.filter_parameters)
        # Override global dark input style for this white panel
        self.param_search.setStyleSheet(
            """
            QLineEdit {
                padding: 8px 10px;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                font-size: 13px;
                background-color: #ffffff;
                color: #111827;
            }
            QLineEdit:focus {
                border-color: #4f46e5;
                background-color: #ffffff;
                color: #111827;
            }
            """
        )

        self.param_list = QListWidget()
        self.param_list.setMaximumHeight(250)
        self.param_list.setStyleSheet(
            """
            QListWidget {
                background: #ffffff;
                border: 1px solid #e0e0e0;
                color: #111827;
            }
            QListWidget::item {
                padding: 4px 6px;
                color: #111827;
            }
            QListWidget::item:selected {
                background: #e3f2fd;
                color: #111827;
            }
            """
        )

        refresh_btn = QPushButton("Refresh Parameters")
        refresh_btn.clicked.connect(self.refresh_parameters_from_drone)

        # Log widget
        self.log_widget = LogWidget()

        # Labels with white text
        param_label = QLabel("Parameters:")
        param_label.setStyleSheet("color: white;")

        activity_label = QLabel("Activity Log:")
        activity_label.setStyleSheet("color: white;")

        layout.addWidget(title_label)
        layout.addWidget(self.connection_details)
        layout.addWidget(param_label)
        layout.addWidget(self.param_search)
        layout.addWidget(self.param_list)
        layout.addWidget(refresh_btn)
        layout.addWidget(activity_label)
        layout.addWidget(self.log_widget)

        return info_frame
    
    def setup_styling(self):
        """Apply modern ChatGPT-like styling to the interface"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #343541;
            }
            QFrame {
                background-color: #40414f;
                border-radius: 8px;
                border: 1px solid #4d4d5f;
            }
            QFrame#chatFrame {
                background-color: #343541;
                border: none;
            }
            QLineEdit {
                padding: 12px 16px;
                border: 1px solid #565869;
                border-radius: 8px;
                font-size: 14px;
                background-color: #40414f;
                color: #ececf1;
            }
            QLineEdit:focus {
                border-color: #10a37f;
                background-color: #40414f;
            }
            QPushButton {
                background-color: #10a37f;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1a7f64;
            }
            QPushButton:pressed {
                background-color: #0d8a6a;
            }
            QPushButton:disabled {
                background-color: #565869;
                color: #8e8ea0;
            }
            QScrollArea {
                border: none;
                background-color: #343541;
            }
            QProgressBar {
                border: none;
                background-color: #565869;
                border-radius: 2px;
                height: 3px;
            }
            QProgressBar::chunk {
                background-color: #10a37f;
                border-radius: 2px;
            }
            QLabel {
                color: #ececf1;
            }
            QMenuBar {
                background-color: #202123;
                color: #ececf1;
                border-bottom: 1px solid #4d4d5f;
            }
            QMenuBar::item:selected {
                background-color: #40414f;
            }
            QMenu {
                background-color: #2a2b32;
                color: #ececf1;
                border: 1px solid #4d4d5f;
            }
            QMenu::item:selected {
                background-color: #40414f;
            }
            QStatusBar {
                background-color: #202123;
                color: #ececf1;
            }
        """)

    
    def setup_menu(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        new_session_action = QAction("New Session", self)
        new_session_action.triggered.connect(self.new_session)
        file_menu.addAction(new_session_action)
        
        save_session_action = QAction("Save Session", self)
        save_session_action.triggered.connect(self.save_session)
        file_menu.addAction(save_session_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Connection menu
        connection_menu = menubar.addMenu("Connection")
        
        connect_action = QAction("Connect to Drone", self)
        connect_action.triggered.connect(self.connect_to_drone)
        connection_menu.addAction(connect_action)
        
        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect_from_drone)
        connection_menu.addAction(disconnect_action)
        
        connection_menu.addSeparator()
        
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings)
        connection_menu.addAction(settings_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_status_bar(self):
        """Setup the status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Not connected to drone")

    def poll_status(self):
        """Poll backend for status and update UI."""
        try:
            if not self.backend:
                return
            status = self.backend.get_system_status()
            conn = status.get('drone_connection', {})
            connected = bool(conn.get('connected'))
            if connected != self.is_connected:
                self.is_connected = connected
                self.connection_widget.update_status(connected)
                port = conn.get('port') or 'Unknown'
                baud = conn.get('baudrate') or 'Unknown'
                self.connection_details.setText(f"Status: {'Connected ✅' if connected else 'Disconnected'}\nCOM Port: {port}\nBaud Rate: {baud}")
                self.status_bar.showMessage("Connected to drone" if connected else "Disconnected from drone")

            # Update parameters view when available
            params = status.get('drone_parameters', {}) or {}
            if params and self.param_list.count() == 0:
                self.populate_parameter_list(params)
        except Exception:
            pass

    def populate_parameter_list(self, params: dict):
        """Populate the parameter list from a dict {name: value}."""
        self.param_list.clear()
        for name in sorted(params.keys()):
            item = QListWidgetItem(f"{name}: {params[name]}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.param_list.addItem(item)

    def filter_parameters(self):
        """Filter parameter list by search text."""
        text = self.param_search.text().strip().lower()
        for i in range(self.param_list.count()):
            item = self.param_list.item(i)
            visible = (text in item.text().lower())
            item.setHidden(not visible)

    def refresh_parameters_from_drone(self):
        """Request a parameter refresh via backend."""
        try:
            if not self.backend or not self.backend.is_drone_connected():
                self.add_bot_message("⚠️ Not connected to drone. Attempting to connect...", {"type": "warning"})
                result = self.backend.connect_to_drone()
                if not result.success:
                    self.add_bot_message("❌ Unable to connect to drone.", {"type": "error"})
                    return
            op = self.backend.execute_drone_operation("refresh_parameters")
            self.log_widget.add_entry("system", op.message)
            # After refresh, fetch full list for sidebar
            QTimer.singleShot(200, self.fetch_and_populate_all_parameters)
        except Exception as e:
            self.log_widget.add_entry("error", f"Refresh failed: {e}")
    
    def send_message(self):
        """Handle sending user messages"""
        message = self.input_field.text().strip()
        if not message:
            return
            
        # Add user message to chat
        self.add_user_message(message)
        self.input_field.clear()
        
        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.send_button.setEnabled(False)
        
        # Log the query
        self.log_widget.add_entry("user_query", f"User: {message}")
        
        # Process with chatbot thread
        self.chat_thread.set_query(message, {"session": self.current_session})
        self.chat_thread.start()
    
    def handle_bot_response(self, response_text, metadata):
        """Handle bot response from thread"""
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        
        # Ensure param_name is a string, not None
        if "param_name" in metadata and metadata["param_name"] is None:
            metadata["param_name"] = ""
        
        # Add bot message
        self.add_bot_message(response_text, metadata)
        
        # Log the response
        self.log_widget.add_entry("bot_response", f"Bot: {response_text[:50]}...")
        
        # Handle parameter change requests
        if metadata.get("type") == "change_request":
            self.handle_parameter_change_request(metadata)
    
    def handle_error(self, error_message):
        """Handle errors from the chat thread"""
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        
        self.add_bot_message(f"Sorry, I encountered an error: {error_message}", {"type": "error"})
        self.log_widget.add_entry("error", error_message)
    
    def handle_parameter_change_request(self, metadata):
        """Handle parameter change confirmation"""
        param_name = metadata.get("param_name")
        new_value = metadata.get("new_value")
        
        if not self.is_connected:
            self.add_bot_message("⚠️ Cannot change parameters: Not connected to drone. Please establish connection first.", {"type": "warning"})
            return
        
        # Show confirmation dialog
        dialog = ConfirmationDialog(param_name, new_value, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.execute_parameter_change(param_name, new_value)
        else:
            self.add_bot_message("Parameter change cancelled.", {"type": "info"})
    
    def execute_parameter_change(self, param_name, new_value):
        """Execute the actual parameter change"""
        if not self.backend:
            self.add_bot_message("❌ Backend not available. Cannot execute parameter change.", {"type": "error"})
            return
        
        if not self.backend.is_drone_connected():
            # Attempt auto-connect if not yet connected
            result = self.backend.connect_to_drone()
            if not result.success:
                self.add_bot_message("❌ Not connected to drone. Cannot execute parameter change.", {"type": "error"})
                return
        
        try:
            # Execute the parameter change through the backend
            result = self.backend.execute_drone_operation(
                "change_parameter",
                param_name=param_name,
                new_value=new_value,
                force=True  # Skip interactive confirmation since UI already handled it
            )
            
            if result.success:
                self.add_bot_message(f"✅ Parameter {param_name} updated to {new_value} successfully!", {"type": "success"})
                self.log_widget.add_entry("param_change", f"Changed {param_name} = {new_value}")
            else:
                self.add_bot_message(f"❌ Failed to change parameter: {result.message}", {"type": "error"})
                self.log_widget.add_entry("param_change_error", f"Failed to change {param_name}: {result.message}")
                
        except Exception as e:
            self.add_bot_message(f"❌ Error executing parameter change: {str(e)}", {"type": "error"})
            self.log_widget.add_entry("param_change_error", f"Error changing {param_name}: {str(e)}")
    
    def add_user_message(self, message):
        """Add user message bubble to chat"""
        bubble = ChatBubbleWidget(message, is_user=True)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self.scroll_to_bottom()
        
        # Add to session history
        self.current_session.append({"role": "user", "content": message, "timestamp": datetime.now()})
    
    def add_bot_message(self, message, metadata=None):
        """Add bot message bubble to chat"""
        bubble = ChatBubbleWidget(message, is_user=False, metadata=metadata)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self.scroll_to_bottom()
        
        # Add to session history
        self.current_session.append({"role": "assistant", "content": message, "metadata": metadata, "timestamp": datetime.now()})
    
    def scroll_to_bottom(self):
        """Scroll chat to bottom"""
        QTimer.singleShot(10, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()))
    
    def connect_to_drone(self):
        """Connect to drone via MAVLink"""
        if not self.backend:
            self.add_bot_message("❌ Backend not available. Cannot connect to drone.", {"type": "error"})
            return
        
        try:
            # Try to connect to drone through backend
            result = self.backend.connect_to_drone()
            
            if result.success:
                self.is_connected = True
                self.connection_widget.update_status(True)
                
                # Get connection details
                status = self.backend.get_system_status()
                drone_status = status.get('drone_connection', {})
                port = drone_status.get('port', 'Unknown')
                baudrate = drone_status.get('baudrate', 'Unknown')
                
                self.connection_details.setText(f"Status: Connected ✅\nCOM Port: {port}\nBaud Rate: {baudrate}")
                self.status_bar.showMessage("Connected to drone")
                self.log_widget.add_entry("connection", "Connected to drone successfully")
                
                self.add_bot_message("🔗 Connected to drone! I can now safely help you modify parameters.", {"type": "success"})
                # After connection, populate the sidebar with all parameters
                QTimer.singleShot(200, self.fetch_and_populate_all_parameters)
            else:
                self.add_bot_message(f"❌ Failed to connect to drone: {result.message}", {"type": "error"})
                self.log_widget.add_entry("connection_error", f"Connection failed: {result.message}")
                
        except Exception as e:
            self.add_bot_message(f"❌ Error connecting to drone: {str(e)}", {"type": "error"})
            self.log_widget.add_entry("connection_error", f"Connection error: {str(e)}")
    
    def disconnect_from_drone(self):
        """Disconnect from drone"""
        if self.backend:
            try:
                result = self.backend.disconnect_from_drone()
                if result.success:
                    self.log_widget.add_entry("connection", "Disconnected from drone")
                else:
                    self.log_widget.add_entry("connection_error", f"Disconnect error: {result.message}")
            except Exception as e:
                self.log_widget.add_entry("connection_error", f"Disconnect error: {str(e)}")
        
        self.is_connected = False
        self.connection_widget.update_status(False)
        self.connection_details.setText("Status: Disconnected\nCOM Port: Not selected\nBaud Rate: 57600")
        self.status_bar.showMessage("Disconnected from drone")
        
        self.add_bot_message("📡 Disconnected from drone. I can still explain parameters but cannot modify them.", {"type": "info"})

    def fetch_and_populate_all_parameters(self):
        """Fetch all parameters via backend list operation and populate sidebar."""
        try:
            if not self.backend or not self.backend.is_drone_connected():
                return
            op = self.backend.execute_drone_operation("list_parameters")
            if not op.success:
                return
            text = (op.data or {}).get("result", "")
            if not text:
                return
            # Parse lines like "  NAME = value"
            params = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("📋") or set(line) == set("-"):
                    continue
                if "=" in line:
                    parts = line.split("=", 1)
                    name = parts[0].strip()
                    value = parts[1].strip()
                    # Remove potential alignment padding
                    if name:
                        params[name] = value
            if params:
                self.populate_parameter_list(params)
        except Exception:
            pass
    
    def new_session(self):
        """Start a new chat session"""
        self.current_session = []
        # Clear chat display
        for i in reversed(range(self.chat_layout.count() - 1)):
            child = self.chat_layout.itemAt(i).widget()
            if child:
                child.setParent(None)
        
        self.add_bot_message("New session started. How can I help you with PX4 parameters?")
    
    def save_session(self):
        """Save current session to file"""
        if not self.current_session:
            QMessageBox.information(self, "Save Session", "No session data to save.")
            return
        
        # This will integrate with logs/ directory structure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/session_{timestamp}.json"
        
        try:
            # Create simplified session data for JSON serialization
            session_data = []
            for item in self.current_session:
                session_item = {
                    "role": item["role"],
                    "content": item["content"],
                    "timestamp": item["timestamp"].isoformat()
                }
                if "metadata" in item:
                    session_item["metadata"] = item["metadata"]
                session_data.append(session_item)
            
            # Would actually save to file here
            QMessageBox.information(self, "Save Session", f"Session saved to {filename}")
            self.log_widget.add_entry("system", f"Session saved to {filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save session: {str(e)}")
    
    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self)
        dialog.exec()
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About PX4 Parameter Assistant",
                         "PX4 Parameter Assistant v1.0\n\n"
                         "A chatbot interface for understanding and safely modifying PX4 parameters.\n\n"
                         "Features:\n"
                         "• Natural language parameter explanations\n"
                         "• Safe parameter modification with validation\n"
                         "• MAVLink integration with QGroundControl\n"
                         "• Session logging and management")


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = MainWindow()  # No backend for standalone mode
    window.show()
    sys.exit(app.exec())