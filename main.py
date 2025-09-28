#!/usr/bin/env python3
"""
Main entry point for PX4 Parameter Assistant

This application provides a chatbot interface for understanding and safely 
modifying PX4 drone parameters using natural language processing.
"""

import sys
import os
import logging
import yaml
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import create_backend, BackendOrchestrator
from ui.main_window import MainWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class PX4ParameterAssistant:
    """Main application class"""
    
    def __init__(self):
        self.app = None
        self.main_window = None
        self.backend = None
        self.config = None
    
    def load_config(self) -> Optional[Dict[str, Any]]:
        """Load configuration from settings.yaml"""
        try:
            config_path = "config/settings.yaml"
            
            if not os.path.exists(config_path):
                logger.warning(f"Config file not found: {config_path}")
                return self.create_default_config()
            
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            logger.info("Configuration loaded successfully")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self.create_default_config()
    
    def create_default_config(self) -> Dict[str, Any]:
        """Create default configuration"""
        default_config = {
            'openai_api_key': '',
            'llm_model': 'gpt-4o-mini',
            'temperature': 0.1,
            'default_com_port': 'COM3',
            'default_baud_rate': 57600,
            'log_level': 'INFO',
            'log_file': 'logs/chatbot_backend.log',
            'max_retries': 3,
            'timeout_seconds': 30
        }
        
        logger.info("Using default configuration")
        return default_config
    
    def setup_backend(self) -> bool:
        """Setup backend with configuration"""
        try:
            if not self.config.get('openai_api_key'):
                logger.warning("No OpenAI API key found. Running in mock mode.")
                self.backend = None
                return True
            
            # Convert config to backend format
            backend_config = {
                'openai_api_key': self.config['openai_api_key'],
                'llm_model': self.config.get('llm_model', 'gpt-4o-mini'),
                'px4_params_path': 'data/px4_params.json'
            }
            
            self.backend = create_backend(**backend_config)
            logger.info("Backend initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Backend setup failed: {e}")
            self.backend = None
            return False
    
    def setup_application(self) -> bool:
        """Setup PyQt application"""
        try:
            # Create application
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("PX4 Parameter Assistant")
            self.app.setApplicationVersion("1.0.0")
            self.app.setOrganizationName("PX4 Community")
            
            # Set application style
            self.app.setStyle('Fusion')
            
            logger.info("PyQt application initialized")
            return True
            
        except Exception as e:
            logger.error(f"Application setup failed: {e}")
            return False
    
    def setup_main_window(self) -> bool:
        """Setup main window"""
        try:
            self.main_window = MainWindow(backend=self.backend)
            logger.info("Main window initialized")
            return True
            
        except Exception as e:
            logger.error(f"Main window setup failed: {e}")
            return False
    
    def show_startup_message(self):
        """Show startup message to user"""
        if not self.backend:
            QMessageBox.information(
                self.main_window,
                "Mock Mode",
                "Running in mock mode.\n\n"
                "To use the full AI functionality:\n"
                "1. Add your OpenAI API key to config/settings.yaml\n"
                "2. Restart the application\n\n"
                "You can still test the UI functionality in mock mode."
            )
    
    def run(self) -> int:
        """Run the application"""
        logger.info("Starting PX4 Parameter Assistant...")
        
        # Load configuration
        self.config = self.load_config()
        if not self.config:
            logger.error("Failed to load configuration")
            return 1
        
        # Setup application
        if not self.setup_application():
            logger.error("Failed to setup application")
            return 1
        
        # Setup backend
        if not self.setup_backend():
            logger.warning("Backend setup failed, continuing in mock mode")
        
        # Setup main window
        if not self.setup_main_window():
            logger.error("Failed to setup main window")
            return 1
        
        # Show startup message if in mock mode
        if not self.backend:
            self.show_startup_message()
        
        # Show main window
        self.main_window.show()
        
        logger.info("Application started successfully")
        
        # Run event loop
        return self.app.exec()


def main():
    """Main entry point"""
    try:
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        # Create and run application
        app = PX4ParameterAssistant()
        return app.run()
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Application failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
