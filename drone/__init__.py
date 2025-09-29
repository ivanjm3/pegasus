"""
Drone communication package for PX4 parameter management.

This package provides high-level interfaces for communicating with PX4 drones
via MAVLink protocol, including parameter reading, writing, and management.
"""

from .mavlink_handler import MAVLinkHandler, ParameterInfo, ConnectionConfig, ConnectionState
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
    
    # Configuration classes
    "ConnectionConfig",
    
    # Data classes
    "ParameterInfo",
    
    # Enums
    "ConnectionState",
    
    # Utility functions
    "detect_com_ports",
    "find_px4_port",
    "test_port_connection",
    "get_available_baudrates",
    "validate_port_config",
    "format_port_info",
]


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
        from .mavlink_handler import MAVLinkHandler
        from .param_manager import read_parameter
        
        handler = MAVLinkHandler()
        if not handler.connect(port, baudrate):
            return False
        
        # Test reading a common parameter
        result = read_parameter(handler, "SYS_AUTOSTART")
        
        handler.disconnect()
        return "✅" in result if result else False
        
    except Exception as e:
        print(f"Quick test failed: {e}")
        return False
