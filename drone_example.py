#!/usr/bin/env python3
"""
Simple example of using the drone communication layer.

This example demonstrates:
1. Auto-detecting PX4 connection
2. Reading parameters
3. Setting parameters with verification
4. Error handling
"""

import sys
import time
import logging

# Add the project root to the path
sys.path.insert(0, '/home/vishnu/dev/proj/pegasus-1')

from drone import create_parameter_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main example function."""
    print("PX4 Drone Communication Example")
    print("=" * 40)
    
    # Create parameter manager (auto-detect port)
    print("Creating parameter manager...")
    manager = create_parameter_manager(baudrate=57600)
    
    # Add callbacks to monitor operations
    def on_operation(result):
        status = "SUCCESS" if result.success else "FAILED"
        print(f"  → {result.operation.value} {result.parameter_name}: {status}")
        if not result.success and result.error_message:
            print(f"    Error: {result.error_message}")
    
    def on_connection(connected):
        status = "CONNECTED" if connected else "DISCONNECTED"
        print(f"  → Connection: {status}")
    
    manager.add_operation_callback(on_operation)
    manager.add_connection_callback(on_connection)
    
    try:
        # Connect to PX4
        print("\nConnecting to PX4...")
        if not manager.connect():
            print("❌ Failed to connect to PX4")
            print("Make sure your PX4 is connected and powered on.")
            return
        
        print("✅ Connected to PX4 successfully!")
        
        # Wait a moment for parameters to load
        print("\nLoading parameters...")
        time.sleep(2)
        
        # Get parameter count
        params = manager.get_all_parameters()
        print(f"📊 Loaded {len(params)} parameters")
        
        # Example 1: Read a parameter
        print("\n📖 Reading SYS_AUTOSTART parameter...")
        result = manager.get_parameter("SYS_AUTOSTART")
        if result and result.success:
            print(f"   SYS_AUTOSTART = {result.value}")
        else:
            print("   ❌ Failed to read SYS_AUTOSTART")
            return
        
        # Example 2: Set a parameter (with verification)
        print("\n✏️  Setting SYS_AUTOSTART parameter...")
        current_value = result.value
        new_value = current_value + 1 if current_value < 1000 else current_value - 1
        
        print(f"   Changing from {current_value} to {new_value}")
        set_result = manager.set_parameter("SYS_AUTOSTART", new_value, verify=True)
        
        if set_result.success:
            print("   ✅ Parameter set successfully!")
            
            # Verify the change
            print("\n🔍 Verifying parameter change...")
            verify_result = manager.get_parameter("SYS_AUTOSTART")
            if verify_result and verify_result.success:
                print(f"   Verified: SYS_AUTOSTART = {verify_result.value}")
                
                if abs(verify_result.value - new_value) < 0.001:
                    print("   ✅ Parameter verification successful!")
                else:
                    print("   ⚠️  Parameter value doesn't match expected value")
            else:
                print("   ❌ Failed to verify parameter change")
        else:
            print(f"   ❌ Failed to set parameter: {set_result.error_message}")
        
        # Example 3: List some common parameters
        print("\n📋 Common PX4 parameters:")
        common_params = [
            "SYS_AUTOSTART", "RC_MAP_ROLL", "RC_MAP_PITCH", "RC_MAP_YAW",
            "MC_PITCHRATE_P", "MC_ROLLRATE_P", "MC_YAWRATE_P"
        ]
        
        for param_name in common_params:
            param_info = manager.get_parameter(param_name)
            if param_info and param_info.success:
                print(f"   {param_name}: {param_info.value}")
            else:
                print(f"   {param_name}: Not available")
        
        print("\n🎉 Example completed successfully!")
        print("💡 You can now check QGroundControl to see the parameter changes.")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Example interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        logger.exception("Error in example")
    finally:
        # Cleanup
        print("\n🔌 Disconnecting...")
        manager.disconnect()
        print("✅ Disconnected")


if __name__ == "__main__":
    main()
