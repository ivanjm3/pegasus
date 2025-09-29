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
            # Check for API key in environment or config
            api_key = os.getenv("OPENAI_API_KEY") or self.config.get('openai_api_key')
            
            if not api_key:
                logger.warning("No OpenAI API key found. Running in mock mode.")
                # Create backend with mock key for testing
                self.backend = create_backend("mock-api-key-for-testing", 
                                            llm_model=self.config.get('llm_model', 'gpt-4o-mini'),
                                            px4_params_path='data/px4_params.json')
                logger.info("Backend initialized in mock mode")
                return True
            
            # Convert config to backend format
            backend_config = {
                'openai_api_key': api_key,
                'llm_model': self.config.get('llm_model', 'gpt-4o-mini'),
                'px4_params_path': 'data/px4_params.json'
            }
            
            self.backend = create_backend(**backend_config)
            logger.info("Backend initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Backend setup failed: {e}")
            # Fallback to mock mode
            try:
                self.backend = create_backend("mock-api-key-for-testing", 
                                            llm_model=self.config.get('llm_model', 'gpt-4o-mini'),
                                            px4_params_path='data/px4_params.json')
                logger.info("Backend initialized in fallback mock mode")
                return True
            except Exception as fallback_error:
                logger.error(f"Fallback backend setup failed: {fallback_error}")
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
            # Auto-connect to drone on startup if backend is available
            try:
                if self.backend and hasattr(self.backend, 'connect_to_drone'):
                    result = self.backend.connect_to_drone()
                    if not result.success:
                        logger.warning(f"Auto-connect failed: {result.message}")
            except Exception as e:
                logger.warning(f"Auto-connect error: {e}")
            return True
            
        except Exception as e:
            logger.error(f"Main window setup failed: {e}")
            return False
    
    def show_startup_message(self):
        """Show startup message to user"""
        # Get system status
        if self.backend:
            status = self.backend.get_system_status()
            param_count = status.get('parameter_count', 0)
            drone_available = status.get('drone_connection', {}).get('drone_available', False)
            
            QMessageBox.information(
                self.main_window,
                "PX4 Parameter Assistant Ready",
                f"🚁 PX4 Parameter Assistant v1.0\n\n"
                f"✅ System Status:\n"
                f"• Parameters loaded: {param_count}\n"
                f"• Drone module: {'Available' if drone_available else 'Not available'}\n"
                f"• AI Mode: {'Full AI' if self.config.get('openai_api_key') or os.getenv('OPENAI_API_KEY') else 'Mock Mode'}\n\n"
                f"🎯 How to use:\n"
                f"1. Connect to your drone using the 'Connection' menu\n"
                f"2. Ask questions about parameters\n"
                f"3. Request parameter changes safely\n\n"
                f"💡 Example: 'What does MPC_XY_VEL_MAX control?'"
            )
        else:
            QMessageBox.warning(
                self.main_window,
                "Limited Functionality",
                "⚠️ Backend not available.\n\n"
                "The application will run with limited functionality.\n"
                "Please check the logs for more information."
            )
    
    def run(self) -> int:
        """Run the application"""
        print("🚁 PX4 Parameter Assistant")
        print("=" * 50)
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
            logger.warning("Backend setup failed, continuing with limited functionality")
        
        # Setup main window
        if not self.setup_main_window():
            logger.error("Failed to setup main window")
            return 1
        
        # Show startup message with system status
        self.show_startup_message()
        
        # Show main window
        self.main_window.show()
        
        # Log system status and show console info
        if self.backend:
            status = self.backend.get_system_status()
            param_count = status.get('parameter_count', 0)
            drone_available = status.get('drone_connection', {}).get('drone_available', False)
            ai_mode = "Full AI" if self.config.get('openai_api_key') or os.getenv('OPENAI_API_KEY') else "Mock Mode"
            
            print(f"✅ System Status:")
            print(f"   • Parameters loaded: {param_count}")
            print(f"   • Drone module: {'Available' if drone_available else 'Not available'}")
            print(f"   • AI Mode: {ai_mode}")
            print(f"   • LLM Model: {status.get('llm_model', 'Unknown')}")
            print()
            print("🎯 Ready to assist with PX4 parameter management!")
            print("   Use the UI to connect to your drone and start chatting.")
            print()
            
            logger.info(f"Application started successfully - Parameters: {param_count}, "
                       f"Drone available: {drone_available}")
        else:
            print("⚠️ Application started with limited functionality")
            print("   Check logs for more information.")
            print()
            logger.info("Application started with limited functionality")
        
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
