#!/usr/bin/env python3
"""
Victron Gateway Node Class for Polyglot v3
Contains gateway (Cerbo GX, Venus GX) node definition
"""
import udi_interface
import json

LOGGER = udi_interface.LOGGER

class VictronGateway(udi_interface.Node):
    """Gateway node (Cerbo GX, Venus GX) that shows firmware version"""
    
    def __init__(self, polyglot, primary, address, name):
        super().__init__(polyglot, primary, address, name)
        self.name = name
        self.poly = polyglot
        self.system_status = 1              # System status (0=offline, 1=online, 2=alarm)
        self.firmware_version = "0.0.0"     # Firmware version
        self.active_alarms = 0              # Number of active alarms
        self.connected_devices = 0          # Number of connected devices
        self.vrm_connected = 0              # VRM connection status (0=disconnected, 1=connected)
        # New additional properties
        self.free_disk_space = 0            # Free disk space in MB
        self.network_type = 0               # Network connection type (0=None, 1=Ethernet, 2=WiFi, 3=Modem)
        self.ess_battery_state = "0x00"     # ESS Battery Life State (hex string)
        self.ess_soc_limit = 0.0           # ESS SOC Limit (percentage)
        self.services_status = "0x00"       # Services status bitmask (hex string)
        self.system_errors = 0              # System error count
        self.grid_setpoint = 0              # Grid setpoint in watts
        self.relay_states = "0x00"          # Relay states bitmask (hex string)
        self.device_info = None             # Device info from system overview
        self.vrm_client = None              # Will be set by parent controller
        self.installation_id = None         # Will be set by parent controller

    def start(self):
        """Called when Victron Gateway starts"""
        LOGGER.info(f"Starting Victron Gateway: {self.name}")
        
        # Try to get real data from VRM API
        self.update_from_vrm()
        
        # Set initial values (either from VRM or defaults)
        self.setDriver('ST', self.system_status, 25)           # System status
        self.setDriver('GV0', self.firmware_version, 56)       # Firmware version
        self.setDriver('GV1', self.active_alarms, 56)          # Active alarms count
        self.setDriver('GV2', self.connected_devices, 56)      # Connected devices count
        self.setDriver('GV3', self.vrm_connected, 2)           # VRM connection (bool)
        self.setDriver('GV4', self.free_disk_space, 56)        # Free disk space (MB)
        self.setDriver('GV5', self.network_type, 25)           # Network type (enum)
        self.setDriver('GV6', self.ess_battery_state, 56)      # ESS Battery Life State (hex)
        self.setDriver('GV7', self.ess_soc_limit, 51)          # ESS SOC Limit (%)
        self.setDriver('GV8', self.services_status, 56)        # Services status (hex)
        self.setDriver('GV9', self.system_errors, 56)          # System error count
        self.setDriver('GV10', self.grid_setpoint, 73)         # Grid setpoint (watts)
        self.setDriver('GV11', self.relay_states, 56)          # Relay states (hex)
        self.reportDrivers()
        
        LOGGER.info(f"Victron Gateway {self.name} started successfully")

    def update_from_vrm(self):
        """Update gateway data from VRM API"""
        try:
            if not self.vrm_client or not self.installation_id:
                LOGGER.debug(f"No VRM client available for {self.name}, using defaults")
                return
                
            LOGGER.debug(f"Getting status from Victron for {self.name}")
            
            # Get diagnostics data for detailed gateway information
            diagnostics_data = self.vrm_client.get_diagnostics_data(self.installation_id)
            if diagnostics_data:
                self.parse_diagnostics_data(diagnostics_data)
            
            # Get system overview data
            overview_data = self.vrm_client.get_system_overview(self.installation_id)
            if overview_data:
                self.parse_overview_data(overview_data)
                
                # Count connected devices from overview data
                records = overview_data.get('records', {})
                devices = records.get('devices', [])
                self.connected_devices = len(devices)
                LOGGER.debug(f"Gateway {self.name} - {self.connected_devices} connected devices")
                
            # Assume VRM connected if we got data
            self.vrm_connected = 1
            self.system_status = 1  # Online
            
            # Update all drivers with current values
            self.setDriver('ST', self.system_status, 25)           
            self.setDriver('GV0', self.firmware_version, 56)       
            self.setDriver('GV1', self.active_alarms, 56)          
            self.setDriver('GV2', self.connected_devices, 56)      
            self.setDriver('GV3', self.vrm_connected, 2)           
            self.setDriver('GV4', self.free_disk_space, 56)        
            self.setDriver('GV5', self.network_type, 25)           
            self.setDriver('GV6', self.ess_battery_state, 56)      
            self.setDriver('GV7', self.ess_soc_limit, 51)          
            self.setDriver('GV8', self.services_status, 56)        
            self.setDriver('GV9', self.system_errors, 56)          
            self.setDriver('GV10', self.grid_setpoint, 73)         
            self.setDriver('GV11', self.relay_states, 56)          
            self.reportDrivers()
            
            # Single summary info message for gateway
            LOGGER.info(f"Gateway {self.name}: Online, {self.connected_devices} devices, Disk: {self.free_disk_space}MB, Net: {self.network_type}, ESS: {self.ess_battery_state}")
            
        except Exception as ex:
            LOGGER.exception(f"Failed to update {self.name} from VRM API: {ex}")
            self.vrm_connected = 0
            self.system_status = 0  # Offline

    def update_from_shared_data(self, shared_diagnostics_data):
        """Update from shared diagnostics data (efficient polling method)"""
        try:
            LOGGER.debug(f"Updating node {self.name}")
            
            # Try to parse shared diagnostics data first
            if shared_diagnostics_data:
                LOGGER.debug(f"Gateway parsing shared diagnostics data for {self.name}")
                self.parse_diagnostics_data(shared_diagnostics_data)
            
            # Gateway typically uses system overview, not diagnostics, so fall back to individual call
            LOGGER.debug(f"Gateway uses overview data, falling back to individual VRM call for {self.name}")
            self.update_from_vrm()
            
        except Exception as ex:
            LOGGER.exception(f"Failed to update {self.name} from shared data: {ex}")
            # Final fallback to individual update
            try:
                self.update_from_vrm()
            except Exception as fallback_ex:
                LOGGER.error(f"Fallback update also failed for {self.name}: {fallback_ex}")

    def parse_diagnostics_data(self, diagnostics_data):
        """Parse diagnostics data for gateway-specific information
        
        Hex Value Mappings:
        ESS Battery Life State (GV6):
        - 0x00 = External control/BL disabled
        - 0x01 = Restarting
        - 0x02 = Self-consumption  
        - 0x05 = Discharged
        - 0x08 = Auto-recharge
        
        Services Status Bitmask (GV8):
        - Bit 0 (0x01) = MQTT Local
        - Bit 1 (0x02) = VNC Internet  
        - Bit 2 (0x04) = Remote Support
        - Bit 3 (0x08) = SignalK
        
        Relay States Bitmask (GV11):
        - Bit 0 (0x01) = Relay 1 (1=closed, 0=open)
        - Bit 1 (0x02) = Relay 2 (1=closed, 0=open)
        """
        try:
            LOGGER.debug(f"===== GATEWAY PARSING DIAGNOSTICS DATA for {self.name} =====")
            LOGGER.debug(f"Total diagnostics records received: {len(diagnostics_data.get('records', [])) if diagnostics_data else 0}")
            
            if not diagnostics_data or 'records' not in diagnostics_data:
                LOGGER.warning(f"No diagnostics records for {self.name}")
                return
            
            # Look for Gateway instance 0 records
            gateway_records = []
            for record in diagnostics_data['records']:
                if (record.get('Device') == 'Gateway' and 
                    record.get('instance') == 0):
                    gateway_records.append(record)
            
            LOGGER.debug(f"Found {len(gateway_records)} Gateway records")
            
            if not gateway_records:
                LOGGER.warning(f"No Gateway records found in diagnostics data")
                return
            
            # Parse gateway-specific fields with hex formatting for enums
            for record in gateway_records:
                description = record.get('description', '').lower()
                raw_value = record.get('rawValue')
                original_description = record.get('description', '')
                
                if raw_value is not None:
                    # Free disk space (Data partition free space)
                    if 'data partition free space' in description:
                        # Convert bytes to MB
                        self.free_disk_space = int(raw_value / (1024 * 1024))
                        LOGGER.debug(f"Found disk space: {self.free_disk_space}MB ({raw_value} bytes)")
                    
                    # Network connection type (Default gateway)
                    elif 'default gateway' in description:
                        self.network_type = int(raw_value)
                        LOGGER.debug(f"Found network type: {self.network_type} ({original_description})")
                    
                    # ESS Battery Life State (hex format)
                    elif 'ess battery life state' in description:
                        self.ess_battery_state = f"0x{int(raw_value):02X}"
                        LOGGER.debug(f"Found ESS battery state: {self.ess_battery_state} ({raw_value}) - {original_description}")
                    
                    # ESS SOC Limit
                    elif 'ess battery life soc limit' in description:
                        self.ess_soc_limit = float(raw_value)
                        LOGGER.debug(f"Found ESS SOC limit: {self.ess_soc_limit}%")
                    
                    # Grid setpoint
                    elif 'grid setpoint' in description:
                        self.grid_setpoint = int(raw_value)
                        LOGGER.debug(f"Found grid setpoint: {self.grid_setpoint}W")
                    
                    # Services status (build bitmask)
                    elif description in ['mqtt local (https)', 'vnc internet', 'remote support', 'signalk']:
                        # Build services bitmask progressively
                        current_services = int(self.services_status.replace('0x', ''), 16) if self.services_status != "0x00" else 0
                        
                        if 'mqtt local' in description and raw_value == 1:
                            current_services |= 0x01  # Bit 0: MQTT
                        elif 'vnc internet' in description and raw_value == 1:
                            current_services |= 0x02  # Bit 1: VNC
                        elif 'remote support' in description and raw_value == 1:
                            current_services |= 0x04  # Bit 2: Remote Support
                        elif 'signalk' in description and raw_value == 1:
                            current_services |= 0x08  # Bit 3: SignalK
                        
                        self.services_status = f"0x{current_services:02X}"
                        LOGGER.debug(f"Updated services status: {self.services_status} (processed {description})")
                    
                    # Relay states
                    elif 'relay 1 state' in description:
                        relay1_state = int(raw_value)
                        # Get current relay2 state or default to 0
                        current_relays = int(self.relay_states.replace('0x', ''), 16) if self.relay_states != "0x00" else 0
                        current_relays = (current_relays & 0x02) | relay1_state  # Update bit 0
                        self.relay_states = f"0x{current_relays:02X}"
                        LOGGER.debug(f"Updated relay states: {self.relay_states} (relay1={relay1_state})")
                        
                    elif 'ccgx relay 2 state' in description or 'relay 2 state' in description:
                        relay2_state = int(raw_value) << 1  # Shift to bit 1
                        # Get current relay1 state or default to 0
                        current_relays = int(self.relay_states.replace('0x', ''), 16) if self.relay_states != "0x00" else 0
                        current_relays = (current_relays & 0x01) | relay2_state  # Update bit 1
                        self.relay_states = f"0x{current_relays:02X}"
                        LOGGER.debug(f"Updated relay states: {self.relay_states} (relay2={relay2_state >> 1})")
                    
                    # System errors (combine hung and zombie processes)
                    elif 'hung processes' in description:
                        hung_processes = int(raw_value)
                        self.system_errors = hung_processes  # Will add zombie processes if found
                        LOGGER.debug(f"Found hung processes: {hung_processes}")
                        
                    elif 'zombie processes' in description:
                        zombie_processes = int(raw_value)
                        self.system_errors += zombie_processes  # Add to hung processes
                        LOGGER.debug(f"Found zombie processes: {zombie_processes}, total errors: {self.system_errors}")
                    
                    # Firmware version
                    elif 'fw version' in description:
                        version_str = str(raw_value)
                        self.firmware_version = version_str.lstrip('v')
                        LOGGER.debug(f"Found firmware version: {self.firmware_version}")
            
            LOGGER.debug(f"===== GATEWAY DIAGNOSTICS PARSING COMPLETE for {self.name} =====")
            LOGGER.debug(f"Final values - Disk: {self.free_disk_space}MB, Net: {self.network_type}, ESS: {self.ess_battery_state}, Services: {self.services_status}, Relays: {self.relay_states}")
                        
        except Exception as ex:
            LOGGER.exception(f"Failed to parse diagnostics data for {self.name}: {ex}")

    def parse_overview_data(self, overview_data):
        """Parse system overview data for gateway"""
        try:
            LOGGER.debug(f"===== GATEWAY PARSING OVERVIEW DATA for {self.name} =====")
            LOGGER.debug(f"Overview data JSON: {json.dumps(overview_data, indent=2) if overview_data else 'None'}")
            LOGGER.debug(f"Data type: {type(overview_data)}")
            
            if not overview_data:
                LOGGER.warning(f"No overview data to parse for {self.name}")
                return
            
            found_fields = []
            
            # Handle nested API response structure
            actual_data = overview_data
            if 'records' in overview_data and 'devices' in overview_data['records']:
                devices = overview_data['records']['devices']
                if isinstance(devices, list) and len(devices) > 0:
                    # Find the gateway device
                    gateway_device = None
                    for device in devices:
                        if device.get('name') == 'Gateway' or 'gateway' in device.get('identifier', '').lower():
                            gateway_device = device
                            break
                    
                    if gateway_device:
                        actual_data = gateway_device
                        LOGGER.debug(f"Found gateway device data: {gateway_device.get('productName', 'Unknown')}")
            
            # Look for firmware version
            if 'firmware_version' in actual_data:
                version_str = str(actual_data['firmware_version'])
                # Remove 'v' prefix if present
                self.firmware_version = version_str.lstrip('v')
                found_fields.append(f"firmware_version: {self.firmware_version}")
                LOGGER.info(f"Gateway {self.name} firmware version: {self.firmware_version}")
            elif 'firmwareVersion' in actual_data:
                version_str = str(actual_data['firmwareVersion'])
                # Remove 'v' prefix if present
                self.firmware_version = version_str.lstrip('v')
                found_fields.append(f"firmwareVersion: {self.firmware_version}")
                LOGGER.info(f"Gateway {self.name} firmware version: {self.firmware_version}")
            elif 'version' in actual_data:
                version_str = str(actual_data['version'])
                # Remove 'v' prefix if present
                self.firmware_version = version_str.lstrip('v')
                found_fields.append(f"version: {self.firmware_version}")
                LOGGER.info(f"Gateway {self.name} firmware version: {self.firmware_version}")
                
            # Look for alarm information
            if 'alarms' in actual_data:
                alarms = actual_data['alarms']
                if isinstance(alarms, list):
                    self.active_alarms = len(alarms)
                elif isinstance(alarms, int):
                    self.active_alarms = alarms
                found_fields.append(f"alarms: {self.active_alarms}")
                LOGGER.debug(f"Gateway {self.name} active alarms: {self.active_alarms}")
                
            # Summary of what was found and processed
            if found_fields:
                LOGGER.debug(f"Successfully processed {len(found_fields)} fields for {self.name}: {', '.join(found_fields)}")
            else:
                LOGGER.warning(f"No recognizable gateway data fields found for {self.name}")
                LOGGER.debug(f"Available keys in data: {list(overview_data.keys()) if isinstance(overview_data, dict) else 'Not a dict'}")
                
            LOGGER.debug(f"===== END GATEWAY PARSING for {self.name} =====")
                
            # Check if we have any alarms to set system status
            if self.active_alarms > 0:
                self.system_status = 2  # Alarm state
            else:
                self.system_status = 1  # Normal operation
                
        except Exception as ex:
            LOGGER.exception(f"Failed to parse overview data for {self.name}: {ex}")

    def query(self, command=None):
        """Called when ISY queries gateway"""
        LOGGER.info(f"Updating node {self.name}")
        
        # Try to get cached VRM data from controller first
        try:
            controller = self.poly.getNode('controller')
            if controller and hasattr(controller, 'get_cached_vrm_data'):
                shared_data = controller.get_cached_vrm_data()
                if shared_data:
                    LOGGER.debug(f"Using cached VRM data for {self.name}")
                    self.update_from_shared_data(shared_data)
                else:
                    # Fall back to individual VRM call
                    LOGGER.debug(f"No cached data available, falling back to individual VRM call for {self.name}")
                    self.update_from_vrm()
            else:
                # Fall back to individual VRM call
                self.update_from_vrm()
        except Exception as ex:
            LOGGER.warning(f"Failed to get cached data for {self.name}, falling back to individual call: {ex}")
            self.update_from_vrm()
        
        # Update drivers with all new values
        self.setDriver('ST', self.system_status, 25)
        self.setDriver('GV0', self.firmware_version, 56)
        self.setDriver('GV1', self.active_alarms, 56)
        self.setDriver('GV2', self.connected_devices, 56)
        self.setDriver('GV3', self.vrm_connected, 2)
        self.setDriver('GV4', self.free_disk_space, 56)
        self.setDriver('GV5', self.network_type, 25)
        self.setDriver('GV6', self.ess_battery_state, 56)
        self.setDriver('GV7', self.ess_soc_limit, 51)
        self.setDriver('GV8', self.services_status, 56)
        self.setDriver('GV9', self.system_errors, 56)
        self.setDriver('GV10', self.grid_setpoint, 73)
        self.setDriver('GV11', self.relay_states, 56)
        self.reportDrivers()

    def shortPoll(self):
        """Called every shortPoll seconds"""
        LOGGER.debug(f"Gateway {self.name} - shortPoll triggered")
        self.query()

    def longPoll(self):
        """Called every longPoll seconds"""
        LOGGER.debug(f"Gateway {self.name} - longPoll triggered")
        self.query()



    # Define the drivers (status values) for this node
    drivers = [
        {'driver': 'ST', 'value': 1, 'uom': 25},        # System status (0=offline, 1=online, 2=alarm)
        {'driver': 'GV0', 'value': "0.0.0", 'uom': 56}, # Firmware version string
        {'driver': 'GV1', 'value': 0, 'uom': 56},       # Active alarms count
        {'driver': 'GV2', 'value': 0, 'uom': 56},       # Connected devices count
        {'driver': 'GV3', 'value': 0, 'uom': 2},        # VRM connection (0=disconnected, 1=connected)
        {'driver': 'GV4', 'value': 0, 'uom': 56},       # Free disk space (MB)
        {'driver': 'GV5', 'value': 0, 'uom': 25},       # Network type (0=None, 1=Ethernet, 2=WiFi, 3=Modem)
        {'driver': 'GV6', 'value': "0x00", 'uom': 56},  # ESS Battery Life State (hex)
        {'driver': 'GV7', 'value': 0, 'uom': 51},       # ESS SOC Limit (%)
        {'driver': 'GV8', 'value': "0x00", 'uom': 56},  # Services status bitmask (hex)
        {'driver': 'GV9', 'value': 0, 'uom': 56},       # System error count
        {'driver': 'GV10', 'value': 0, 'uom': 73},      # Grid setpoint (watts)
        {'driver': 'GV11', 'value': "0x00", 'uom': 56}  # Relay states bitmask (hex)
    ]

    # Define the node ID (must match nodedef)
    id = 'VicGateway'

    # Define the commands this node supports
    commands = {
        'QUERY': query
    }
