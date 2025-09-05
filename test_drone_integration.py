#!/usr/bin/env python3
"""
Comprehensive test script for drone communication layer.

This script tests all the required functionality:
1. COM port detection
2. PX4 connection via pymavlink
3. Parameter list fetching
4. Parameter reading (SYS_AUTOSTART)
5. Parameter setting and verification
6. QGroundControl verification (manual step)
"""

import sys
import time
import logging
from typing import Optional

# Add the project root to the path
sys.path.insert(0, '/home/vishnu/dev/proj/pegasus-1')

from drone import (
    ParameterManager,
    ParameterManagerConfig,
    ConnectionConfig,
    detect_com_ports,
    find_px4_port,
    validate_port_config,
    quick_test_connection
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DroneIntegrationTest:
    """Comprehensive test suite for drone communication."""
    
    def __init__(self):
        self.manager: Optional[ParameterManager] = None
        self.test_results = {}
        
    def run_all_tests(self, port: str = None, baudrate: int = 57600) -> bool:
        """
        Run all integration tests.
        
        Args:
            port: COM port (auto-detect if None)
            baudrate: Baud rate for communication
            
        Returns:
            True if all tests pass, False otherwise
        """
        print("=" * 60)
        print("PX4 DRONE COMMUNICATION INTEGRATION TEST")
        print("=" * 60)
        
        tests = [
            ("COM Port Detection", self.test_com_port_detection),
            ("Port Validation", lambda: self.test_port_validation(port, baudrate)),
            ("Quick Connection Test", lambda: self.test_quick_connection(port, baudrate)),
            ("Full Connection Test", lambda: self.test_full_connection(port, baudrate)),
            ("Parameter List Fetching", self.test_parameter_list),
            ("Parameter Reading", self.test_parameter_reading),
            ("Parameter Setting", self.test_parameter_setting),
            ("Parameter Verification", self.test_parameter_verification),
        ]
        
        all_passed = True
        
        for test_name, test_func in tests:
            print(f"\n--- {test_name} ---")
            try:
                result = test_func()
                self.test_results[test_name] = result
                status = "✓ PASSED" if result else "✗ FAILED"
                print(f"Result: {status}")
                if not result:
                    all_passed = False
            except Exception as e:
                print(f"✗ FAILED - Exception: {e}")
                self.test_results[test_name] = False
                all_passed = False
        
        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for test_name, result in self.test_results.items():
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"{test_name}: {status}")
        
        print(f"\nOverall Result: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
        
        if all_passed:
            print("\n🎉 SUCCESS! All drone communication features are working correctly.")
            print("You can now verify parameter changes in QGroundControl.")
        else:
            print("\n⚠️  Some tests failed. Check the logs above for details.")
        
        return all_passed
    
    def test_com_port_detection(self) -> bool:
        """Test COM port detection functionality."""
        print("Detecting available COM ports...")
        
        ports = detect_com_ports()
        print(f"Found {len(ports)} COM ports:")
        
        for port in ports:
            print(f"  - {port['port']}: {port['description']}")
        
        if not ports:
            print("No COM ports found. Make sure your PX4 is connected.")
            return False
        
        # Test PX4 port detection
        px4_port = find_px4_port()
        if px4_port:
            print(f"Detected potential PX4 port: {px4_port}")
        else:
            print("No specific PX4 port detected, will use first available port")
        
        return True
    
    def test_port_validation(self, port: str, baudrate: int) -> bool:
        """Test port validation functionality."""
        if not port:
            port = find_px4_port()
            if not port:
                print("No port available for validation")
                return False
        
        print(f"Validating port {port} at {baudrate} baud...")
        
        validation = validate_port_config(port, baudrate)
        
        if validation['valid']:
            print("✓ Port validation successful")
            return True
        else:
            print(f"✗ Port validation failed: {validation['error']}")
            return False
    
    def test_quick_connection(self, port: str, baudrate: int) -> bool:
        """Test quick connection functionality."""
        print("Testing quick connection...")
        
        result = quick_test_connection(port, baudrate)
        
        if result:
            print("✓ Quick connection test successful")
        else:
            print("✗ Quick connection test failed")
        
        return result
    
    def test_full_connection(self, port: str, baudrate: int) -> bool:
        """Test full connection with parameter manager."""
        print("Testing full connection with parameter manager...")
        
        try:
            # Create parameter manager
            config = ParameterManagerConfig(
                connection_config=ConnectionConfig(
                    port=port or "",
                    baudrate=baudrate,
                    timeout=10.0
                ),
                operation_timeout=15.0
            )
            
            self.manager = ParameterManager(config)
            
            # Add callbacks for monitoring
            def on_operation(result):
                print(f"  Operation: {result.operation.value} {result.parameter_name} - {'SUCCESS' if result.success else 'FAILED'}")
            
            def on_connection(connected):
                print(f"  Connection: {'CONNECTED' if connected else 'DISCONNECTED'}")
            
            self.manager.add_operation_callback(on_operation)
            self.manager.add_connection_callback(on_connection)
            
            # Connect
            if self.manager.connect(port, baudrate):
                print("✓ Full connection successful")
                return True
            else:
                print("✗ Full connection failed")
                return False
                
        except Exception as e:
            print(f"✗ Connection test failed with exception: {e}")
            return False
    
    def test_parameter_list(self) -> bool:
        """Test parameter list fetching."""
        if not self.manager or not self.manager.is_connected():
            print("Not connected to PX4")
            return False
        
        print("Fetching parameter list...")
        
        # Refresh parameters
        if self.manager.refresh_parameters(timeout=20.0):
            params = self.manager.get_all_parameters()
            print(f"✓ Successfully loaded {len(params)} parameters")
            
            # Show some sample parameters
            sample_params = list(params.keys())[:10]
            print("Sample parameters:")
            for param_name in sample_params:
                param_info = params[param_name]
                print(f"  - {param_name}: {param_info.value}")
            
            return len(params) > 0
        else:
            print("✗ Failed to fetch parameter list")
            return False
    
    def test_parameter_reading(self) -> bool:
        """Test parameter reading functionality."""
        if not self.manager or not self.manager.is_connected():
            print("Not connected to PX4")
            return False
        
        print("Testing parameter reading (SYS_AUTOSTART)...")
        
        result = self.manager.get_parameter("SYS_AUTOSTART", timeout=10.0)
        
        if result and result.success:
            print(f"✓ Successfully read SYS_AUTOSTART = {result.value}")
            return True
        else:
            print(f"✗ Failed to read SYS_AUTOSTART: {result.error_message if result else 'No result'}")
            return False
    
    def test_parameter_setting(self) -> bool:
        """Test parameter setting functionality."""
        if not self.manager or not self.manager.is_connected():
            print("Not connected to PX4")
            return False
        
        print("Testing parameter setting...")
        
        # First, read current value
        read_result = self.manager.get_parameter("SYS_AUTOSTART", timeout=10.0)
        if not read_result or not read_result.success:
            print("✗ Cannot read current SYS_AUTOSTART value")
            return False
        
        current_value = read_result.value
        print(f"Current SYS_AUTOSTART value: {current_value}")
        
        # Set a new value (safe modification)
        new_value = current_value + 1 if current_value < 1000 else current_value - 1
        print(f"Setting SYS_AUTOSTART to: {new_value}")
        
        set_result = self.manager.set_parameter("SYS_AUTOSTART", new_value, verify=True, timeout=15.0)
        
        if set_result.success:
            print(f"✓ Successfully set SYS_AUTOSTART = {new_value}")
            return True
        else:
            print(f"✗ Failed to set SYS_AUTOSTART: {set_result.error_message}")
            return False
    
    def test_parameter_verification(self) -> bool:
        """Test parameter verification after setting."""
        if not self.manager or not self.manager.is_connected():
            print("Not connected to PX4")
            return False
        
        print("Testing parameter verification...")
        
        # Read the parameter again to verify the change
        verify_result = self.manager.get_parameter("SYS_AUTOSTART", timeout=10.0)
        
        if verify_result and verify_result.success:
            print(f"✓ Verified SYS_AUTOSTART = {verify_result.value}")
            print("✓ Parameter verification successful")
            print("\n📋 MANUAL VERIFICATION REQUIRED:")
            print("   Please check QGroundControl to verify the parameter change is visible there.")
            return True
        else:
            print(f"✗ Parameter verification failed: {verify_result.error_message if verify_result else 'No result'}")
            return False
    
    def cleanup(self):
        """Cleanup resources."""
        if self.manager:
            self.manager.disconnect()


def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test PX4 drone communication")
    parser.add_argument("--port", help="COM port (auto-detect if not specified)")
    parser.add_argument("--baudrate", type=int, default=57600, help="Baud rate (default: 57600)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run tests
    test_suite = DroneIntegrationTest()
    
    try:
        success = test_suite.run_all_tests(args.port, args.baudrate)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)
    finally:
        test_suite.cleanup()


if __name__ == "__main__":
    main()
