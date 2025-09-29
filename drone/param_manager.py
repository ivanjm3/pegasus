"""
Simplified Parameter Editor using existing MAVLinkHandler.
Much cleaner and uses your existing MAVLink infrastructure.
"""

import time
import logging
from .mavlink_handler import MAVLinkHandler, ConnectionConfig

def list_parameters(handler: MAVLinkHandler) -> str:
    """Lists all parameters."""
    params = handler.get_all_parameters()
    if not params:
        return "No parameters loaded. Try refreshing."
    
    output = [f"📋 All Parameters ({len(params)}):", "-" * 60]
    for name, param in sorted(params.items()):
        output.append(f"  {name:<30} = {param.value}")
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
            output.append(f"  {name:<30} = {param.value}")
        return "\n".join(output)
    else:
        return f"❌ No matches for '{search_term}'"

def read_parameter(handler: MAVLinkHandler, param_name: str) -> str:
    """Reads a specific parameter, from cache or drone."""
    if not param_name:
        return "Please provide a parameter name."

    cached = handler.get_parameter(param_name)
    if cached:
        return f"✅ {param_name} = {cached.value} (cached)"

    if handler.request_parameter(param_name):
        for _ in range(20):  # Try for 2 seconds
            handler.process_messages(0.1)
            time.sleep(0.1)
            result = handler.get_parameter(param_name)
            if result:
                handler.get_all_parameters()[param_name] = result  # Update cache
                return f"✅ {param_name} = {result.value} (from drone)"
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

    if handler.set_parameter(param_name, new_value):
        # Verification loop
        time.sleep(1)
        handler.request_parameter(param_name)
        for _ in range(20):
            handler.process_messages(0.1)
            time.sleep(0.1)
            verify = handler.get_parameter(param_name)
            if verify and abs(verify.value - new_value) < 0.001:
                handler.get_all_parameters()[param_name] = verify  # Update cache
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