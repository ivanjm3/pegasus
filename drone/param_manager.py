"""
Simplified Parameter Editor using existing MAVLinkHandler.
Much cleaner and uses your existing MAVLink infrastructure.
"""

import time
import logging
from mavlink_handler import MAVLinkHandler, ConnectionConfig

def interactive_parameter_editor():
    """Interactive parameter editor using MAVLinkHandler directly."""
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    try:
        # Create handler (it will auto-detect port)
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
        
        # Load parameters with better logic
        print("📥 Loading parameters...")
        if handler.request_parameter_list():
            # Process messages to receive parameters
            start_time = time.time()
            last_count = 0
            stable_count = 0
            
            while time.time() - start_time < 30:  # Longer timeout
                handler.process_messages(0.1)
                params = handler.get_all_parameters()
                
                # Show progress
                if len(params) != last_count:
                    if len(params) % 100 == 0:
                        print(f"   Loading... ({len(params)} parameters)")
                    last_count = len(params)
                    stable_count = 0
                else:
                    stable_count += 1
                
                # Stop if we haven't received new parameters for 3 seconds
                if stable_count > 30 and len(params) > 0:
                    print(f"   Parameter loading stabilized at {len(params)} parameters")
                    break
                    
                time.sleep(0.1)
        
        params = handler.get_all_parameters()
        print(f"📊 Loaded {len(params)} parameters")
        
        # Interactive loop
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
            print("-"*50)
            
            try:
                choice = input("Enter choice (1-6): ").strip()
                
                if choice == "1":
                    # List all parameters
                    if len(params) == 0:
                        print("No parameters loaded. Try option 5 to refresh.")
                        continue
                    
                    print(f"\n📋 All Parameters ({len(params)}):")
                    print("-"*60)
                    for name, param in sorted(params.items()):
                        print(f"  {name:<30} = {param.value}")
                
                elif choice == "2":
                    # Search parameters
                    if len(params) == 0:
                        print("No parameters loaded. Try option 5 to refresh.")
                        continue
                    
                    search = input("🔍 Enter search term: ").strip().upper()
                    if search:
                        matches = [(n, p) for n, p in params.items() if search in n.upper()]
                        if matches:
                            print(f"\n📋 Found {len(matches)} matches:")
                            for name, param in sorted(matches):
                                print(f"  {name:<30} = {param.value}")
                        else:
                            print(f"❌ No matches for '{search}'")
                
                elif choice == "3":
                    # Read specific parameter
                    param_name = input("📖 Enter parameter name: ").strip()
                    if param_name:
                        # Try from cache first
                        cached = handler.get_parameter(param_name)
                        if cached:
                            print(f"✅ {param_name} = {cached.value} (cached)")
                        else:
                            # Request from drone
                            print(f"📖 Requesting {param_name} from drone...")
                            if handler.request_parameter(param_name):
                                # Process messages briefly
                                for _ in range(20):  # Try for 2 seconds
                                    handler.process_messages(0.1)
                                    time.sleep(0.1)
                                    result = handler.get_parameter(param_name)
                                    if result:
                                        print(f"✅ {param_name} = {result.value}")
                                        params[param_name] = result  # Cache it
                                        break
                                else:
                                    print(f"❌ Could not read {param_name}")
                            else:
                                print(f"❌ Failed to request {param_name}")
                
                elif choice == "4":
                    # Change parameter
                    param_name = input("🔧 Enter parameter name: ").strip()
                    if not param_name:
                        continue
                    
                    # Get current value
                    current = handler.get_parameter(param_name)
                    if not current:
                        print(f"📖 Parameter {param_name} not in cache, requesting...")
                        if handler.request_parameter(param_name):
                            for _ in range(20):
                                handler.process_messages(0.1)
                                time.sleep(0.1)
                                current = handler.get_parameter(param_name)
                                if current:
                                    break
                        
                        if not current:
                            print(f"❌ Could not read {param_name}")
                            continue
                    
                    print(f"📊 Current: {param_name} = {current.value}")
                    
                    try:
                        new_value_str = input(f"🔧 New value: ").strip()
                        if not new_value_str:
                            continue
                        
                        new_value = float(new_value_str)
                        
                        # Confirm
                        print(f"\n⚠️  CONFIRMATION:")
                        print(f"   Parameter: {param_name}")
                        print(f"   Current:   {current.value}")
                        print(f"   New:       {new_value}")
                        print("🚨 WARNING: This can affect flight behavior!")
                        
                        if input("Are you sure? (yes/no): ").lower() in ['yes', 'y']:
                            print(f"🔄 Setting {param_name} = {new_value}...")
                            
                            if handler.set_parameter(param_name, new_value):
                                print("✅ Parameter set command sent")
                                
                                # Wait and verify
                                time.sleep(1)
                                handler.request_parameter(param_name)
                                
                                for _ in range(20):
                                    handler.process_messages(0.1)
                                    time.sleep(0.1)
                                    verify = handler.get_parameter(param_name)
                                    if verify and abs(verify.value - new_value) < 0.001:
                                        print(f"✅ Verified: {param_name} = {verify.value}")
                                        params[param_name] = verify  # Update cache
                                        break
                                else:
                                    print("⚠️  Could not verify the change")
                            else:
                                print("❌ Failed to set parameter")
                        else:
                            print("❌ Cancelled")
                    
                    except ValueError:
                        print("❌ Invalid number format")
                
                elif choice == "5":
                    # Refresh parameters
                    print("🔄 Refreshing parameters...")
                    if handler.request_parameter_list():
                        start_time = time.time()
                        while time.time() - start_time < 15:
                            handler.process_messages(0.1)
                            new_params = handler.get_all_parameters()
                            if len(new_params) > len(params):
                                params = new_params
                        print(f"✅ Refreshed! {len(params)} parameters")
                    else:
                        print("❌ Failed to refresh")
                
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
        try:
            handler.disconnect()
            print("🔌 Disconnected")
        except:
            pass


if __name__ == "__main__":
    interactive_parameter_editor()