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

from .utils import validate_port_config, find_px4_port

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
    baudrate: int = 57600
    timeout: float = 5.0
    retries: int = 3
    heartbeat_timeout: float = 10.0


class MAVLinkHandler:
    """
    MAVLink handler for PX4 communication.
    
    Features:
    - COM port connection
    - Parameter list fetching (PARAM_REQUEST_LIST)
    - Parameter reading (PARAM_REQUEST_READ)
    - Parameter setting (PARAM_SET)
    - ACK confirmation handling
    """
    
    def __init__(self, config: Optional[ConnectionConfig] = None):
        """
        Initialize MAVLink handler.
        
        Args:
            config: Connection configuration
        """
        self.config = config or ConnectionConfig(port="", baudrate=57600)
        self.connection = None
        self.state = ConnectionState.DISCONNECTED
        self.parameters: Dict[str, ParameterInfo] = {}
        self.parameter_callbacks: Dict[str, List[Callable]] = {}
        self.ack_callbacks: Dict[str, List[Callable]] = {}
        self._last_heartbeat = 0
        self._message_handlers = {
            mavlink2.MAVLINK_MSG_ID_PARAM_VALUE: self._handle_param_value,
            mavlink2.MAVLINK_MSG_ID_PARAM_ACK: self._handle_param_ack,
            mavlink2.MAVLINK_MSG_ID_HEARTBEAT: self._handle_heartbeat,
        }
        
    def connect(self, port: Optional[str] = None, baudrate: Optional[int] = None) -> bool:
        """
        Connect to PX4 via MAVLink.
        
        Args:
            port: COM port (if None, will auto-detect)
            baudrate: Baud rate (if None, uses config default)
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.state = ConnectionState.CONNECTING
            
            # Use provided values or fall back to config/auto-detect
            if port is None:
                port = self.config.port or find_px4_port()
                if not port:
                    raise ValueError("No port specified and auto-detection failed")
            
            if baudrate is None:
                baudrate = self.config.baudrate
            
            # Validate port configuration
            validation = validate_port_config(port, baudrate)
            if not validation['valid']:
                raise ValueError(f"Port validation failed: {validation['error']}")
            
            logger.info(f"Connecting to {port} at {baudrate} baud...")
            
            # Create connection string
            connection_string = f"{port}:{baudrate}"
            
            # Attempt connection with retries
            for attempt in range(self.config.retries):
                try:
                    self.connection = mavutil.mavlink_connection(
                        connection_string,
                        timeout=self.config.timeout
                    )
                    
                    # Wait for heartbeat to confirm connection
                    if self._wait_for_heartbeat():
                        self.state = ConnectionState.CONNECTED
                        self.config.port = port
                        self.config.baudrate = baudrate
                        logger.info(f"Successfully connected to {port}")
                        
                        # Start message processing
                        self._start_message_processing()
                        return True
                    else:
                        logger.warning(f"Heartbeat timeout on attempt {attempt + 1}")
                        self.connection.close()
                        
                except Exception as e:
                    logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                    if attempt < self.config.retries - 1:
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
        """
        Request complete parameter list from PX4.
        
        Returns:
            True if request sent successfully, False otherwise
        """
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
        """
        Request specific parameter from PX4.
        
        Args:
            param_name: Name of parameter to request
            
        Returns:
            True if request sent successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Not connected to PX4")
            return False
        
        try:
            logger.info(f"Requesting parameter: {param_name}")
            self.connection.mav.param_request_read_send(
                self.connection.target_system,
                self.connection.target_component,
                param_name.encode('utf-8'),
                -1  # -1 means use param_name instead of param_index
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to request parameter {param_name}: {e}")
            return False
    
    def set_parameter(self, param_name: str, value: float, param_type: int = mavlink2.MAV_PARAM_TYPE_REAL32) -> bool:
        """
        Set parameter value on PX4.
        
        Args:
            param_name: Name of parameter to set
            value: New parameter value
            param_type: Parameter type (default: MAV_PARAM_TYPE_REAL32)
            
        Returns:
            True if request sent successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Not connected to PX4")
            return False
        
        try:
            logger.info(f"Setting parameter {param_name} = {value}")
            self.connection.mav.param_set_send(
                self.connection.target_system,
                self.connection.target_component,
                param_name.encode('utf-8'),
                value,
                param_type
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to set parameter {param_name}: {e}")
            return False
    
    def get_parameter(self, param_name: str) -> Optional[ParameterInfo]:
        """
        Get parameter information from local cache.
        
        Args:
            param_name: Name of parameter
            
        Returns:
            ParameterInfo if found, None otherwise
        """
        return self.parameters.get(param_name)
    
    def get_all_parameters(self) -> Dict[str, ParameterInfo]:
        """
        Get all cached parameters.
        
        Returns:
            Dictionary of all parameters
        """
        return self.parameters.copy()
    
    def add_parameter_callback(self, param_name: str, callback: Callable[[ParameterInfo], None]) -> None:
        """
        Add callback for parameter updates.
        
        Args:
            param_name: Parameter name (or "*" for all parameters)
            callback: Callback function
        """
        if param_name not in self.parameter_callbacks:
            self.parameter_callbacks[param_name] = []
        self.parameter_callbacks[param_name].append(callback)
    
    def add_ack_callback(self, param_name: str, callback: Callable[[bool, str], None]) -> None:
        """
        Add callback for parameter ACK responses.
        
        Args:
            param_name: Parameter name
            callback: Callback function (success, message)
        """
        if param_name not in self.ack_callbacks:
            self.ack_callbacks[param_name] = []
        self.ack_callbacks[param_name].append(callback)
    
    def _start_message_processing(self) -> None:
        """Start background message processing."""
        # This would typically be run in a separate thread
        # For now, we'll process messages on demand
        pass
    
    def process_messages(self, timeout: float = 0.1) -> int:
        """
        Process incoming MAVLink messages.
        
        Args:
            timeout: Timeout for message processing
            
        Returns:
            Number of messages processed
        """
        if not self.is_connected():
            return 0
        
        messages_processed = 0
        
        try:
            while True:
                msg = self.connection.recv_match(
                    type=list(self._message_handlers.keys()),
                    timeout=timeout,
                    blocking=False
                )
                
                if msg is None:
                    break
                
                # Route message to appropriate handler
                msg_type = msg.get_type()
                if msg_type in self._message_handlers:
                    self._message_handlers[msg_type](msg)
                    messages_processed += 1
                
        except Exception as e:
            logger.error(f"Error processing messages: {e}")
        
        return messages_processed
    
    def _handle_param_value(self, msg) -> None:
        """Handle PARAM_VALUE message."""
        try:
            param_name = msg.param_id.decode('utf-8').rstrip('\x00')
            param_info = ParameterInfo(
                name=param_name,
                value=msg.param_value,
                param_type=msg.param_type,
                param_count=msg.param_count,
                param_index=msg.param_index
            )
            
            self.parameters[param_name] = param_info
            logger.debug(f"Received parameter: {param_name} = {msg.param_value}")
            
            # Call parameter callbacks
            self._call_parameter_callbacks(param_name, param_info)
            
        except Exception as e:
            logger.error(f"Error handling PARAM_VALUE: {e}")
    
    def _handle_param_ack(self, msg) -> None:
        """Handle PARAM_ACK message."""
        try:
            param_name = msg.param_id.decode('utf-8').rstrip('\x00')
            success = msg.param_result == mavlink2.PARAM_ACK_ACCEPTED
            
            logger.info(f"Parameter ACK for {param_name}: {'SUCCESS' if success else 'FAILED'}")
            
            # Call ACK callbacks
            self._call_ack_callbacks(param_name, success, msg.param_result)
            
        except Exception as e:
            logger.error(f"Error handling PARAM_ACK: {e}")
    
    def _handle_heartbeat(self, msg) -> None:
        """Handle HEARTBEAT message."""
        self._last_heartbeat = time.time()
        logger.debug("Received heartbeat")
    
    def _wait_for_heartbeat(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for heartbeat from PX4.
        
        Args:
            timeout: Timeout in seconds (uses config default if None)
            
        Returns:
            True if heartbeat received, False if timeout
        """
        if timeout is None:
            timeout = self.config.heartbeat_timeout
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            msg = self.connection.recv_match(type='HEARTBEAT', timeout=0.1)
            if msg:
                logger.debug("Heartbeat received")
                return True
        
        logger.warning("Heartbeat timeout")
        return False
    
    def _call_parameter_callbacks(self, param_name: str, param_info: ParameterInfo) -> None:
        """Call parameter update callbacks."""
        # Call specific parameter callbacks
        if param_name in self.parameter_callbacks:
            for callback in self.parameter_callbacks[param_name]:
                try:
                    callback(param_info)
                except Exception as e:
                    logger.error(f"Error in parameter callback: {e}")
        
        # Call wildcard callbacks
        if "*" in self.parameter_callbacks:
            for callback in self.parameter_callbacks["*"]:
                try:
                    callback(param_info)
                except Exception as e:
                    logger.error(f"Error in wildcard parameter callback: {e}")
    
    def _call_ack_callbacks(self, param_name: str, success: bool, result: int) -> None:
        """Call ACK callbacks."""
        if param_name in self.ack_callbacks:
            for callback in self.ack_callbacks[param_name]:
                try:
                    callback(success, f"Result code: {result}")
                except Exception as e:
                    logger.error(f"Error in ACK callback: {e}")


if __name__ == "__main__":
    # Test the MAVLink handler
    logging.basicConfig(level=logging.INFO)
    
    # Create handler
    handler = MAVLinkHandler()
    
    # Test connection
    print("Testing MAVLink connection...")
    if handler.connect():
        print("✓ Connected successfully")
        
        # Test parameter operations
        print("\nTesting parameter operations...")
        
        # Request parameter list
        if handler.request_parameter_list():
            print("✓ Parameter list requested")
            
            # Process messages for a bit to get parameters
            print("Processing messages...")
            for i in range(50):  # Process for 5 seconds
                handler.process_messages(0.1)
                time.sleep(0.1)
            
            params = handler.get_all_parameters()
            print(f"✓ Received {len(params)} parameters")
            
            # Test specific parameter request
            if handler.request_parameter("SYS_AUTOSTART"):
                print("✓ SYS_AUTOSTART parameter requested")
                handler.process_messages(1.0)
                
                param = handler.get_parameter("SYS_AUTOSTART")
                if param:
                    print(f"✓ SYS_AUTOSTART = {param.value}")
                else:
                    print("✗ SYS_AUTOSTART not found")
        
        handler.disconnect()
        print("✓ Disconnected")
    else:
        print("✗ Connection failed")
