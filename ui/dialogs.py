from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QLineEdit, QComboBox, QSpinBox,
                            QCheckBox, QTabWidget, QWidget, QFormLayout,
                            QTextEdit, QGroupBox, QSlider, QFrame,
                            QProgressBar, QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPalette, QColor
import serial.tools.list_ports
import json
import os


class ConfirmationDialog(QDialog):
    """Dialog for confirming parameter changes with safety warnings"""
    
    def __init__(self, param_name, new_value, old_value=None, param_info=None, parent=None):
        super().__init__(parent)
        self.param_name = param_name
        self.new_value = new_value
        self.old_value = old_value
        self.param_info = param_info or {}
        
        self.setWindowTitle("Confirm Parameter Change")
        self.setFixedSize(500, 400)
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
        """Initialize confirmation dialog UI"""
        layout = QVBoxLayout(self)
        
        # Warning header
        warning_frame = QFrame()
        warning_frame.setStyleSheet("""
            QFrame {
                background-color: #fff3cd;
                border: 2px solid #ffeaa7;
                border-radius: 8px;
                padding: 10px;
                margin: 5px;
            }
        """)
        warning_layout = QHBoxLayout(warning_frame)
        
        warning_icon = QLabel("⚠️")
        warning_icon.setFont(QFont("Arial", 20))
        warning_text = QLabel("Parameter Change Confirmation")
        warning_text.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        warning_text.setStyleSheet("color: #856404;")
        
        warning_layout.addWidget(warning_icon)
        warning_layout.addWidget(warning_text)
        warning_layout.addStretch()
        
        # Parameter details
        details_group = QGroupBox("Change Details")
        details_layout = QFormLayout(details_group)
        
        # Parameter name
        param_label = QLabel(self.param_name)
        param_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        param_label.setStyleSheet("color: #2c3e50;")
        details_layout.addRow("Parameter:", param_label)
        
        # Current value
        if self.old_value is not None:
            current_label = QLabel(str(self.old_value))
            current_label.setStyleSheet("color: #e74c3c;")
            details_layout.addRow("Current Value:", current_label)
        
        # New value
        new_label = QLabel(str(self.new_value))
        new_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        new_label.setStyleSheet("color: #27ae60;")
        details_layout.addRow("New Value:", new_label)
        
        # Parameter description
        if self.param_info.get('description'):
            desc_text = QTextEdit()
            desc_text.setPlainText(self.param_info['description'])
            desc_text.setMaximumHeight(80)
            desc_text.setReadOnly(True)
            desc_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6;")
            details_layout.addRow("Description:", desc_text)
        
        # Value range info
        if self.param_info.get('min') is not None or self.param_info.get('max') is not None:
            min_val = self.param_info.get('min', 'N/A')
            max_val = self.param_info.get('max', 'N/A')
            range_label = QLabel(f"{min_val} to {max_val}")
            range_label.setStyleSheet("color: #6c757d;")
            details_layout.addRow("Valid Range:", range_label)
        
        # Unit info
        if self.param_info.get('unit'):
            unit_label = QLabel(self.param_info['unit'])
            unit_label.setStyleSheet("color: #6c757d;")
            details_layout.addRow("Unit:", unit_label)
        
        # Safety warnings
        safety_group = QGroupBox("Safety Information")
        safety_layout = QVBoxLayout(safety_group)
        
        safety_warnings = [
            "🔒 This will modify drone parameters permanently",
            "✋ Ensure drone is disarmed before making changes",
            "📡 Changes will be visible in QGroundControl",
            "💾 Consider backing up current parameters first"
        ]
        
        for warning in safety_warnings:
            warning_label = QLabel(warning)
            warning_label.setStyleSheet("color: #495057; padding: 2px;")
            safety_layout.addWidget(warning_label)
        
        # Backup option
        self.backup_checkbox = QCheckBox("Create parameter backup before change")
        self.backup_checkbox.setChecked(True)
        self.backup_checkbox.setStyleSheet("font-weight: bold; color: #17a2b8;")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.confirm_button = QPushButton("Confirm Change")
        self.confirm_button.clicked.connect(self.accept)
        self.confirm_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.confirm_button)
        
        # Add all components to main layout
        layout.addWidget(warning_frame)
        layout.addWidget(details_group)
        layout.addWidget(safety_group)
        layout.addWidget(self.backup_checkbox)
        layout.addLayout(button_layout)
    
    def should_backup(self):
        """Return whether user wants to backup parameters"""
        return self.backup_checkbox.isChecked()


