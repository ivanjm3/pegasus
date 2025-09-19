"""
MAVLink handler for PX4 drone communication.
Handles connection, parameter operations, and message processing.
"""

import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

try:
    from pymavlink import mavutil
    from pymavlink.dialects.v20 import common as mavlink2
except ImportError as e:
    logging.error(f"Failed to import pymavlink: {e}")
    raise

# Import from utils.py in same directory
try:
    from utils import validate_port_config, find_px4_port
except ImportError:
    print("Warning: Could not import utils.py - using fallback functions")
    def validate_port_config(port, baudrate):
        return {'valid': True, 'error': None}
    
    def find_px4_port():
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            if 'Legacy FMU' in port.description or 'PX4' in port.description:
                return port.device
        return "COM4"  # fallback

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ParameterInfo:
    """Parameter information structure."""
    name: str
    value: float
    param_type: int
    param_count: int
    param_index: int


@dataclass
class ConnectionConfig:
    """Connection configuration."""
    port: str
    baudrate: int = 115200
    timeout: float = 5.0
    retries: int = 3
    heartbeat_timeout: float = 10.0


class MAVLinkHandler:
    """
    MAVLink handler for PX4 communication.
    """
    
    def __init__(self, config: Optional[ConnectionConfig] = None):
        """Initialize MAVLink handler."""
        self.config = config or ConnectionConfig(port="", baudrate=115200)
        self.connection = None
        self.state = ConnectionState.DISCONNECTED
        self.parameters: Dict[str, ParameterInfo] = {}
        self.parameter_callbacks: Dict[str, List[Callable]] = {}
        self.ack_callbacks: Dict[str, List[Callable]] = {}
        self._last_heartbeat = 0
        
    def connect(self, port: Optional[str] = None, baudrate: Optional[int] = None) -> bool:
        """Connect to PX4 via MAVLink."""
        try:
            self.state = ConnectionState.CONNECTING
            
            # Get port from utils.py if not provided
            if port is None:
                port = find_px4_port()
                if not port:
                    raise ValueError("No port found")
            
            if baudrate is None:
                baudrate = self.config.baudrate
            
            logger.info(f"Connecting to {port} at {baudrate} baud...")
            
            # Try different connection methods for Windows COM ports
            connection_attempts = [
                port,  # Just "COM4"
                f"COM{port.replace('COM', '')}",  # Ensure COM prefix
                f"{port}:{baudrate}",  # With baudrate
            ]
            
            for attempt_num in range(self.config.retries):
                for conn_str in connection_attempts:
                    try:
                        logger.info(f"Attempt {attempt_num + 1}: Trying connection string '{conn_str}'")
                        
                        # Create MAVLink connection
                        self.connection = mavutil.mavlink_connection(
                            conn_str,
                            baud=baudrate,
                            timeout=self.config.timeout
                        )
                        
                        # Wait for heartbeat
                        if self._wait_for_heartbeat():
                            self.state = ConnectionState.CONNECTED
                            self.config.port = port
                            self.config.baudrate = baudrate
                            logger.info(f"✓ Successfully connected to {port}")
                            return True
                        else:
                            logger.warning(f"No heartbeat received for '{conn_str}'")
                            if self.connection:
                                self.connection.close()
                            
                    except Exception as e:
                        logger.debug(f"Connection string '{conn_str}' failed: {e}")
                        continue
                
                # Wait before retrying
                if attempt_num < self.config.retries - 1:
                    time.sleep(1)
            
            raise Exception("All connection attempts failed")
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.state = ConnectionState.ERROR
            return False
    
    def disconnect(self) -> None:
        """Disconnect from PX4."""
        try:
            if self.connection:
                self.connection.close()
                logger.info("Disconnected from PX4")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
        finally:
            self.state = ConnectionState.DISCONNECTED
            self.connection = None
    
    def is_connected(self) -> bool:
        """Check if connected to PX4."""
        return self.state == ConnectionState.CONNECTED and self.connection is not None
    
    def request_parameter_list(self) -> bool:
        """Request complete parameter list from PX4."""
        if not self.is_connected():
            logger.error("Not connected to PX4")
            return False
        
        try:
            logger.info("Requesting parameter list...")
            self.connection.mav.param_request_list_send(
                self.connection.target_system,
                self.connection.target_component
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to request parameter list: {e}")
            return False
    
    def request_parameter(self, param_name: str) -> bool:
        """Request specific parameter from PX4."""
        if not self.is_connected():
            logger.error("Not connected to PX4")
            return False
        
        try:
            logger.info(f"Requesting parameter: {param_name}")
            # Ensure proper parameter name encoding
            param_name_bytes = param_name.encode('utf-8')[:16].ljust(16, b'\x00')
            
            self.connection.mav.param_request_read_send(
                self.connection.target_system,
                self.connection.target_component,
                param_name_bytes,
                -1
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to request parameter {param_name}: {e}")
            return False
    
    def set_parameter(self, param_name: str, value: float, param_type: int = mavlink2.MAV_PARAM_TYPE_REAL32) -> bool:
        """Set parameter value on PX4."""
        if not self.is_connected():
            logger.error("Not connected to PX4")
            return False
        
        try:
            logger.info(f"Setting parameter {param_name} = {value}")
            # Ensure proper parameter name encoding
            param_name_bytes = param_name.encode('utf-8')[:16].ljust(16, b'\x00')
            
            self.connection.mav.param_set_send(
                self.connection.target_system,
                self.connection.target_component,
                param_name_bytes,
                value,
                param_type
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to set parameter {param_name}: {e}")
            return False
    
    def get_parameter(self, param_name: str) -> Optional[ParameterInfo]:
        """Get parameter from cache."""
        return self.parameters.get(param_name)
    
    def get_all_parameters(self) -> Dict[str, ParameterInfo]:
        """Get all cached parameters."""
        return self.parameters.copy()
    
    def add_parameter_callback(self, param_name: str, callback: Callable[[ParameterInfo], None]) -> None:
        """Add callback for parameter updates."""
        if param_name not in self.parameter_callbacks:
            self.parameter_callbacks[param_name] = []
        self.parameter_callbacks[param_name].append(callback)
    
    def process_messages(self, timeout: float = 0.1) -> int:
        """Process incoming MAVLink messages."""
        if not self.is_connected():
            return 0
        
        messages_processed = 0
        
        try:
            while True:
                msg = self.connection.recv_match(timeout=timeout, blocking=False)
                
                if msg is None:
                    break
                
                msg_type = msg.get_type()
                
                if msg_type == 'PARAM_VALUE':
                    self._handle_param_value(msg)
                    messages_processed += 1
                elif msg_type == 'HEARTBEAT':
                    self._handle_heartbeat(msg)
                    messages_processed += 1
                elif msg_type == 'COMMAND_ACK':
                    self._handle_command_ack(msg)
                    messages_processed += 1
                
        except Exception as e:
            logger.error(f"Error processing messages: {e}")
        
        return messages_processed
    
    def _handle_param_value(self, msg) -> None:
        """Handle PARAM_VALUE message."""
        try:
            # Handle both string and bytes param_id
            if isinstance(msg.param_id, bytes):
                param_name = msg.param_id.decode('utf-8').rstrip('\x00')
            else:
                param_name = str(msg.param_id).rstrip('\x00')
            param_info = ParameterInfo(
                name=param_name,
                value=msg.param_value,
                param_type=msg.param_type,
                param_count=msg.param_count,
                param_index=msg.param_index
            )
            
            self.parameters[param_name] = param_info
            logger.debug(f"Received parameter: {param_name} = {msg.param_value}")
            
            # Call callbacks
            self._call_parameter_callbacks(param_name, param_info)
            
        except Exception as e:
            logger.error(f"Error handling PARAM_VALUE: {e}")
    
    def _handle_command_ack(self, msg) -> None:
        """Handle COMMAND_ACK message."""
        try:
            success = msg.result == mavlink2.MAV_RESULT_ACCEPTED
            logger.debug(f"Command ACK - Command: {msg.command}, Result: {'SUCCESS' if success else 'FAILED'}")
            
        except Exception as e:
            logger.error(f"Error handling COMMAND_ACK: {e}")
    
    def _handle_heartbeat(self, msg) -> None:
        """Handle HEARTBEAT message."""
        self._last_heartbeat = time.time()
        logger.debug(f"Heartbeat from system {msg.get_srcSystem()}")
    
    def _wait_for_heartbeat(self, timeout: Optional[float] = None) -> bool:
        """Wait for heartbeat from PX4."""
        if timeout is None:
            timeout = self.config.heartbeat_timeout
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            msg = self.connection.recv_match(type='HEARTBEAT', timeout=0.1, blocking=False)
            if msg:
                logger.debug("✓ Heartbeat received")
                self._last_heartbeat = time.time()
                return True
        
        logger.warning("✗ Heartbeat timeout")
        return False
    
    def _call_parameter_callbacks(self, param_name: str, param_info: ParameterInfo) -> None:
        """Call parameter callbacks."""
        # Specific parameter callbacks
        if param_name in self.parameter_callbacks:
            for callback in self.parameter_callbacks[param_name]:
                try:
                    callback(param_info)
                except Exception as e:
                    logger.error(f"Error in parameter callback: {e}")
        
        # Wildcard callbacks
        if "*" in self.parameter_callbacks:
            for callback in self.parameter_callbacks["*"]:
                try:
                    callback(param_info)
                except Exception as e:
                    logger.error(f"Error in wildcard callback: {e}")


if __name__ == "__main__":
    # Test the MAVLink handler
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("=== MAVLink Handler Test ===")
    print("Make sure your PX4 flight controller is connected via USB")
    
    # Create handler
    handler = MAVLinkHandler()
    
    # Test connection
    print("\n1. Testing connection...")
    if handler.connect():
        print("✓ Connected successfully!")
        
        print(f"✓ Connected to: {handler.config.port} at {handler.config.baudrate} baud")
        
        # Test parameter operations
        print("\n2. Testing parameter operations...")
        
        # Add callback to see parameters
        def param_callback(param: ParameterInfo):
            if param.param_index % 100 == 0:  # Print every 100th parameter
                print(f"  Parameter {param.param_index}/{param.param_count}: {param.name} = {param.value}")
        
        handler.add_parameter_callback("*", param_callback)
        
        # Request parameter list
        if handler.request_parameter_list():
            print("✓ Parameter list requested")
            
            # Process messages
            print("✓ Processing messages...")
            start_time = time.time()
            total_messages = 0
            
            while time.time() - start_time < 15:  # 15 seconds
                messages = handler.process_messages(0.1)
                total_messages += messages
                
                if messages == 0:
                    time.sleep(0.1)
                
                # Show progress
                params = handler.get_all_parameters()
                if len(params) > 0 and len(params) % 50 == 0:
                    print(f"  Received {len(params)} parameters so far...")
            
            params = handler.get_all_parameters()
            print(f"✓ Total parameters received: {len(params)}")
            print(f"✓ Total messages processed: {total_messages}")
            
            # Show some sample parameters
            if len(params) > 0:
                print("\n3. Sample parameters:")
                count = 0
                for name, param in params.items():
                    count += 1
                    if count >= 5:
                        break
            
            # Test specific parameter
            print(f"\n4. Testing specific parameter request...")
            test_params = ["SYS_AUTOSTART", "MC_ROLLRATE_P", "MPC_XY_P"]
            
            for param_name in test_params:
                if handler.request_parameter(param_name):
                    print(f"✓ {param_name} requested")
                    # Process messages briefly
                    for _ in range(10):
                        handler.process_messages(0.1)
                        time.sleep(0.1)
                    
                    param = handler.get_parameter(param_name)
                    if param:
                        print(f"✓ {param_name} = {param.value}")
                        break
                    else:
                        print(f"? {param_name} not found")
            
        else:
            print("✗ Failed to request parameter list")
        
        # Disconnect
        print("\n5. Disconnecting...")
        handler.disconnect()
        print("✓ Disconnected")
        
    else:
        print("✗ Connection failed!")
        print("\nTroubleshooting:")
        print("- Make sure flight controller is connected via USB")
        print("- Make sure it's powered on and fully booted")
        print("- Close any other software using the COM port (QGroundControl, etc.)")
        print("- Try a different USB cable or port")
    
    print("\n=== Test Complete ===")