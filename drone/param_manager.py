"""
Parameter manager for PX4 drone communication.
Handles parameter operations with ACK confirmation and verification.
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future

from .mavlink_handler import MAVLinkHandler, ParameterInfo, ConnectionConfig
from .utils import validate_port_config, find_px4_port

logger = logging.getLogger(__name__)


class ParameterOperation(Enum):
    """Parameter operation types."""
    READ = "read"
    WRITE = "write"
    LIST = "list"


@dataclass
class ParameterOperationResult:
    """Result of a parameter operation."""
    success: bool
    operation: ParameterOperation
    parameter_name: str
    value: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: float = 0.0


@dataclass
class ParameterManagerConfig:
    """Configuration for parameter manager."""
    connection_config: ConnectionConfig
    operation_timeout: float = 10.0
    retry_attempts: int = 3
    retry_delay: float = 1.0
    message_processing_interval: float = 0.1
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 5


class ParameterManager:
    """
    High-level parameter manager for PX4 communication.
    
    Features:
    - Automatic connection management
    - Parameter operations with ACK confirmation
    - Retry logic and error handling
    - Asynchronous operations
    - Parameter caching and verification
    """
    
    def __init__(self, config: Optional[ParameterManagerConfig] = None):
        """
        Initialize parameter manager.
        
        Args:
            config: Configuration for the parameter manager
        """
        self.config = config or ParameterManagerConfig(
            connection_config=ConnectionConfig()
        )
        
        self.mavlink_handler = MAVLinkHandler(self.config.connection_config)
        self.parameters: Dict[str, ParameterInfo] = {}
        self.operation_results: Dict[str, ParameterOperationResult] = {}
        self.pending_operations: Dict[str, Future] = {}
        
        # Threading
        self._message_thread = None
        self._stop_message_processing = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=4)
        
        # Callbacks
        self.operation_callbacks: List[Callable[[ParameterOperationResult], None]] = []
        self.connection_callbacks: List[Callable[[bool], None]] = []
        
        # Setup MAVLink callbacks
        self._setup_mavlink_callbacks()
        
    def connect(self, port: Optional[str] = None, baudrate: Optional[int] = None) -> bool:
        """
        Connect to PX4 and start parameter management.
        
        Args:
            port: COM port (auto-detect if None)
            baudrate: Baud rate (use config default if None)
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info("Connecting to PX4...")
            
            # Connect MAVLink handler
            if not self.mavlink_handler.connect(port, baudrate):
                logger.error("Failed to connect MAVLink handler")
                return False
            
            # Start message processing thread
            self._start_message_processing()
            
            # Request parameter list
            if not self.mavlink_handler.request_parameter_list():
                logger.error("Failed to request parameter list")
                return False
            
            # Wait for initial parameters
            if self._wait_for_parameters(timeout=15.0):
                logger.info(f"Successfully connected and loaded {len(self.parameters)} parameters")
                self._notify_connection_callbacks(True)
                return True
            else:
                logger.warning("Connected but failed to load parameters")
                self._notify_connection_callbacks(True)
                return True  # Still consider it a success
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._notify_connection_callbacks(False)
            return False
    
    def disconnect(self) -> None:
        """Disconnect from PX4 and cleanup resources."""
        try:
            logger.info("Disconnecting from PX4...")
            
            # Stop message processing
            self._stop_message_processing.set()
            if self._message_thread and self._message_thread.is_alive():
                self._message_thread.join(timeout=2.0)
            
            # Disconnect MAVLink handler
            self.mavlink_handler.disconnect()
            
            # Shutdown executor
            self._executor.shutdown(wait=True)
            
            logger.info("Disconnected successfully")
            
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to PX4."""
        return self.mavlink_handler.is_connected()
    
    def get_parameter(self, param_name: str, timeout: Optional[float] = None) -> Optional[ParameterOperationResult]:
        """
        Get parameter value from PX4.
        
        Args:
            param_name: Name of parameter to read
            timeout: Operation timeout (uses config default if None)
            
        Returns:
            ParameterOperationResult with parameter value
        """
        if not self.is_connected():
            return ParameterOperationResult(
                success=False,
                operation=ParameterOperation.READ,
                parameter_name=param_name,
                error_message="Not connected to PX4"
            )
        
        try:
            logger.info(f"Reading parameter: {param_name}")
            
            # Check if we already have this parameter
            if param_name in self.parameters:
                param_info = self.parameters[param_name]
                return ParameterOperationResult(
                    success=True,
                    operation=ParameterOperation.READ,
                    parameter_name=param_name,
                    value=param_info.value,
                    timestamp=time.time()
                )
            
            # Request parameter from PX4
            if not self.mavlink_handler.request_parameter(param_name):
                return ParameterOperationResult(
                    success=False,
                    operation=ParameterOperation.READ,
                    parameter_name=param_name,
                    error_message="Failed to send parameter request"
                )
            
            # Wait for parameter response
            timeout = timeout or self.config.operation_timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if param_name in self.parameters:
                    param_info = self.parameters[param_name]
                    result = ParameterOperationResult(
                        success=True,
                        operation=ParameterOperation.READ,
                        parameter_name=param_name,
                        value=param_info.value,
                        timestamp=time.time()
                    )
                    self._notify_operation_callbacks(result)
                    return result
                
                time.sleep(0.1)
            
            return ParameterOperationResult(
                success=False,
                operation=ParameterOperation.READ,
                parameter_name=param_name,
                error_message=f"Timeout waiting for parameter {param_name}"
            )
            
        except Exception as e:
            logger.error(f"Error reading parameter {param_name}: {e}")
            return ParameterOperationResult(
                success=False,
                operation=ParameterOperation.READ,
                parameter_name=param_name,
                error_message=str(e)
            )
    
    def set_parameter(self, param_name: str, value: float, verify: bool = True, timeout: Optional[float] = None) -> ParameterOperationResult:
        """
        Set parameter value on PX4.
        
        Args:
            param_name: Name of parameter to set
            value: New parameter value
            verify: Whether to verify the parameter was set correctly
            timeout: Operation timeout (uses config default if None)
            
        Returns:
            ParameterOperationResult indicating success/failure
        """
        if not self.is_connected():
            return ParameterOperationResult(
                success=False,
                operation=ParameterOperation.WRITE,
                parameter_name=param_name,
                error_message="Not connected to PX4"
            )
        
        try:
            logger.info(f"Setting parameter {param_name} = {value}")
            
            # Set parameter with retries
            for attempt in range(self.config.retry_attempts):
                if self.mavlink_handler.set_parameter(param_name, value):
                    break
                elif attempt < self.config.retry_attempts - 1:
                    logger.warning(f"Parameter set attempt {attempt + 1} failed, retrying...")
                    time.sleep(self.config.retry_delay)
                else:
                    return ParameterOperationResult(
                        success=False,
                        operation=ParameterOperation.WRITE,
                        parameter_name=param_name,
                        error_message="Failed to send parameter set request"
                    )
            
            # Wait for ACK
            timeout = timeout or self.config.operation_timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # Check if we received an ACK for this parameter
                if param_name in self.operation_results:
                    result = self.operation_results[param_name]
                    if result.operation == ParameterOperation.WRITE:
                        del self.operation_results[param_name]  # Clean up
                        
                        # Verify parameter if requested
                        if verify and result.success:
                            verify_result = self._verify_parameter_set(param_name, value)
                            if not verify_result:
                                result.success = False
                                result.error_message = "Parameter verification failed"
                        
                        self._notify_operation_callbacks(result)
                        return result
                
                time.sleep(0.1)
            
            return ParameterOperationResult(
                success=False,
                operation=ParameterOperation.WRITE,
                parameter_name=param_name,
                error_message=f"Timeout waiting for parameter set ACK"
            )
            
        except Exception as e:
            logger.error(f"Error setting parameter {param_name}: {e}")
            return ParameterOperationResult(
                success=False,
                operation=ParameterOperation.WRITE,
                parameter_name=param_name,
                error_message=str(e)
            )
    
    def get_all_parameters(self) -> Dict[str, ParameterInfo]:
        """
        Get all cached parameters.
        
        Returns:
            Dictionary of all parameters
        """
        return self.parameters.copy()
    
    def refresh_parameters(self, timeout: Optional[float] = None) -> bool:
        """
        Refresh parameter list from PX4.
        
        Args:
            timeout: Operation timeout (uses config default if None)
            
        Returns:
            True if refresh successful, False otherwise
        """
        if not self.is_connected():
            logger.error("Not connected to PX4")
            return False
        
        try:
            logger.info("Refreshing parameter list...")
            
            # Clear existing parameters
            self.parameters.clear()
            
            # Request new parameter list
            if not self.mavlink_handler.request_parameter_list():
                logger.error("Failed to request parameter list")
                return False
            
            # Wait for parameters
            timeout = timeout or self.config.operation_timeout
            return self._wait_for_parameters(timeout)
            
        except Exception as e:
            logger.error(f"Error refreshing parameters: {e}")
            return False
    
    def add_operation_callback(self, callback: Callable[[ParameterOperationResult], None]) -> None:
        """
        Add callback for parameter operations.
        
        Args:
            callback: Callback function
        """
        self.operation_callbacks.append(callback)
    
    def add_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """
        Add callback for connection status changes.
        
        Args:
            callback: Callback function
        """
        self.connection_callbacks.append(callback)
    
    def _setup_mavlink_callbacks(self) -> None:
        """Setup MAVLink handler callbacks."""
        # Parameter update callback
        def on_parameter_update(param_info: ParameterInfo):
            self.parameters[param_info.name] = param_info
            logger.debug(f"Parameter updated: {param_info.name} = {param_info.value}")
        
        # ACK callback
        def on_parameter_ack(param_name: str, success: bool, message: str):
            result = ParameterOperationResult(
                success=success,
                operation=ParameterOperation.WRITE,
                parameter_name=param_name,
                error_message=None if success else message,
                timestamp=time.time()
            )
            self.operation_results[param_name] = result
            logger.debug(f"Parameter ACK: {param_name} - {'SUCCESS' if success else 'FAILED'}")
        
        self.mavlink_handler.add_parameter_callback("*", on_parameter_update)
        self.mavlink_handler.add_ack_callback("*", on_parameter_ack)
    
    def _start_message_processing(self) -> None:
        """Start background message processing thread."""
        if self._message_thread and self._message_thread.is_alive():
            return
        
        self._stop_message_processing.clear()
        self._message_thread = threading.Thread(
            target=self._message_processing_loop,
            daemon=True
        )
        self._message_thread.start()
        logger.debug("Started message processing thread")
    
    def _message_processing_loop(self) -> None:
        """Background message processing loop."""
        while not self._stop_message_processing.is_set():
            try:
                if self.is_connected():
                    self.mavlink_handler.process_messages(self.config.message_processing_interval)
                else:
                    time.sleep(0.5)  # Wait longer if not connected
            except Exception as e:
                logger.error(f"Error in message processing loop: {e}")
                time.sleep(1.0)
    
    def _wait_for_parameters(self, timeout: float) -> bool:
        """
        Wait for parameters to be loaded.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            True if parameters loaded, False if timeout
        """
        start_time = time.time()
        initial_count = len(self.parameters)
        
        while time.time() - start_time < timeout:
            if len(self.parameters) > initial_count:
                # Parameters are being loaded
                time.sleep(0.5)
                continue
            
            # Check if we have a reasonable number of parameters
            if len(self.parameters) > 100:  # PX4 typically has 500+ parameters
                return True
            
            time.sleep(0.1)
        
        logger.warning(f"Parameter loading timeout. Loaded {len(self.parameters)} parameters")
        return len(self.parameters) > 0
    
    def _verify_parameter_set(self, param_name: str, expected_value: float) -> bool:
        """
        Verify that a parameter was set correctly.
        
        Args:
            param_name: Parameter name
            expected_value: Expected value
            
        Returns:
            True if parameter matches expected value, False otherwise
        """
        try:
            # Request parameter to verify
            if not self.mavlink_handler.request_parameter(param_name):
                return False
            
            # Wait for parameter response
            start_time = time.time()
            while time.time() - start_time < 5.0:  # 5 second timeout for verification
                if param_name in self.parameters:
                    actual_value = self.parameters[param_name].value
                    # Allow small floating point differences
                    if abs(actual_value - expected_value) < 0.001:
                        logger.info(f"Parameter {param_name} verified: {actual_value}")
                        return True
                    else:
                        logger.warning(f"Parameter {param_name} verification failed: expected {expected_value}, got {actual_value}")
                        return False
                
                time.sleep(0.1)
            
            logger.warning(f"Parameter {param_name} verification timeout")
            return False
            
        except Exception as e:
            logger.error(f"Error verifying parameter {param_name}: {e}")
            return False
    
    def _notify_operation_callbacks(self, result: ParameterOperationResult) -> None:
        """Notify operation callbacks."""
        for callback in self.operation_callbacks:
            try:
                callback(result)
            except Exception as e:
                logger.error(f"Error in operation callback: {e}")
    
    def _notify_connection_callbacks(self, connected: bool) -> None:
        """Notify connection callbacks."""
        for callback in self.connection_callbacks:
            try:
                callback(connected)
            except Exception as e:
                logger.error(f"Error in connection callback: {e}")


if __name__ == "__main__":
    # Test the parameter manager
    logging.basicConfig(level=logging.INFO)
    
    # Create parameter manager
    config = ParameterManagerConfig(
        connection_config=ConnectionConfig(baudrate=57600)
    )
    manager = ParameterManager(config)
    
    # Add callbacks
    def on_operation(result: ParameterOperationResult):
        print(f"Operation result: {result.operation.value} {result.parameter_name} - {'SUCCESS' if result.success else 'FAILED'}")
        if not result.success:
            print(f"  Error: {result.error_message}")
    
    def on_connection(connected: bool):
        print(f"Connection status: {'CONNECTED' if connected else 'DISCONNECTED'}")
    
    manager.add_operation_callback(on_operation)
    manager.add_connection_callback(on_connection)
    
    try:
        # Test connection
        print("Testing parameter manager...")
        if manager.connect():
            print("✓ Connected successfully")
            
            # Test parameter operations
            print("\nTesting parameter operations...")
            
            # Read SYS_AUTOSTART
            result = manager.get_parameter("SYS_AUTOSTART")
            if result and result.success:
                print(f"✓ SYS_AUTOSTART = {result.value}")
                
                # Test setting parameter (with a safe value)
                new_value = result.value + 1 if result.value < 1000 else result.value - 1
                set_result = manager.set_parameter("SYS_AUTOSTART", new_value, verify=True)
                if set_result.success:
                    print(f"✓ Successfully set SYS_AUTOSTART = {new_value}")
                    
                    # Verify the change
                    verify_result = manager.get_parameter("SYS_AUTOSTART")
                    if verify_result and verify_result.success:
                        print(f"✓ Verified SYS_AUTOSTART = {verify_result.value}")
                else:
                    print(f"✗ Failed to set SYS_AUTOSTART: {set_result.error_message}")
            else:
                print("✗ Failed to read SYS_AUTOSTART")
            
            # Show parameter count
            params = manager.get_all_parameters()
            print(f"\nTotal parameters loaded: {len(params)}")
            
        else:
            print("✗ Connection failed")
    
    finally:
        manager.disconnect()
        print("✓ Disconnected")