class SettingsDialog(QDialog):
    """Settings dialog for configuring connection and preferences"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(600, 500)
        self.setModal(True)
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        """Initialize settings dialog UI"""
        layout = QVBoxLayout(self)
        
        # Tab widget for different setting categories
        tab_widget = QTabWidget()
        
        # Connection settings tab
        connection_tab = self.create_connection_tab()
        tab_widget.addTab(connection_tab, "Connection")
        
        # LLM settings tab
        llm_tab = self.create_llm_tab()
        tab_widget.addTab(llm_tab, "AI Assistant")
        
        # Interface settings tab
        interface_tab = self.create_interface_tab()
        tab_widget.addTab(interface_tab, "Interface")
        
        # Advanced settings tab
        advanced_tab = self.create_advanced_tab()
        tab_widget.addTab(advanced_tab, "Advanced")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        restore_defaults_button = QPushButton("Restore Defaults")
        restore_defaults_button.clicked.connect(self.restore_defaults)
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(restore_defaults_button)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)
        
        layout.addWidget(tab_widget)
        layout.addLayout(button_layout)
    
    def create_connection_tab(self):
        """Create connection settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Serial connection group
        serial_group = QGroupBox("Serial Connection")
        serial_layout = QFormLayout(serial_group)
        
        # COM port selection
        self.port_combo = QComboBox()
        self.refresh_ports()
        
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_ports)
        refresh_button.setMaximumWidth(80)
        
        port_layout = QHBoxLayout()
        port_layout.addWidget(self.port_combo)
        port_layout.addWidget(refresh_button)
        
        serial_layout.addRow("COM Port:", port_layout)
        
        # Baud rate
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "921600"])
        self.baud_combo.setCurrentText("57600")
        serial_layout.addRow("Baud Rate:", self.baud_combo)
        
        # Connection timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(5)
        self.timeout_spin.setSuffix(" seconds")
        serial_layout.addRow("Timeout:", self.timeout_spin)
        
        # Auto-connect option
        self.auto_connect_check = QCheckBox("Auto-connect on startup")
        serial_layout.addRow("", self.auto_connect_check)
        
        # MAVLink settings group
        mavlink_group = QGroupBox("MAVLink Settings")
        mavlink_layout = QFormLayout(mavlink_group)
        
        # System ID
        self.system_id_spin = QSpinBox()
        self.system_id_spin.setRange(1, 255)
        self.system_id_spin.setValue(255)
        mavlink_layout.addRow("System ID:", self.system_id_spin)
        
        # Component ID
        self.component_id_spin = QSpinBox()
        self.component_id_spin.setRange(1, 255)
        self.component_id_spin.setValue(190)
        mavlink_layout.addRow("Component ID:", self.component_id_spin)
        
        layout.addWidget(serial_group)
        layout.addWidget(mavlink_group)
        layout.addStretch()
        
        return widget
    
    def create_llm_tab(self):
        """Create LLM settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # API settings group
        api_group = QGroupBox("OpenAI API Settings")
        api_layout = QFormLayout(api_group)
        
        # API key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        api_layout.addRow("API Key:", self.api_key_edit)
        
        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "gpt-4o-mini",
            "gpt-4o", 
            "gpt-3.5-turbo",
            "gpt-4-turbo"
        ])
        api_layout.addRow("Model:", self.model_combo)
        
        # Temperature
        self.temperature_slider = QSlider(Qt.Orientation.Horizontal)
        self.temperature_slider.setRange(0, 100)
        self.temperature_slider.setValue(30)
        self.temp_label = QLabel("0.3")
        self.temperature_slider.valueChanged.connect(
            lambda v: self.temp_label.setText(f"{v/100:.1f}")
        )
        
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(self.temperature_slider)
        temp_layout.addWidget(self.temp_label)
        api_layout.addRow("Temperature:", temp_layout)
        
        # Max tokens
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 4000)
        self.max_tokens_spin.setValue(1000)
        api_layout.addRow("Max Tokens:", self.max_tokens_spin)
        
        # Response settings group
        response_group = QGroupBox("Response Settings")
        response_layout = QFormLayout(response_group)
        
        # Confirmation requirement
        self.require_confirmation_check = QCheckBox("Always require confirmation for parameter changes")
        self.require_confirmation_check.setChecked(True)
        response_layout.addRow("", self.require_confirmation_check)
        
        # Explanation detail level
        self.detail_combo = QComboBox()
        self.detail_combo.addItems(["Basic", "Detailed", "Technical"])
        self.detail_combo.setCurrentText("Detailed")
        response_layout.addRow("Explanation Detail:", self.detail_combo)
        
        layout.addWidget(api_group)
        layout.addWidget(response_group)
        layout.addStretch()
        
        return widget
    
    def create_interface_tab(self):
        """Create interface settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "Auto"])
        appearance_layout.addRow("Theme:", self.theme_combo)
        
        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 20)
        self.font_size_spin.setValue(11)
        appearance_layout.addRow("Font Size:", self.font_size_spin)
        
        # Chat settings group
        chat_group = QGroupBox("Chat Interface")
        chat_layout = QFormLayout(chat_group)
        
        # Message animations
        self.animations_check = QCheckBox("Enable message animations")
        self.animations_check.setChecked(True)
        chat_layout.addRow("", self.animations_check)
        
        # Timestamps
        self.timestamps_check = QCheckBox("Show timestamps on messages")
        self.timestamps_check.setChecked(True)
        chat_layout.addRow("", self.timestamps_check)
        
        # Sound notifications
        self.sounds_check = QCheckBox("Enable sound notifications")
        chat_layout.addRow("", self.sounds_check)
        
        # Logging group
        logging_group = QGroupBox("Logging")
        logging_layout = QFormLayout(logging_group)
        
        # Enable logging
        self.logging_check = QCheckBox("Enable session logging")
        self.logging_check.setChecked(True)
        logging_layout.addRow("", self.logging_check)
        
        # Auto-save sessions
        self.autosave_check = QCheckBox("Auto-save sessions")
        self.autosave_check.setChecked(True)
        logging_layout.addRow("", self.autosave_check)
        
        # Log retention days
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 365)
        self.retention_spin.setValue(30)
        self.retention_spin.setSuffix(" days")
        logging_layout.addRow("Keep logs for:", self.retention_spin)
        
        layout.addWidget(appearance_group)
        layout.addWidget(chat_group)
        layout.addWidget(logging_group)
        layout.addStretch()
        
        return widget
    
    def create_advanced_tab(self):
        """Create advanced settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Safety group
        safety_group = QGroupBox("Safety Settings")
        safety_layout = QFormLayout(safety_group)
        
        # Parameter backup
        self.auto_backup_check = QCheckBox("Automatically backup parameters before changes")
        self.auto_backup_check.setChecked(True)
        safety_layout.addRow("", self.auto_backup_check)
        
        # Validation strictness
        self.validation_combo = QComboBox()
        self.validation_combo.addItems(["Strict", "Normal", "Permissive"])
        self.validation_combo.setCurrentText("Normal")
        safety_layout.addRow("Validation Level:", self.validation_combo)
        
        # Performance group
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout(perf_group)
        
        # Request timeout
        self.request_timeout_spin = QSpinBox()
        self.request_timeout_spin.setRange(5, 60)
        self.request_timeout_spin.setValue(30)
        self.request_timeout_spin.setSuffix(" seconds")
        perf_layout.addRow("Request Timeout:", self.request_timeout_spin)
        
        # Cache responses
        self.cache_check = QCheckBox("Cache parameter information")
        self.cache_check.setChecked(True)
        perf_layout.addRow("", self.cache_check)
        
        # Developer group
        dev_group = QGroupBox("Developer")
        dev_layout = QFormLayout(dev_group)
        
        # Debug mode
        self.debug_check = QCheckBox("Enable debug logging")
        dev_layout.addRow("", self.debug_check)
        
        # Show raw responses
        self.raw_responses_check = QCheckBox("Show raw LLM responses in logs")
        dev_layout.addRow("", self.raw_responses_check)
        
        layout.addWidget(safety_group)
        layout.addWidget(perf_group)
        layout.addWidget(dev_group)
        layout.addStretch()
        
        return widget
    
    def refresh_ports(self):
        """Refresh available COM ports"""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            display_text = f"{port.device} - {port.description}"
            self.port_combo.addItem(display_text, port.device)
        
        if not ports:
            self.port_combo.addItem("No ports available", None)
    
    def load_settings(self):
        """Load settings from config file"""
        try:
            settings_path = "config/settings.json"
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                
                # Load connection settings
                self.baud_combo.setCurrentText(str(settings.get("baud_rate", 57600)))
                self.timeout_spin.setValue(settings.get("timeout", 5))
                self.auto_connect_check.setChecked(settings.get("auto_connect", False))
                
                # Load LLM settings
                self.api_key_edit.setText(settings.get("openai_api_key", ""))
                self.model_combo.setCurrentText(settings.get("llm_model", "gpt-4o-mini"))
                self.temperature_slider.setValue(int(settings.get("temperature", 0.3) * 100))
                self.max_tokens_spin.setValue(settings.get("max_tokens", 1000))
                
                # Load interface settings
                self.font_size_spin.setValue(settings.get("font_size", 11))
                self.animations_check.setChecked(settings.get("animations", True))
                self.logging_check.setChecked(settings.get("logging_enabled", True))
                
        except Exception as e:
            print(f"Failed to load settings: {e}")
    
    def save_settings(self):
        """Save settings to config file"""
        try:
            settings = {
                # Connection settings
                "com_port": self.port_combo.currentData(),
                "baud_rate": int(self.baud_combo.currentText()),
                "timeout": self.timeout_spin.value(),
                "auto_connect": self.auto_connect_check.isChecked(),
                "system_id": self.system_id_spin.value(),
                "component_id": self.component_id_spin.value(),
                
                # LLM settings
                "openai_api_key": self.api_key_edit.text(),
                "llm_model": self.model_combo.currentText(),
                "temperature": self.temperature_slider.value() / 100.0,
                "max_tokens": self.max_tokens_spin.value(),
                "require_confirmation": self.require_confirmation_check.isChecked(),
                "explanation_detail": self.detail_combo.currentText(),
                
                # Interface settings
                "theme": self.theme_combo.currentText(),
                "font_size": self.font_size_spin.value(),
                "animations": self.animations_check.isChecked(),
                "timestamps": self.timestamps_check.isChecked(),
                "sounds": self.sounds_check.isChecked(),
                "logging_enabled": self.logging_check.isChecked(),
                "autosave_sessions": self.autosave_check.isChecked(),
                "log_retention_days": self.retention_spin.value(),
                
                # Advanced settings
                "auto_backup": self.auto_backup_check.isChecked(),
                "validation_level": self.validation_combo.currentText(),
                "request_timeout": self.request_timeout_spin.value(),
                "cache_enabled": self.cache_check.isChecked(),
                "debug_mode": self.debug_check.isChecked(),
                "show_raw_responses": self.raw_responses_check.isChecked()
            }
            
            os.makedirs("config", exist_ok=True)
            with open("config/settings.json", 'w') as f:
                json.dump(settings, f, indent=2)
            
            QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save settings: {str(e)}")
    
    def restore_defaults(self):
        """Restore all settings to defaults"""
        reply = QMessageBox.question(self, "Restore Defaults", 
                                   "Are you sure you want to restore all settings to their default values?")
        if reply == QMessageBox.StandardButton.Yes:
            # Reset all widgets to default values
            self.baud_combo.setCurrentText("57600")
            self.timeout_spin.setValue(5)
            self.auto_connect_check.setChecked(False)
            self.system_id_spin.setValue(255)
            self.component_id_spin.setValue(190)
            
            self.api_key_edit.clear()
            self.model_combo.setCurrentText("gpt-4o-mini")
            self.temperature_slider.setValue(30)
            self.max_tokens_spin.setValue(1000)
            self.require_confirmation_check.setChecked(True)
            
            self.theme_combo.setCurrentText("Light")
            self.font_size_spin.setValue(11)
            self.animations_check.setChecked(True)
            self.timestamps_check.setChecked(True)
            self.sounds_check.setChecked(False)
            self.logging_check.setChecked(True)


class ConnectionDialog(QDialog):
    """Dialog for establishing drone connection"""
    
    connection_requested = pyqtSignal(str, int, dict)  # port, baud, options
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Drone")
        self.setFixedSize(400, 300)
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
        """Initialize connection dialog UI"""
        layout = QVBoxLayout(self)
        
        # Status display
        self.status_label = QLabel("Select connection parameters:")
        self.status_label.setStyleSheet("font-weight: bold; color: #495057;")
        
        # Connection form
        form_group = QGroupBox("Connection Settings")
        form_layout = QFormLayout(form_group)
        
        # COM port
        self.port_combo = QComboBox()
        self.refresh_ports()
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setMaximumWidth(30)
        refresh_btn.clicked.connect(self.refresh_ports)
        refresh_btn.setToolTip("Refresh ports")
        
        port_layout = QHBoxLayout()
        port_layout.addWidget(self.port_combo)
        port_layout.addWidget(refresh_btn)
        
        form_layout.addRow("Port:", port_layout)
        
        # Baud rate
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["57600", "115200", "921600"])
        form_layout.addRow("Baud Rate:", self.baud_combo)
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.attempt_connection)
        self.connect_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.connect_button)
        
        layout.addWidget(self.status_label)
        layout.addWidget(form_group)
        layout.addWidget(self.progress)
        layout.addLayout(button_layout)
    
    def refresh_ports(self):
        """Refresh available ports"""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        
        for port in ports:
            self.port_combo.addItem(f"{port.device} - {port.description}", port.device)
        
        if not ports:
            self.port_combo.addItem("No ports found", None)
            self.connect_button.setEnabled(False)
        else:
            self.connect_button.setEnabled(True)
    
    def attempt_connection(self):
        """Attempt to connect with selected parameters"""
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No Port", "Please select a valid port.")
            return
        
        baud = int(self.baud_combo.currentText())
        
        # Show progress
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # Indeterminate
        self.connect_button.setEnabled(False)
        self.status_label.setText("Connecting...")
        
        # Emit connection request
        options = {"timeout": 5}
        self.connection_requested.emit(port, baud, options)
        
        # Simulate connection attempt (replace with actual logic)
        QTimer.singleShot(2000, self.connection_result)
    
    def connection_result(self, success=True):
        """Handle connection result"""
        self.progress.setVisible(False)
        self.connect_button.setEnabled(True)
        
        if success:
            self.status_label.setText("Connected successfully!")
            self.status_label.setStyleSheet("font-weight: bold; color: #28a745;")
            QTimer.singleShot(1000, self.accept)
        else:
            self.status_label.setText("Connection failed. Please try again.")
            self.status_label.setStyleSheet("font-weight: bold; color: #dc3545;")


class AboutDialog(QDialog):
    """About dialog with application information"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About PX4 Parameter Assistant")
        self.setFixedSize(500, 400)
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
        """Initialize about dialog UI"""
        layout = QVBoxLayout(self)
        
        # App icon and title
        header_layout = QHBoxLayout()
        
        # App icon (placeholder)
        icon_label = QLabel("🚁")
        icon_label.setFont(QFont("Arial", 48))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title_layout = QVBoxLayout()
        title_label = QLabel("PX4 Parameter Assistant")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        
        version_label = QLabel("Version 1.0.0")
        version_label.setStyleSheet("color: #6c757d;")
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(version_label)
        
        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_layout)
        header_layout.addStretch()
        
        # Description
        desc_text = QTextEdit()
        desc_text.setReadOnly(True)
        desc_text.setMaximumHeight(120)
        desc_text.setPlainText(
            "A chatbot interface for understanding and safely modifying PX4 parameters. "
            "This application uses natural language processing to help drone operators "
            "interact with complex parameter systems through conversational queries."
        )
        desc_text.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6;")
        
        # Features list
        features_group = QGroupBox("Features")
        features_layout = QVBoxLayout(features_group)
        
        features = [
            "Natural language parameter explanations",
            "Safe parameter modification with validation",
            "MAVLink integration with QGroundControl",
            "Session logging and management",
            "Real-time connection status",
            "Parameter backup and restore"
        ]
        
        for feature in features:
            feature_label = QLabel(f"• {feature}")
            features_layout.addWidget(feature_label)
        
        # Credits
        credits_group = QGroupBox("Credits")
        credits_layout = QVBoxLayout(credits_group)
        
        credits_text = QLabel(
            "Built with PyQt6, OpenAI API, and PyMAVLink\n"
            "Designed for PX4 autopilot systems\n"
            "© 2024 - Open Source Project"
        )
        credits_text.setStyleSheet("color: #6c757d;")
        credits_layout.addWidget(credits_text)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(header_layout)
        layout.addWidget(desc_text)
        layout.addWidget(features_group)
        layout.addWidget(credits_group)
        layout.addLayout(button_layout)


