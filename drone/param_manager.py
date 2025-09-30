"""
Simplified Parameter Editor using existing MAVLinkHandler.
Much cleaner and uses your existing MAVLink infrastructure.
"""

import time
import logging
import math
from .mavlink_handler import MAVLinkHandler, ConnectionConfig, ParameterInfo
try:
    # Used only for type-aware display formatting
    from pymavlink.dialects.v20 import common as mavlink2
except Exception:
    mavlink2 = None  # Fallback: will display raw values


def _format_value_for_display(param: ParameterInfo) -> str:
    """Return a display string according to MAV_PARAM_TYPE without altering the value.

    - Integer types are shown as integers
    - Bitmask-like params (name ends with _MASK) are shown as decimal and hex
    - Booleans (0/1) are shown with boolean hint
    - Floats are shown with trimmed precision
    - Unknown types fall back to the raw numeric
    """
    value = param.value
    ptype = getattr(param, 'param_type', None)

    def fmt_float(x: float) -> str:
        # Trim unnecessary zeros while keeping reasonable precision
        s = f"{x:.6f}"
        s = s.rstrip('0').rstrip('.') if '.' in s else s
        return s

    # If pymavlink types are unavailable, best-effort formatting
    if mavlink2 is None or ptype is None:
        return fmt_float(value)

    int_types = {
        getattr(mavlink2, 'MAV_PARAM_TYPE_INT8', -1),
        getattr(mavlink2, 'MAV_PARAM_TYPE_UINT8', -1),
        getattr(mavlink2, 'MAV_PARAM_TYPE_INT16', -1),
        getattr(mavlink2, 'MAV_PARAM_TYPE_UINT16', -1),
        getattr(mavlink2, 'MAV_PARAM_TYPE_INT32', -1),
        getattr(mavlink2, 'MAV_PARAM_TYPE_UINT32', -1),
    }
    real_types = {
        getattr(mavlink2, 'MAV_PARAM_TYPE_REAL32', -1),
    }

    if ptype in int_types:
        # Guard against NaN/Inf coming over the wire for int params
        if not math.isfinite(value):
            # Show as-is to avoid crashing, indicate non-finite
            return str(value)
        integer = int(value)
        # Boolean hint for 0/1 values on 8-bit params
        if ptype == getattr(mavlink2, 'MAV_PARAM_TYPE_UINT8', -2) and integer in (0, 1):
            return f"{integer} ({'true' if integer == 1 else 'false'})"
        # Bitmask hint when parameter name suggests a mask
        if param.name.upper().endswith('_MASK'):
            return f"{integer} (0x{integer:X})"
        return str(integer)

    if ptype in real_types:
        if not math.isfinite(value):
            return str(value)
        return fmt_float(value)

    # Fallback
    return fmt_float(value)

def list_parameters(handler: MAVLinkHandler) -> str:
    """Lists all parameters."""
    params = handler.get_all_parameters()
    if not params:
        return "No parameters loaded. Try refreshing."
    
    output = [f"📋 All Parameters ({len(params)}):", "-" * 60]
    for name, param in sorted(params.items()):
        display = _format_value_for_display(param)
        output.append(f"  {name:<30} = {display}")
    return "\n".join(output)

def search_parameters(handler: MAVLinkHandler, search_term: str) -> str:
    """Searches parameters for a given term."""
    params = handler.get_all_parameters()
    if not params:
        return "No parameters loaded. Try refreshing."

    if not search_term:
        return "Please provide a search term."

    matches = [(n, p) for n, p in params.items() if search_term.upper() in n.upper()]
    if matches:
        output = [f"📋 Found {len(matches)} matches for '{search_term}':"]
        for name, param in sorted(matches):
            display = _format_value_for_display(param)
            output.append(f"  {name:<30} = {display}")
        return "\n".join(output)
    else:
        return f"❌ No matches for '{search_term}'"

def read_parameter(handler: MAVLinkHandler, param_name: str) -> str:
    """Reads a specific parameter, from cache or drone."""
    if not param_name:
        return "Please provide a parameter name."

    cached = handler.get_parameter(param_name)
    if cached:
        return f"✅ {param_name} = {_format_value_for_display(cached)} (cached)"

    if handler.request_parameter(param_name):
        for _ in range(20):  # Try for 2 seconds
            handler.process_messages(0.1)
            time.sleep(0.1)
            result = handler.get_parameter(param_name)
            if result:
                handler.get_all_parameters()[param_name] = result  # Update cache
                return f"✅ {param_name} = {_format_value_for_display(result)} (from drone)"
        return f"❌ Could not read {param_name} from drone."
    else:
        return f"❌ Failed to send request for {param_name}."

