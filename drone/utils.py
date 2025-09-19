"""
Utility functions for drone communication and COM port detection.
"""

import serial
import serial.tools.list_ports
import logging
from typing import List, Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


#appends dets of ports connected to ports list
def detect_com_ports() -> List[Dict[str, Any]]:
    """
    Detect all available COM ports and return detailed information.
    
    Returns:
        List of dictionaries containing port information:
        - port: Port name (e.g., 'COM3', '/dev/ttyUSB0')
        - description: Human readable description
        - hwid: Hardware ID
        - vid: Vendor ID
        - pid: Product ID
    """
    ports = []
    
    try:
        available_ports = serial.tools.list_ports.comports()
        
        for port in available_ports:
            port_info = {
                'port': port.device,
                'description': port.description,
                'hwid': port.hwid,
                'vid': port.vid,
                'pid': port.pid,
                'serial_number': port.serial_number,
                'manufacturer': port.manufacturer,
                'product': port.product
            }
            ports.append(port_info)   #ports <list> has all the ports info and retured
            logger.info(f"Found port: {port.device} - {port.description}")
            
    except Exception as e:
        logger.error(f"Error detecting COM ports: {e}")
        
    return ports


# this function gen does find the px4 port exactly using the px4 keywords in description field 
def find_px4_port() -> Optional[str]:
    """
    Attempt to find a PX4-compatible port by checking common patterns.
    
    Returns:
        Port name if found, None otherwise
    """
    ports = detect_com_ports()
    
    # Common PX4 identifiers
    px4_keywords = [
        'px4', 'pixhawk', 'mavlink', 'autopilot', 'flight controller',
        'ardupilot', 'qgroundcontrol', 'usb serial', 'ftdi', 'cp210','fmu'
    ]
    
    for port_info in ports:
        description = port_info['description'].lower()
        manufacturer = (port_info.get('manufacturer') or '').lower()
        product = (port_info.get('product') or '').lower()
        
        # Check if any PX4 keywords are in the description
        for keyword in px4_keywords:
            if keyword in description or keyword in manufacturer or keyword in product:
                logger.info(f"Found potential PX4 port: {port_info['port']} - {port_info['description']}")
                return port_info['port']
    
    # If no specific PX4 port found, return the first available port
    if ports:
        logger.warning(f"No specific PX4 port detected, using first available: {ports[0]['port']}")
        return ports[0]['port']
    
    return None

#sends a baudrate to the port and checks if the port is accessible
def test_port_connection(port: str, baudrate: int = 57600, timeout: float = 5.0) -> bool:
    """
    Test if a port can be opened and is responsive.
    
    Args:
        port: Port name to test
        baudrate: Baud rate for testing
        timeout: Timeout in seconds
        
    Returns:
        True if port is accessible, False otherwise
    """
    try:
        with serial.Serial(port, baudrate, timeout=timeout) as ser:
            # Try to read any available data
            time.sleep(0.1)  # Give it a moment to initialize
            data = ser.read(ser.in_waiting)
            logger.info(f"Port {port} is accessible, read {len(data)} bytes")
            return True
            
    except serial.SerialException as e:
        logger.error(f"Port {port} is not accessible: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error testing port {port}: {e}")
        return False


def get_available_baudrates() -> List[int]:
    """
    Get list of commonly used baud rates for PX4 communication.
    
    Returns:
        List of baud rates
    """
    return [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

#it checks the validity of the port and baudrate
def validate_port_config(port: str, baudrate: int) -> Dict[str, Any]:
    """
    Validate port configuration and return status.
    
    Args:
        port: Port name
        baudrate: Baud rate
        
    Returns:
        Dictionary with validation results
    """
    result = {
        'valid': False,
        'port_exists': False,
        'port_accessible': False,
        'baudrate_valid': False,
        'error': None
    }
    
    try:
        # Check if port exists
        available_ports = [p['port'] for p in detect_com_ports()]
        result['port_exists'] = port in available_ports
        
        if not result['port_exists']:
            result['error'] = f"Port {port} not found in available ports"
            return result
        
        # Check if baudrate is valid
        result['baudrate_valid'] = baudrate in get_available_baudrates()
        if not result['baudrate_valid']:
            result['error'] = f"Baudrate {baudrate} not in supported list"
            return result
        
        # Test port accessibility
        result['port_accessible'] = test_port_connection(port, baudrate)
        if not result['port_accessible']:
            result['error'] = f"Port {port} is not accessible"
            return result
        
        result['valid'] = True
        
    except Exception as e:
        result['error'] = f"Validation error: {e}"
        logger.error(f"Port validation error: {e}")
    
    return result


def format_port_info(port_info: Dict[str, Any]) -> str:
    """
    Format port information for display.
    
    Args:
        port_info: Port information dictionary
        
    Returns:
        Formatted string
    """
    return (f"Port: {port_info['port']}\n"
            f"Description: {port_info['description']}\n"
            f"Hardware ID: {port_info['hwid']}\n"
            f"Vendor ID: {port_info.get('vid', 'N/A')}\n"
            f"Product ID: {port_info.get('pid', 'N/A')}\n"
            f"Serial: {port_info.get('serial_number', 'N/A')}\n"
            f"Manufacturer: {port_info.get('manufacturer', 'N/A')}\n"
            f"Product: {port_info.get('product', 'N/A')}")


if __name__ == "__main__":
    # Test the utility functions
    logging.basicConfig(level=logging.INFO)
    
    print("=== COM Port Detection Test ===")
    ports = detect_com_ports()
    
    if ports:
        print(f"\nFound {len(ports)} ports:")
        for port in ports:
            print(f"\n{format_port_info(port)}")
    else:
        print("No COM ports found")
    
    print("\n=== PX4 Port Detection ===")
    px4_port = find_px4_port()
    if px4_port:
        print(f"Potential PX4 port: {px4_port}")
        
        print("\n=== Port Validation ===")
        for baudrate in [57600, 115200]:
            result = validate_port_config(px4_port, baudrate)
            print(f"Port {px4_port} at {baudrate} baud: {'✓' if result['valid'] else '✗'}")
            if not result['valid']:
                print(f"  Error: {result['error']}")
    else:
        print("No PX4 port detected")