class ParameterBackupDialog(QDialog):
    """Dialog for backing up and restoring parameters"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parameter Backup & Restore")
        self.setFixedSize(500, 350)
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
        """Initialize backup dialog UI"""
        layout = QVBoxLayout(self)
        
        # Instructions
        info_label = QLabel("Manage parameter backups for safety and recovery.")
        info_label.setStyleSheet("font-weight: bold; color: #495057; margin-bottom: 10px;")
        
        # Backup section
        backup_group = QGroupBox("Create Backup")
        backup_layout = QVBoxLayout(backup_group)
        
        backup_desc = QLabel("Create a backup of current drone parameters:")
        backup_layout.addWidget(backup_desc)
        
        backup_name_layout = QHBoxLayout()
        backup_name_layout.addWidget(QLabel("Backup Name:"))
        self.backup_name_edit = QLineEdit()
        self.backup_name_edit.setText(f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        backup_name_layout.addWidget(self.backup_name_edit)
        
        create_backup_btn = QPushButton("Create Backup")
        create_backup_btn.clicked.connect(self.create_backup)
        create_backup_btn.setStyleSheet("background-color: #28a745; color: white; padding: 8px 16px; border-radius: 4px;")
        
        backup_layout.addLayout(backup_name_layout)
        backup_layout.addWidget(create_backup_btn)
        
        # Restore section
        restore_group = QGroupBox("Restore from Backup")
        restore_layout = QVBoxLayout(restore_group)
        
        restore_desc = QLabel("Select a backup to restore:")
        restore_layout.addWidget(restore_desc)
        
        # Backup list (placeholder - would be populated from actual files)
        self.backup_list = QComboBox()
        self.populate_backup_list()
        restore_layout.addWidget(self.backup_list)
        
        restore_buttons = QHBoxLayout()
        
        refresh_list_btn = QPushButton("Refresh")
        refresh_list_btn.clicked.connect(self.populate_backup_list)
        
        restore_btn = QPushButton("Restore Selected")
        restore_btn.clicked.connect(self.restore_backup)
        restore_btn.setStyleSheet("background-color: #ffc107; color: #212529; padding: 8px 16px; border-radius: 4px;")
        
        delete_backup_btn = QPushButton("Delete")
        delete_backup_btn.clicked.connect(self.delete_backup)
        delete_backup_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 8px 16px; border-radius: 4px;")
        
        restore_buttons.addWidget(refresh_list_btn)
        restore_buttons.addStretch()
        restore_buttons.addWidget(restore_btn)
        restore_buttons.addWidget(delete_backup_btn)
        
        restore_layout.addLayout(restore_buttons)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_btn)
        
        layout.addWidget(info_label)
        layout.addWidget(backup_group)
        layout.addWidget(restore_group)
        layout.addLayout(close_layout)
    
    def populate_backup_list(self):
        """Populate the backup list from available files"""
        self.backup_list.clear()
        
        # Mock backup files (replace with actual file scanning)
        mock_backups = [
            "backup_20241201_143022.json",
            "backup_20241130_091544.json", 
            "backup_20241129_165433.json"
        ]
        
        for backup in mock_backups:
            self.backup_list.addItem(backup)
        
        if not mock_backups:
            self.backup_list.addItem("No backups available")
    
    def create_backup(self):
        """Create a parameter backup"""
        backup_name = self.backup_name_edit.text().strip()
        if not backup_name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a backup name.")
            return
        
        # Mock backup creation
        QMessageBox.information(self, "Backup Created", f"Backup '{backup_name}' created successfully!")
        self.populate_backup_list()
    
    def restore_backup(self):
        """Restore from selected backup"""
        selected_backup = self.backup_list.currentText()
        if selected_backup == "No backups available":
            return
        
        reply = QMessageBox.question(
            self, "Confirm Restore",
            f"Are you sure you want to restore from '{selected_backup}'?\n"
            "This will overwrite current parameters!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "Restore Complete", f"Parameters restored from '{selected_backup}'")
    
    def delete_backup(self):
        """Delete selected backup"""
        selected_backup = self.backup_list.currentText()
        if selected_backup == "No backups available":
            return
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete backup '{selected_backup}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "Backup Deleted", f"Backup '{selected_backup}' deleted.")
            self.populate_backup_list()


# Import datetime for backup functionality
from datetime import datetime

# Export all dialog classes
__all__ = [
    'ConfirmationDialog',
    'SettingsDialog', 
    'ConnectionDialog',
    'AboutDialog',
    'ParameterBackupDialog'
]