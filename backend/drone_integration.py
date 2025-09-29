"""
Integration layer between backend orchestrator and drone operations.
This module provides a clean interface for executing parameter operations
from the LLM backend through the drone communication layer.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import threading
import time

logger = logging.getLogger(__name__)

# Import drone operations with error handling
try:
    from drone.mavlink_handler import MAVLinkHandler, ConnectionConfig
    from drone.param_manager import (
        change_parameter,
        list_parameters,
        read_parameter,
        refresh_parameters,
        search_parameters,
    )
    DRONE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Drone module not available: {e}")
    DRONE_AVAILABLE = False

@dataclass
class DroneOperationResult:
    """Result of a drone operation"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class DroneIntegration:
    """
    Integration layer for executing drone operations from the backend.
    Handles connection management and operation execution.
    """
    
    def __init__(self):
        self.mav_handler: Optional[MAVLinkHandler] = None
        self.is_connected = False
        self.connection_config: Optional[ConnectionConfig] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_stop = threading.Event()
        self._last_connect_attempt = 0.0
        self._connect_backoff_s = 2.0
    
    def connect(self, port: Optional[str] = None, baudrate: int = 57600) -> DroneOperationResult:
        """Connect to the drone (auto-detect port if not provided)."""
        if not DRONE_AVAILABLE:
            return DroneOperationResult(
                success=False,
                message="Drone module not available",
                error="Drone module not installed"
            )
        
        try:
            # Create/update connection config
            self.connection_config = ConnectionConfig(
                port=port or "",
                baudrate=baudrate,
                timeout=5.0,
                retries=3
            )
            
            # Create and connect MAVLink handler
            self.mav_handler = MAVLinkHandler(self.connection_config)
            connect_port = port or None
            if self.mav_handler.connect(connect_port, baudrate):
                self.is_connected = True
                logger.info("Successfully connected to drone")
                # Start background processing loop
                self._ensure_loop_running()
                return DroneOperationResult(
                    success=True,
                    message="Connected to drone successfully"
                )
            else:
                return DroneOperationResult(
                    success=False,
                    message="Failed to connect to drone",
                    error="Connection timeout or communication error"
                )
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return DroneOperationResult(
                success=False,
                message="Connection failed",
                error=str(e)
            )
    
    def disconnect(self) -> DroneOperationResult:
        """Disconnect from the drone"""
        if self.mav_handler:
            try:
                self.mav_handler.disconnect()
                self.is_connected = False
                self._stop_loop()
                logger.info("Disconnected from drone")
                return DroneOperationResult(
                    success=True,
                    message="Disconnected from drone"
                )
            except Exception as e:
                logger.error(f"Disconnect error: {e}")
                return DroneOperationResult(
                    success=False,
                    message="Error during disconnect",
                    error=str(e)
                )
        else:
            return DroneOperationResult(
                success=True,
                message="Not connected"
            )
    
    def execute_operation(self, operation: str, **kwargs) -> DroneOperationResult:
        """Execute a drone operation"""
        if not self.is_connected or not self.mav_handler:
            return DroneOperationResult(
                success=False,
                message="Not connected to drone",
                error="Must connect to drone first"
            )
        
        if not DRONE_AVAILABLE:
            return DroneOperationResult(
                success=False,
                message="Drone module not available",
                error="Drone module not installed"
            )
        
        try:
            if operation == "list_parameters":
                result = list_parameters(self.mav_handler)
                return DroneOperationResult(
                    success=True,
                    message="Parameter list retrieved",
                    data={"result": result}
                )
            
            elif operation == "search_parameters":
                search_term = kwargs.get("search_term", "")
                result = search_parameters(self.mav_handler, search_term)
                return DroneOperationResult(
                    success=True,
                    message=f"Search completed for '{search_term}'",
                    data={"result": result, "search_term": search_term}
                )
            
            elif operation == "read_parameter":
                param_name = kwargs.get("param_name", "")
                if not param_name:
                    return DroneOperationResult(
                        success=False,
                        message="Parameter name required",
                        error="Missing parameter_name"
                    )
                
                result = read_parameter(self.mav_handler, param_name)
                return DroneOperationResult(
                    success=True,
                    message=f"Parameter '{param_name}' read",
                    data={"result": result, "param_name": param_name}
                )
            
            elif operation == "change_parameter":
                param_name = kwargs.get("param_name", "")
                new_value = kwargs.get("new_value", "")
                force = kwargs.get("force", False)
                
                if not param_name or new_value is None:
                    return DroneOperationResult(
                        success=False,
                        message="Parameter name and value required",
                        error="Missing param_name or new_value"
                    )
                
                result = change_parameter(self.mav_handler, param_name, str(new_value), force=force)
                return DroneOperationResult(
                    success=True,
                    message=f"Parameter '{param_name}' changed to {new_value}",
                    data={"result": result, "param_name": param_name, "new_value": new_value}
                )
            
            elif operation == "refresh_parameters":
                result = refresh_parameters(self.mav_handler)
                return DroneOperationResult(
                    success=True,
                    message="Parameters refreshed from drone",
                    data={"result": result}
                )
            
            else:
                return DroneOperationResult(
                    success=False,
                    message=f"Unknown operation: {operation}",
                    error="Invalid operation"
                )
                
        except Exception as e:
            logger.error(f"Operation error: {e}")
            return DroneOperationResult(
                success=False,
                message=f"Operation '{operation}' failed",
                error=str(e)
            )
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status"""
        return {
            "connected": self.is_connected,
            "port": self.connection_config.port if self.connection_config else None,
            "baudrate": self.connection_config.baudrate if self.connection_config else None,
            "drone_available": DRONE_AVAILABLE
        }

    def get_parameters_snapshot(self) -> Dict[str, Any]:
        """Return a lightweight snapshot of parameters {name: value}"""
        snapshot: Dict[str, Any] = {}
        try:
            if self.mav_handler:
                for name, info in self.mav_handler.get_all_parameters().items():
                    snapshot[name] = info.value
        except Exception:
            pass
        return snapshot

    def _ensure_loop_running(self) -> None:
        if self._loop_thread and self._loop_thread.is_alive():
            return
        self._loop_stop.clear()
        self._loop_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._loop_thread.start()

    def _stop_loop(self) -> None:
        self._loop_stop.set()
        if self._loop_thread and self._loop_thread.is_alive():
            try:
                self._loop_thread.join(timeout=1.0)
            except Exception:
                pass

    def _processing_loop(self) -> None:
        """Continuously process MAVLink messages and handle reconnection & auto-refresh."""
        last_refresh = 0.0
        while not self._loop_stop.is_set():
            try:
                if self.mav_handler and self.is_connected:
                    # Process inbound messages
                    self.mav_handler.process_messages(0.05)

                    # Auto request list if cache is empty, with throttling
                    if len(self.mav_handler.get_all_parameters()) == 0:
                        now = time.time()
                        if now - last_refresh > 2.0:
                            try:
                                self.mav_handler.request_parameter_list()
                                last_refresh = now
                            except Exception:
                                pass
                else:
                    # Attempt reconnect with backoff
                    now = time.time()
                    if now - self._last_connect_attempt > self._connect_backoff_s and DRONE_AVAILABLE:
                        self._last_connect_attempt = now
                        try:
                            # Recreate handler if missing
                            if self.mav_handler is None:
                                self.mav_handler = MAVLinkHandler(self.connection_config or ConnectionConfig(port="", baudrate=57600))
                            if self.mav_handler.connect(None, self.connection_config.baudrate if self.connection_config else 57600):
                                self.is_connected = True
                                logger.info("Reconnected to drone")
                        except Exception:
                            pass
                time.sleep(0.05)
            except Exception:
                time.sleep(0.2)

# Global instance for easy access
drone_integration = DroneIntegration()