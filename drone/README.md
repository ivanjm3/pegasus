# Drone Communication Layer

This package provides a high-level interface for communicating with PX4 drones via MAVLink protocol. It supports parameter reading, writing, and management with automatic ACK confirmation and verification.

## Features

- **COM Port Detection**: Automatically detect and validate COM ports
- **PX4 Connection**: Connect to PX4 via pymavlink over serial communication
- **Parameter Management**: Read, write, and manage PX4 parameters
- **ACK Confirmation**: Automatic confirmation of parameter operations
- **Verification**: Verify parameter changes after setting
- **Error Handling**: Comprehensive error handling and retry logic
- **Threading**: Background message processing for real-time communication

## Quick Start

### Basic Usage

```python
from drone import create_parameter_manager

# Create parameter manager (auto-detect port)
manager = create_parameter_manager(baudrate=57600)

# Connect to PX4
if manager.connect():
    # Read a parameter
    result = manager.get_parameter("SYS_AUTOSTART")
    if result.success:
        print(f"SYS_AUTOSTART = {result.value}")
    
    # Set a parameter
    set_result = manager.set_parameter("SYS_AUTOSTART", 1001, verify=True)
    if set_result.success:
        print("Parameter set successfully!")
    
    # Disconnect
    manager.disconnect()
```

### Advanced Usage

```python
from drone import ParameterManager, ParameterManagerConfig, ConnectionConfig

# Create custom configuration
config = ParameterManagerConfig(
    connection_config=ConnectionConfig(
        port="COM3",  # or "/dev/ttyUSB0" on Linux
        baudrate=57600,
        timeout=10.0,
        retries=3
    ),
    operation_timeout=15.0,
    retry_attempts=3,
    auto_reconnect=True
)

# Create manager with custom config
manager = ParameterManager(config)

# Add callbacks
def on_operation(result):
    print(f"Operation: {result.operation.value} {result.parameter_name} - {'SUCCESS' if result.success else 'FAILED'}")

def on_connection(connected):
    print(f"Connection: {'CONNECTED' if connected else 'DISCONNECTED'}")

manager.add_operation_callback(on_operation)
manager.add_connection_callback(on_connection)

# Connect and use
if manager.connect():
    # Your operations here
    pass
```

## API Reference

### Core Classes

#### `ParameterManager`
Main class for PX4 parameter management.

**Methods:**
- `connect(port=None, baudrate=None) -> bool`: Connect to PX4
- `disconnect()`: Disconnect from PX4
- `get_parameter(param_name, timeout=None) -> ParameterOperationResult`: Read parameter
- `set_parameter(param_name, value, verify=True, timeout=None) -> ParameterOperationResult`: Set parameter
- `get_all_parameters() -> Dict[str, ParameterInfo]`: Get all cached parameters
- `refresh_parameters(timeout=None) -> bool`: Refresh parameter list from PX4
- `is_connected() -> bool`: Check connection status

#### `MAVLinkHandler`
Low-level MAVLink communication handler.

**Methods:**
- `connect(port=None, baudrate=None) -> bool`: Connect to PX4
- `request_parameter_list() -> bool`: Request complete parameter list
- `request_parameter(param_name) -> bool`: Request specific parameter
- `set_parameter(param_name, value, param_type) -> bool`: Set parameter value
- `process_messages(timeout=0.1) -> int`: Process incoming messages

### Utility Functions

#### Port Detection
- `detect_com_ports() -> List[Dict]`: Detect all available COM ports
- `find_px4_port() -> Optional[str]`: Find potential PX4 port
- `test_port_connection(port, baudrate, timeout) -> bool`: Test port accessibility
- `validate_port_config(port, baudrate) -> Dict`: Validate port configuration

#### Convenience Functions
- `create_parameter_manager(port, baudrate, **kwargs) -> ParameterManager`: Create configured manager
- `quick_test_connection(port, baudrate) -> bool`: Quick connection test

## Configuration

### ConnectionConfig
```python
ConnectionConfig(
    port="COM3",           # COM port (auto-detect if empty)
    baudrate=57600,        # Baud rate
    timeout=5.0,           # Connection timeout
    retries=3,             # Connection retry attempts
    heartbeat_timeout=10.0 # Heartbeat timeout
)
```

### ParameterManagerConfig
```python
ParameterManagerConfig(
    connection_config=ConnectionConfig(...),
    operation_timeout=10.0,      # Operation timeout
    retry_attempts=3,            # Retry attempts for operations
    retry_delay=1.0,             # Delay between retries
    message_processing_interval=0.1,  # Message processing interval
    auto_reconnect=True,         # Auto-reconnect on disconnect
    max_reconnect_attempts=5     # Max reconnect attempts
)
```

## Error Handling

The package includes comprehensive error handling:

- **Connection Errors**: Automatic retry with exponential backoff
- **Parameter Errors**: Detailed error messages and ACK handling
- **Timeout Handling**: Configurable timeouts for all operations
- **Validation**: Port and parameter validation before operations

## Testing

### Run Integration Tests
```bash
python test_drone_integration.py --port COM3 --baudrate 57600
```

### Run Example
```bash
python drone_example.py
```

### Test Individual Components
```python
# Test port detection
from drone import detect_com_ports, find_px4_port
ports = detect_com_ports()
px4_port = find_px4_port()

# Test quick connection
from drone import quick_test_connection
success = quick_test_connection("COM3", 57600)
```

## Requirements

- Python 3.7+
- pymavlink
- pyserial

## Common Issues

### Port Not Found
- Ensure PX4 is connected and powered on
- Check device manager for COM port assignment
- Try different baud rates (57600, 115200)

### Connection Timeout
- Verify PX4 is in the correct mode
- Check cable connection
- Try different COM port

### Parameter Operations Fail
- Ensure PX4 is not in flight mode
- Check parameter name spelling
- Verify parameter is writable

## QGroundControl Verification

After setting parameters, you can verify changes in QGroundControl:

1. Open QGroundControl
2. Connect to your PX4
3. Go to Vehicle Setup → Parameters
4. Search for the parameter you modified
5. Verify the value matches what you set

## Examples

See `drone_example.py` and `test_drone_integration.py` for complete examples of usage.