def change_parameter(handler: MAVLinkHandler, param_name: str, new_value_str: str, force: bool = False) -> str:
    """Changes a parameter value, with interactive confirmation unless forced."""
    if not param_name or not new_value_str:
        return "Parameter name and new value cannot be empty."

    current = handler.get_parameter(param_name)
    if not current:
        read_result = read_parameter(handler, param_name)
        if "❌" in read_result:
            return f"❌ Could not read current value of {param_name} before changing."
        current = handler.get_parameter(param_name)

    if not current:
         return f"❌ Could not retrieve {param_name}."

    try:
        new_value = float(new_value_str)
    except ValueError:
        return "❌ Invalid number format for new value."

    if not force:
        print(f"\n⚠️  CONFIRMATION:")
        print(f"   Parameter: {param_name}")
        print(f"   Current:   {current.value}")
        print(f"   New:       {new_value}")
        print("🚨 WARNING: This can affect flight behavior!")
        
        confirm = input("Are you sure? (yes/no): ").lower()
        if confirm not in ['yes', 'y']:
            return "❌ Change cancelled by user."

    # Use the parameter's native MAVLink type when sending, fallback to default if missing
    param_type = getattr(current, 'param_type', None)
    try:
        # Ensure we always pass a valid MAV_PARAM_TYPE integer
        if isinstance(param_type, int):
            send_type = param_type
        else:
            from pymavlink.dialects.v20 import common as _mav2
            send_type = getattr(_mav2, 'MAV_PARAM_TYPE_REAL32')
    except Exception:
        # Fallback if pymavlink import fails
        send_type = param_type if isinstance(param_type, int) else 9  # 9 == REAL32 in MAVLink v2

    if handler.set_parameter(param_name, new_value, send_type):
        # Verification loop
        time.sleep(1)
        handler.request_parameter(param_name)
        for _ in range(20):
            handler.process_messages(0.1)
            time.sleep(0.1)
            verify = handler.get_parameter(param_name)
            if verify and abs(verify.value - new_value) < 0.001:
                handler.get_all_parameters()[param_name] = verify  # Update cache
                # Auto-set SYS_AUTOCONFIG=1 to persist configuration, unless we're already setting it
                if param_name.upper() != 'SYS_AUTOCONFIG':
                    try:
                        _ = change_parameter(handler, 'SYS_AUTOCONFIG', '1', force=True)
                    except Exception:
                        pass
                return f"✅ Verified change: {param_name} is now {verify.value}."
        return f"⚠️  Command sent, but could not verify the change for {param_name}."
    else:
        return f"❌ Failed to send set_parameter command for {param_name}."

def refresh_parameters(handler: MAVLinkHandler) -> str:
    """Refreshes the parameter list from the drone."""
    if handler.request_parameter_list():
        start_time = time.time()
        params = handler.get_all_parameters()
        initial_count = len(params)
        while time.time() - start_time < 15:
            handler.process_messages(0.1)
            time.sleep(0.1) # Give time for messages to arrive
            new_params = handler.get_all_parameters()
            if len(new_params) > initial_count:
                params = new_params
        return f"✅ Refreshed! Now holding {len(params)} parameters."
    else:
        return "❌ Failed to send parameter refresh request."

def interactive_parameter_editor():
    """Interactive parameter editor using MAVLinkHandler directly."""
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    handler = None
    try:
        handler = MAVLinkHandler()
        
        print("🔗 Connecting to PX4...")
        if not handler.connect():
            print("❌ Connection failed!")
            print("\n🔧 Troubleshooting:")
            print("- Make sure your drone is powered on")
            print("- Check USB cable connection")
            print("- Close QGroundControl or other software")
            return
        
        print(f"✅ Connected to {handler.config.port} at {handler.config.baudrate} baud")
        
        refresh_parameters(handler)

        while True:
            print("\n" + "="*50)
            print("🛠️  PX4 PARAMETER EDITOR")
            print("="*50)
            print("1. List all parameters")
            print("2. Search parameters")
            print("3. Read specific parameter")
            print("4. Change parameter value")
            print("5. Refresh parameter list")
            print("6. Exit")
            print("-" * 50)
            
            try:
                choice = input("Enter choice (1-6): ").strip()
                
                if choice == "1":
                    print(list_parameters(handler))
                
                elif choice == "2":
                    search_term = input("🔍 Enter search term: ").strip()
                    print(search_parameters(handler, search_term))
                
                elif choice == "3":
                    param_name = input("📖 Enter parameter name: ").strip()
                    print(read_parameter(handler, param_name))
                
                elif choice == "4":
                    param_name = input("🔧 Enter parameter name: ").strip()
                    new_value_str = input(f"🔧 New value: ").strip()
                    print(change_parameter(handler, param_name, new_value_str))

                elif choice == "5":
                    print(refresh_parameters(handler))
                
                elif choice == "6":
                    print("👋 Goodbye!")
                    break
                
                else:
                    print("❌ Invalid choice")
                    
            except KeyboardInterrupt:
                print("\n👋 Interrupted by user")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        if handler:
            handler.disconnect()
            print("🔌 Disconnected")

if __name__ == "__main__":
    interactive_parameter_editor()