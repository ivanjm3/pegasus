"""
Utility functions for drone communication and COM port detection.
"""

import serial
import serial.tools.list_ports
import logging
from typing import List, Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


def detect_com_ports() -> List[Dict[str, Any]]:
    """Detect all available COM ports and return detailed information."""
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
            ports.append(port_info)
    except Exception as e:
        logger.error(f"Error detecting COM ports: {e}")
    return ports


def find_px4_port() -> Optional[str]:
    """Try to find a PX4-compatible port using keywords."""
    ports = detect_com_ports()
    px4_keywords = [
        'px4', 'pixhawk', 'mavlink', 'autopilot', 'flight controller',
        'ardupilot', 'qgroundcontrol', 'usb serial', 'ftdi', 'cp210', 'fmu'
    ]

    for port_info in ports:
        description = (port_info['description'] or '').lower()
        manufacturer = (port_info.get('manufacturer') or '').lower()
        product = (port_info.get('product') or '').lower()

        for keyword in px4_keywords:
            if keyword in description or keyword in manufacturer or keyword in product:
                return port_info['port']

    return ports[0]['port'] if ports else None


def test_port_connection(port: str, baudrate: int = 57600, timeout: float = 5.0) -> bool:
    """Test if a port can be opened and is responsive."""
    try:
        with serial.Serial(port, baudrate, timeout=timeout) as ser:
            time.sleep(0.1)
            _ = ser.read(ser.in_waiting)
            return True
    except Exception as e:
        logger.error(f"Port {port} error: {e}")
        return False


def get_available_baudrates() -> List[int]:
    """Common baud rates for PX4 communication."""
    return [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]


def validate_port_config(port: str, baudrate: int) -> Dict[str, Any]:
    """Validate port configuration and return status."""
    result = {
        'valid': False,
        'port_exists': False,
        'port_accessible': False,
        'baudrate_valid': False,
        'error': None
    }

    try:
        available_ports = [p['port'] for p in detect_com_ports()]
        result['port_exists'] = port in available_ports

        if not result['port_exists']:
            result['error'] = f"Port {port} not found"
            return result

        result['baudrate_valid'] = baudrate in get_available_baudrates()
        if not result['baudrate_valid']:
            result['error'] = f"Baudrate {baudrate} not supported"
            return result

        result['port_accessible'] = test_port_connection(port, baudrate)
        if not result['port_accessible']:
            result['error'] = f"Cannot open {port}"
            return result

        result['valid'] = True
    except Exception as e:
        result['error'] = f"Validation error: {e}"

    return result


def format_port_info(port_info: Dict[str, Any]) -> str:
    """Format port information nicely for display."""
    return (
        f"  Port         : {port_info['port']}\n"
        f"  Description  : {port_info['description']}\n"
        f"  HWID         : {port_info['hwid']}\n"
        f"  Vendor ID    : {port_info.get('vid', 'N/A')}\n"
        f"  Product ID   : {port_info.get('pid', 'N/A')}\n"
        f"  Serial       : {port_info.get('serial_number', 'N/A')}\n"
        f"  Manufacturer : {port_info.get('manufacturer', 'N/A')}\n"
        f"  Product      : {port_info.get('product', 'N/A')}"
    )


if __name__ == "__main__":
    # Only show warnings & errors in logs
    logging.basicConfig(level=logging.WARNING)

    print("\n=== COM Port Detection ===")
    ports = detect_com_ports()
    if ports:
        print(f"\nFound {len(ports)} port(s):\n")
        for port in ports:
            print(format_port_info(port))
            print("-" * 50)
    else:
        print("No COM ports found.")

    print("\n=== PX4 Port Detection ===")
    px4_port = find_px4_port()
    if px4_port:
        print(f"PX4-compatible port detected: {px4_port}")
        print("\n=== Port Validation ===")
        for baudrate in [57600, 115200]:
            result = validate_port_config(px4_port, baudrate)
            status = "✓" if result['valid'] else "✗"
            print(f"  {px4_port} @ {baudrate} baud  -> {status}")
            if not result['valid'] and result['error']:
                print(f"    Error: {result['error']}")
    else:
        print("No PX4 port detected.")
