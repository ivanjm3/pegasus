#!/usr/bin/env python3
"""
PX4 Parameter Assistant - End-to-End Demo
This script demonstrates the complete functionality of the system.
"""

import sys
import os
import logging
from PyQt6.QtWidgets import QApplication

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import create_backend
from ui.main_window import MainWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Run the PX4 Parameter Assistant application"""
    print("🚁 PX4 Parameter Assistant - End-to-End Demo")
    print("=" * 60)
    print()
    
    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️  No OpenAI API key found in environment variables.")
        print("   The application will run in mock mode.")
        print("   To enable full AI functionality:")
        print("   1. Set OPENAI_API_KEY environment variable")
        print("   2. Or add your API key to config/settings.yaml")
        print()
        api_key = "mock-api-key-for-demo"
    
    try:
        # Create backend
        print("🔧 Initializing backend...")
        backend = create_backend(api_key, llm_model="gpt-4o-mini")
        print("✅ Backend initialized successfully")
        
        # Show system status
        status = backend.get_system_status()
        print(f"📊 System Status:")
        print(f"   • Parameters loaded: {status['parameter_count']}")
        print(f"   • LLM Model: {status['llm_model']}")
        print(f"   • Drone available: {status['drone_connection']['drone_available']}")
        print()
        
        # Create and show UI
        print("🖥️  Starting user interface...")
        app = QApplication(sys.argv)
        app.setApplicationName("PX4 Parameter Assistant")
        app.setApplicationVersion("1.0.0")
        
        # Create main window
        window = MainWindow(backend=backend)
        window.show()
        
        print("✅ Application started successfully!")
        print()
        print("🎯 How to use:")
        print("   1. Connect to your drone using the 'Connection' menu")
        print("   2. Ask questions about parameters (e.g., 'What is MPC_XY_VEL_MAX?')")
        print("   3. Request parameter changes (e.g., 'Set MPC_XY_VEL_MAX to 8')")
        print("   4. The AI will validate and safely execute your requests")
        print()
        print("🔗 Example queries:")
        print("   • 'What does EKF2_AID_MASK control?'")
        print("   • 'Set horizontal speed limit to 10 m/s'")
        print("   • 'Show me all battery parameters'")
        print("   • 'What's the safe range for MPC_ACC_HOR?'")
        print()
        print("⚠️  Safety Features:")
        print("   • All parameter changes require confirmation")
        print("   • Values are validated against safe ranges")
        print("   • Dangerous changes are blocked with warnings")
        print("   • Parameter backups are created automatically")
        print()
        print("🚀 Ready to assist with PX4 parameter management!")
        print("   Close the window or press Ctrl+C to exit.")
        print()
        
        # Run the application
        return app.exec()
        
    except KeyboardInterrupt:
        print("\n👋 Application interrupted by user")
        return 0
    except Exception as e:
        print(f"\n❌ Application failed: {e}")
        logger.error(f"Application error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
