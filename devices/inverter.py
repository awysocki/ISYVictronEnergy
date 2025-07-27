#!/usr/bin/env python3
"""
Victron Inverter Node Class for Polyglot v3
Contains inverter (MultiPlus, Quattro, Phoenix) node definition
"""
import udi_interface
import requests

LOGGER = udi_interface.LOGGER

class VictronInverter(udi_interface.Node):
    """Inverter node (MultiPlus, Quattro, Phoenix) that gets data from VRM API"""
    
    def __init__(self, polyglot, primary, address, name):
        super().__init__(polyglot, primary, address, name)
        self.name = name
        self.poly = polyglot
        self.inverter_power = 0.0       # Inverter power output
        self.inverter_voltage = 0.0     # AC voltage 
        self.inverter_current = 0.0     # AC current
        self.inverter_state = 0         # Inverter state (0=Off, 1=On, 2=Invert, 3=Charge)
        self.inverter_frequency = 0.0   # AC frequency (Hz)
        self.inverter_temperature = 0.0 # Inverter temperature
        self.device_id = None           # Will be set by parent controller
        self.device_data = None         # Will be set by parent controller
        self.device_info = None         # Device info from system overview
        self.device_instance = None     # Device instance number
        self.overview_data = None       # Will be set for overview-based nodes
        self.vrm_client = None          # Will be set by parent controller
        self.installation_id = None     # Will be set by parent controller

    def start(self):
        """Called when Victron Inverter starts"""
        LOGGER.info(f"=== Victron Inverter Starting: {self.name} ===")
        
        # Try to get real data from VRM API
        self.update_from_vrm()
        
        # Set initial values (either from VRM or defaults)
        self.setDriver('ST', self.inverter_power, 73)      # Power in watts
        self.setDriver('GV0', self.inverter_state, 25)     # Inverter state
        self.setDriver('CV', self.inverter_voltage, 72)    # Voltage in volts (V)
        self.setDriver('CC', self.inverter_current, 1)     # Current in amperes (A)
        self.setDriver('CPW', int(self.inverter_frequency * 10), 90)  # Frequency in 0.1Hz units
        self.setDriver('CLITEMP', int(self.inverter_temperature * 10), 4)  # Temperature in 0.1C units
        self.reportDrivers()
        LOGGER.info(f"=== Victron Inverter Started: {self.name} ===")

    def update_from_vrm(self):
        """Update inverter data from VRM API"""
        try:
            # Similar to other devices but for inverter-specific data
            if self.device_instance and self.vrm_client and self.installation_id:
                LOGGER.info(f"Updating {self.name} using device instance {self.device_instance}...")
                # No device instance for inverters in this system, skip this path
                pass
            
            if self.overview_data:
                LOGGER.debug(f"Updating {self.name} from system overview data...")
                self.parse_overview_data(self.overview_data)
                return
                
            if self.device_info:
                LOGGER.info(f"Device info available for {self.name}: {self.device_info.get('productName', 'Unknown')}")
                
            if self.device_id and self.vrm_client and self.installation_id:
                LOGGER.info(f"Updating {self.name} from VRM API using device ID...")
                device_data = self.vrm_client.get_device_data(self.installation_id, self.device_id)
                if device_data:
                    self.parse_device_data(device_data)
                    return
                    
            LOGGER.info(f"No VRM update method available for {self.name}, using default values")
                
        except Exception as ex:
            LOGGER.exception(f"Failed to update {self.name} from VRM API: {ex}")

    def update_from_shared_data(self, shared_diagnostics_data):
        """Update from shared diagnostics data (efficient polling method)"""
        try:
            LOGGER.debug(f"Updating node {self.name}")
            
            # Try to parse shared diagnostics data first
            if shared_diagnostics_data:
                LOGGER.debug(f"Inverter parsing shared diagnostics data for {self.name}")
                # Inverters might have some diagnostics data, try to extract what we can
                # TODO: Implement parse_diagnostics_data for inverter if needed
                pass
            
            # Inverter typically uses widget/overview data, not diagnostics, so fall back to individual call
            LOGGER.debug(f"Inverter uses widget data, falling back to individual VRM call for {self.name}")
            self.update_from_vrm()
            
        except Exception as ex:
            LOGGER.exception(f"Failed to update {self.name} from shared data: {ex}")
            # Final fallback to individual update
            try:
                self.update_from_vrm()
            except Exception as fallback_ex:
                LOGGER.error(f"Fallback update also failed for {self.name}: {fallback_ex}")

    def parse_overview_data(self, overview_data):
        """Parse system overview data for inverter"""
        try:
            LOGGER.debug(f"Parsing overview data for {self.name}: {overview_data}")
            
            if 'power' in overview_data:
                self.inverter_power = float(overview_data['power'])
                LOGGER.info(f"Updated {self.name} inverter power: {self.inverter_power}W")
                
            if 'voltage' in overview_data:
                self.inverter_voltage = float(overview_data['voltage'])
                LOGGER.info(f"Updated {self.name} inverter voltage: {self.inverter_voltage}V")
                
            if 'current' in overview_data:
                self.inverter_current = float(overview_data['current'])
                LOGGER.info(f"Updated {self.name} inverter current: {self.inverter_current}A")
                
            if 'state' in overview_data:
                self.inverter_state = int(overview_data['state'])
                LOGGER.info(f"Updated {self.name} inverter state: {self.inverter_state}")
                
            if 'frequency' in overview_data:
                self.inverter_frequency = float(overview_data['frequency'])
                LOGGER.info(f"Updated {self.name} inverter frequency: {self.inverter_frequency}Hz")
                
            if 'temperature' in overview_data:
                self.inverter_temperature = float(overview_data['temperature'])
                LOGGER.info(f"Updated {self.name} inverter temperature: {self.inverter_temperature}°C")
                
        except Exception as ex:
            LOGGER.exception(f"Failed to parse overview data for {self.name}: {ex}")

    def parse_device_data(self, device_data):
        """Parse device data from VRM API for inverter"""
        try:
            # Handle widget data format (new official approach)
            if 'inverter_power' in device_data:
                self.inverter_power = float(device_data['inverter_power'])
                LOGGER.info(f"Updated {self.name} inverter power: {self.inverter_power}W")
            elif 'ac_power' in device_data:
                self.inverter_power = float(device_data['ac_power'])
                LOGGER.info(f"Updated {self.name} AC power: {self.inverter_power}W")
                
            if 'inverter_voltage' in device_data:
                self.inverter_voltage = float(device_data['inverter_voltage'])
                LOGGER.info(f"Updated {self.name} inverter voltage: {self.inverter_voltage}V")
            elif 'ac_voltage' in device_data:
                self.inverter_voltage = float(device_data['ac_voltage'])
                LOGGER.info(f"Updated {self.name} AC voltage: {self.inverter_voltage}V")
                
            if 'inverter_current' in device_data:
                self.inverter_current = float(device_data['inverter_current'])
                LOGGER.info(f"Updated {self.name} inverter current: {self.inverter_current}A")
            elif 'ac_current' in device_data:
                self.inverter_current = float(device_data['ac_current'])
                LOGGER.info(f"Updated {self.name} AC current: {self.inverter_current}A")
                
            if 'inverter_state' in device_data:
                self.inverter_state = int(device_data['inverter_state'])
                LOGGER.info(f"Updated {self.name} inverter state: {self.inverter_state}")
                
            if 'inverter_frequency' in device_data:
                self.inverter_frequency = float(device_data['inverter_frequency'])
                LOGGER.info(f"Updated {self.name} inverter frequency: {self.inverter_frequency}Hz")
            elif 'ac_frequency' in device_data:
                self.inverter_frequency = float(device_data['ac_frequency'])
                LOGGER.info(f"Updated {self.name} AC frequency: {self.inverter_frequency}Hz")
                
            if 'inverter_temperature' in device_data:
                self.inverter_temperature = float(device_data['inverter_temperature'])
                LOGGER.info(f"Updated {self.name} inverter temperature: {self.inverter_temperature}°C")
            
            # Handle legacy data format (fallback)
            if 'power' in device_data:
                self.inverter_power = float(device_data['power'])
                LOGGER.info(f"Updated {self.name} inverter power: {self.inverter_power}W")
                
            if 'voltage' in device_data:
                self.inverter_voltage = float(device_data['voltage'])
                LOGGER.info(f"Updated {self.name} inverter voltage: {self.inverter_voltage}V")
                
            if 'current' in device_data:
                self.inverter_current = float(device_data['current'])
                LOGGER.info(f"Updated {self.name} inverter current: {self.inverter_current}A")
                
            if 'state' in device_data:
                self.inverter_state = int(device_data['state'])
                LOGGER.info(f"Updated {self.name} inverter state: {self.inverter_state}")
                
            if 'frequency' in device_data:
                self.inverter_frequency = float(device_data['frequency'])
                LOGGER.info(f"Updated {self.name} inverter frequency: {self.inverter_frequency}Hz")
                
            if 'temperature' in device_data:
                self.inverter_temperature = float(device_data['temperature'])
                LOGGER.info(f"Updated {self.name} inverter temperature: {self.inverter_temperature}°C")
                
            # Look for nested data structures
            if isinstance(device_data, dict):
                for key, value in device_data.items():
                    if isinstance(value, dict):
                        self.parse_device_data(value)
                        
        except Exception as ex:
            LOGGER.exception(f"Failed to parse device data for {self.name}: {ex}")

    def query(self, command=None):
        """Called when ISY queries inverter"""
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
        
        if not self.vrm_client:
            import random
            self.inverter_power = max(0.0, min(3000.0, self.inverter_power + random.uniform(-50, 50)))
            self.inverter_voltage = max(110.0, min(125.0, self.inverter_voltage + random.uniform(-1, 1)))
            self.inverter_frequency = max(59.0, min(61.0, self.inverter_frequency + random.uniform(-0.1, 0.1)))
        
        self.setDriver('ST', self.inverter_power, 73)
        self.setDriver('GV0', self.inverter_state, 25)
        self.setDriver('CV', self.inverter_voltage, 72)
        self.setDriver('CC', self.inverter_current, 1)
        self.setDriver('CPW', int(self.inverter_frequency * 10), 90)
        self.setDriver('CLITEMP', int(self.inverter_temperature * 10), 4)
        self.reportDrivers()

    def shortPoll(self):
        """Called every shortPoll seconds"""
        self.query()

    def longPoll(self):
        """Called every longPoll seconds"""
        self.query()



    # Define the drivers (status values) for this node
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 73},       # Power in watts
        {'driver': 'GV0', 'value': 0, 'uom': 25},      # Inverter state (0=Off, 1=On, 2=Invert, 3=Charge)
        {'driver': 'CV', 'value': 0, 'uom': 72},       # Voltage in volts (V)
        {'driver': 'CC', 'value': 0, 'uom': 1},        # Current in amperes (A)
        {'driver': 'CPW', 'value': 0, 'uom': 90},      # Frequency in 0.1Hz units
        {'driver': 'CLITEMP', 'value': 0, 'uom': 4}    # Temperature in 0.1C units
    ]

    # Define the node ID (must match nodedef) - we'll use VicBatt for now
    id = 'VicBatt'

    # Define the commands this node supports
    commands = {
        'QUERY': query
    }
