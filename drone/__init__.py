"""
Drone communication package for PX4 parameter management.

This package provides high-level interfaces for communicating with PX4 drones
via MAVLink protocol, including parameter reading, writing, and management.
"""

from .mavlink_handler import MAVLinkHandler, ParameterInfo, ConnectionConfig, ConnectionState
from .param_manager import ParameterManager, ParameterManagerConfig, ParameterOperation, ParameterOperationResult
from .utils import (
    detect_com_ports,
    find_px4_port,
    test_port_connection,
    get_available_baudrates,
    validate_port_config,
    format_port_info
)

__version__ = "1.0.0"

__all__ = [
    # Core classes
    "MAVLinkHandler",
    "ParameterManager",
    
    # Configuration classes
    "ConnectionConfig",
    "ParameterManagerConfig",
    
    # Data classes
    "ParameterInfo",
    "ParameterOperationResult",
    
    # Enums
    "ConnectionState",
    "ParameterOperation",
    
    # Utility functions
    "detect_com_ports",
    "find_px4_port",
    "test_port_connection",
    "get_available_baudrates",
    "validate_port_config",
    "format_port_info",
]


def create_parameter_manager(port: str = None, baudrate: int = 57600, **kwargs) -> ParameterManager:
    """
    Convenience function to create a configured parameter manager.
    
    Args:
        port: COM port (auto-detect if None)
        baudrate: Baud rate for communication
        **kwargs: Additional configuration options
        
    Returns:
        Configured ParameterManager instance
    """
    connection_config = ConnectionConfig(
        port=port or "",
        baudrate=baudrate,
        **{k: v for k, v in kwargs.items() if k in ['timeout', 'retries', 'heartbeat_timeout']}
    )
    
    manager_config = ParameterManagerConfig(
        connection_config=connection_config,
        **{k: v for k, v in kwargs.items() if k in ['operation_timeout', 'retry_attempts', 'retry_delay']}
    )
    
    return ParameterManager(manager_config)


def quick_test_connection(port: str = None, baudrate: int = 57600) -> bool:
    """
    Quick test to verify PX4 connection and basic parameter operations.
    
    Args:
        port: COM port (auto-detect if None)
        baudrate: Baud rate for communication
        
    Returns:
        True if test successful, False otherwise
    """
    try:
        manager = create_parameter_manager(port, baudrate)
        
        if not manager.connect():
            return False
        
        # Test reading a common parameter
        result = manager.get_parameter("SYS_AUTOSTART", timeout=10.0)
        
        manager.disconnect()
        return result.success if result else False
        
    except Exception as e:
        print(f"Quick test failed: {e}")
        return False
