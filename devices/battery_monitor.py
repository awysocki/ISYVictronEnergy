#!/usr/bin/env python3
"""
Victron Battery Monitor Node (SmartShunt, BMV, etc.)
"""
import udi_interface
import requests
import json

LOGGER = udi_interface.LOGGER

class VictronBatteryMonitor(udi_interface.Node):
    """Battery monitor node (SmartShunt, BMV, etc.) that gets data from VRM API"""
    
    def __init__(self, polyglot, primary, address, name):
        super().__init__(polyglot, primary, address, name)
        self.name = name
        self.poly = polyglot
        self.battery_percentage = 0.0  # Default/fallback value
        self.battery_voltage = 0.0     # Default/fallback value
        self.battery_current = 0.0      # Battery current
        self.battery_power = 0.0        # Battery power
        self.battery_temperature = 0.0 # Battery temperature
        # Alarm states (0 = no alarm, 1 = alarm active)
        self.low_voltage_alarm = 0
        self.high_voltage_alarm = 0
        self.low_soc_alarm = 0
        self.low_temp_alarm = 0
        self.high_temp_alarm = 0
        self._device_id = None           # Will be set by parent controller
        self.device_data = None         # Will be set by parent controller
        self._device_info = None         # Device info from system overview
        self._device_instance = None     # Device instance number
        self.overview_data = None       # Will be set for overview-based nodes
        self._vrm_client = None          # Will be set by parent controller
        self._installation_id = None     # Will be set by parent controller
        self._temp_unit = 'C'             # Temperature unit preference (C or F)
        LOGGER.debug(f"Battery monitor {self.name} constructor completed")

    @property
    def temp_unit(self):
        return self._temp_unit
    
    @temp_unit.setter
    def temp_unit(self, value):
        LOGGER.debug(f"Setting temp_unit for {self.name}: {value}")
        self._temp_unit = value
        # Update the drivers list with the correct temperature UOM
        temp_uom = 17 if value == 'F' else 4
        # Find and update the CLITEMP driver in the drivers list
        for driver in self.drivers:
            if driver['driver'] == 'CLITEMP':
                driver['uom'] = temp_uom
                LOGGER.debug(f"Updated CLITEMP driver UOM to {temp_uom} for {self.name}")
                break

    @property
    def device_id(self):
        return self._device_id
    
    @device_id.setter
    def device_id(self, value):
        LOGGER.debug(f"Setting device_id for {self.name}: {value}")
        self._device_id = value

    @property 
    def device_info(self):
        return self._device_info
    
    @device_info.setter
    def device_info(self, value):
        LOGGER.debug(f"Setting device_info for {self.name}: {value}")
        self._device_info = value

    @property
    def device_instance(self):
        return self._device_instance
    
    @device_instance.setter
    def device_instance(self, value):
        LOGGER.debug(f"Setting device_instance for {self.name}: {value}")
        self._device_instance = value

    @property
    def vrm_client(self):
        return self._vrm_client
    
    @vrm_client.setter
    def vrm_client(self, value):
        LOGGER.debug(f"Setting vrm_client for {self.name}: {value is not None}")
        self._vrm_client = value

    @property
    def installation_id(self):
        return self._installation_id
        
    @installation_id.setter
    def installation_id(self, value):
        LOGGER.debug(f"Setting installation_id for {self.name}: {value}")
        self._installation_id = value

    def set_temperature_driver(self, celsius_temp, driver_name='CLITEMP'):
        """Set temperature driver with proper unit conversion based on user preference"""
        try:
            if self.temp_unit == 'F':
                # Convert to Fahrenheit
                display_temp = (celsius_temp * 9/5) + 32
                uom = 17  # Fahrenheit UOM
                unit_str = "°F"
            else:
                # Keep as Celsius (default)
                display_temp = celsius_temp
                uom = 4   # Celsius UOM
                unit_str = "°C"
            
            LOGGER.debug(f"Setting temperature {driver_name}: {celsius_temp}°C -> {display_temp}{unit_str} (UOM {uom})")
            
            # Set the driver with both value and UOM
            self.setDriver(driver_name, display_temp, uom)
            
        except Exception as ex:
            LOGGER.error(f"Failed to set temperature driver {driver_name}: {ex}")
            # Fallback to celsius
            self.setDriver(driver_name, celsius_temp, 4)

    def start(self):
        """Called when Victron Battery Monitor starts"""
        LOGGER.info(f"=== Victron Battery Monitor Starting: {self.name} ===")
        LOGGER.debug(f"Startup state - device_instance: {self.device_instance}, vrm_client: {self.vrm_client is not None}, installation_id: {self.installation_id}")
        
        # Only try to get VRM data if we have all required properties
        if self.device_instance and self.vrm_client and self.installation_id:
            LOGGER.info(f"All required properties available, attempting to get initial VRM data for {self.name}")
            try:
                self.update_from_vrm()
            except Exception as ex:
                LOGGER.warning(f"Failed to get initial data for {self.name} during startup: {ex}")
        else:
            LOGGER.info(f"Required properties not yet available for {self.name}, will get data on first poll")
        
        # Set initial values (either from VRM or defaults)
        self.setDriver('ST', self.battery_percentage, 51)  # Battery percentage (0-100%) (SOC)
        self.setDriver('CV', self.battery_voltage, 72)  # Voltage in volts (V)
        self.setDriver('CC', self.battery_current, 1)  # Current in amperes (A)
        self.setDriver('CPW', self.battery_power, 73)  # Power in watts
        self.set_temperature_driver(self.battery_temperature)  # Temperature with unit conversion
        # Initialize alarm drivers
        self.setDriver('GV0', self.low_voltage_alarm, 2)   # Low Voltage Alarm
        self.setDriver('GV1', self.high_voltage_alarm, 2)  # High Voltage Alarm
        self.setDriver('GV2', self.low_soc_alarm, 2)       # Low SOC Alarm
        self.setDriver('GV3', self.low_temp_alarm, 2)      # Low Temp Alarm
        self.setDriver('GV4', self.high_temp_alarm, 2)     # High Temp Alarm
        self.reportDrivers()
        LOGGER.info(f"=== Victron Battery Monitor Started: {self.name} ===")
        
        # If we didn't get real data at startup, the first poll will get it
        if self.battery_percentage == 0 and self.battery_voltage == 0:
            LOGGER.info(f"No initial data for {self.name}, will update on first poll cycle")

    def update_from_vrm(self):
        """Update battery monitor data from VRM API"""
        try:
            LOGGER.debug(f"Device info available for {self.name}: {self.device_info.get('productName', 'Unknown') if self.device_info else 'No device info'}")
            
            # Primary method: Use diagnostics data which includes temperature
            if self.device_instance and self.vrm_client and self.installation_id:
                LOGGER.debug(f"Updating {self.name} from VRM diagnostics API using instance {self.device_instance}...")
                diagnostics_data = self.vrm_client.get_diagnostics_data(self.installation_id)
                if diagnostics_data:
                    LOGGER.debug(f"Got diagnostics data for {self.name}, parsing...")
                    parsed_data = self.parse_diagnostics_data(diagnostics_data)
                    if parsed_data:
                        return
                        
                # Fallback to battery telemetry if diagnostics fails
                LOGGER.debug(f"Diagnostics failed, trying telemetry for {self.name}...")
                telemetry_data = self.get_battery_telemetry_data()
                if telemetry_data:
                    LOGGER.debug(f"Got telemetry data for {self.name}, parsing...")
                    # Parse the telemetry data (which has actual sensor readings)
                    self.parse_battery_telemetry(telemetry_data)
                    return
                    
            # Fallback to device data if everything else fails
            if self.device_id and self.vrm_client and self.installation_id:
                LOGGER.info(f"Falling back to device data for {self.name}")
                device_data = self.vrm_client.get_device_data(self.installation_id, self.device_id)
                if device_data and device_data.get('records'):
                    self.parse_device_data(device_data)
                    return
                    
            LOGGER.warning(f"No working VRM data source for {self.name}, using default values")
                
        except Exception as ex:
            LOGGER.exception(f"Failed to update {self.name} from VRM API: {ex}")

    def parse_battery_telemetry(self, telemetry_data):
        """Parse battery telemetry data and update device fields"""
        try:
            LOGGER.debug(f"===== PARSING BATTERY TELEMETRY for {self.name} =====")
            LOGGER.debug(f"Telemetry data received: {json.dumps(telemetry_data) if telemetry_data else 'None'}")
            
            if isinstance(telemetry_data, dict):
                # Extract battery readings from telemetry data
                self.battery_percentage = float(telemetry_data.get('soc', 0))
                self.battery_voltage = float(telemetry_data.get('voltage', 0))
                self.battery_current = float(telemetry_data.get('current', 0))
                self.battery_power = float(telemetry_data.get('power', 0))
                self.battery_temperature = float(telemetry_data.get('temperature', 0))
                
                # Special logging for temperature
                if 'temperature' in telemetry_data:
                    LOGGER.debug(f"Temperature found in telemetry: {telemetry_data['temperature']}°C")
                else:
                    LOGGER.warning(f"NO TEMPERATURE in telemetry data. Available keys: {list(telemetry_data.keys())}")
                
                LOGGER.debug(f"Battery {self.name} parsed values - SOC: {self.battery_percentage}%, V: {self.battery_voltage}V, I: {self.battery_current}A, P: {self.battery_power}W, T: {self.battery_temperature}°C")
                
                # Update drivers with the new values
                self.setDriver('ST', self.battery_percentage, 51)  # SOC percentage
                self.setDriver('CV', self.battery_voltage, 72)  # Voltage 
                self.setDriver('CC', self.battery_current, 1)  # Current
                self.setDriver('CPW', self.battery_power, 73)  # Power
                LOGGER.debug(f"Setting temperature driver: {self.battery_temperature}°C")
                self.set_temperature_driver(self.battery_temperature)  # Temperature with unit conversion
                self.reportDrivers()
                
                LOGGER.info(f"Battery {self.name}: SOC {self.battery_percentage}%, {self.battery_voltage}V, {self.battery_current}A, {self.battery_power}W, T: {self.battery_temperature}°C")
                return True
            else:
                LOGGER.warning(f"Invalid telemetry data format for {self.name}: {type(telemetry_data)}")
                return False
                
        except Exception as ex:
            LOGGER.exception(f"Failed to parse telemetry data for {self.name}: {ex}")
            return False
            
        LOGGER.debug(f"===== END PARSING BATTERY TELEMETRY for {self.name} =====")

    def update_from_shared_data(self, shared_diagnostics_data):
        """Update from shared diagnostics data (efficient polling method)"""
        try:
            LOGGER.debug(f"Updating node {self.name}")
            
            # For battery monitor, the diagnostics parsing has field mapping issues
            # Fall back to the working individual VRM call path that uses telemetry
            LOGGER.debug(f"Battery monitor falling back to individual VRM call for {self.name}")
            self.update_from_vrm()
            
        except Exception as ex:
            LOGGER.exception(f"Failed to update {self.name} from shared data: {ex}")
            # Final fallback to individual update
            try:
                self.update_from_vrm()
            except Exception as fallback_ex:
                LOGGER.error(f"Fallback update also failed for {self.name}: {fallback_ex}")

    def get_battery_telemetry_data(self):
        """Get real-time battery telemetry data from VRM diagnostics"""
        try:
            if not self.device_instance or not self.vrm_client or not self.installation_id:
                LOGGER.warning(f"Missing instance/client/installation data for {self.name}")
                return None
                
            LOGGER.debug(f"Getting battery telemetry for {self.name} using instance {self.device_instance}")
            
            # Get diagnostics data which contains live telemetry
            diagnostics_data = self.vrm_client.get_diagnostics_data(self.installation_id)
            
            if not diagnostics_data or 'records' not in diagnostics_data:
                LOGGER.warning(f"No diagnostics data received for {self.name}")
                return None
            
            # Collect ALL records for our device instance first
            instance_records = []
            for record in diagnostics_data['records']:
                if (record.get('Device') == 'Battery Monitor' and 
                    record.get('instance') == self.device_instance):
                    instance_records.append(record)
            
            LOGGER.debug(f"Found {len(instance_records)} records for {self.name} instance {self.device_instance}")
            
            if not instance_records:
                LOGGER.warning(f"No records found for {self.name} instance {self.device_instance}")
                return None
            
            # Parse all records for this instance to extract battery monitor values
            battery_data = {}
            
            for record in instance_records:
                # Map VRM data attributes to our values
                description = record.get('description', '').lower()
                raw_value = record.get('rawValue')
                original_description = record.get('description', '')
                
                LOGGER.debug(f"Processing telemetry record: '{original_description}' (lowercase: '{description}') = {raw_value}")
                
                if raw_value is not None:
                    if description == 'voltage' and raw_value is not None:
                        battery_data['voltage'] = float(raw_value)
                        LOGGER.debug(f"Telemetry found voltage: {raw_value}V")
                    elif description == 'current' and raw_value is not None:
                        battery_data['current'] = float(raw_value)
                        LOGGER.debug(f"Telemetry found current: {raw_value}A")
                    elif description == 'state of charge' and raw_value is not None:
                        battery_data['soc'] = float(raw_value)
                        LOGGER.debug(f"Telemetry found SOC: {raw_value}%")
                    elif description == 'consumed amphours' and raw_value is not None:
                        battery_data['consumed_ah'] = float(raw_value)
                        LOGGER.debug(f"Telemetry found consumed Ah: {raw_value}Ah")
                    elif description == 'time to go' and raw_value is not None:
                        battery_data['time_to_go'] = float(raw_value)
                        LOGGER.debug(f"Telemetry found time to go: {raw_value}h")
                    elif 'temperature' in description and raw_value is not None:
                        battery_data['temperature'] = float(raw_value)
                        LOGGER.debug(f"Telemetry found temperature: {raw_value}°C (from description: '{original_description}')")
                    else:
                        if 'temp' in description:
                            LOGGER.warning(f"TEMPERATURE NOT MATCHED in telemetry: '{original_description}' = {raw_value}")
                        LOGGER.debug(f"Unmatched telemetry field: '{original_description}' = {raw_value}")
            
            # Calculate power if we have voltage and current
            if 'voltage' in battery_data and 'current' in battery_data:
                battery_data['power'] = battery_data['voltage'] * battery_data['current']
                LOGGER.debug(f"Calculated power: {battery_data['power']}W")
            
            if battery_data:
                LOGGER.debug(f"===== BATTERY TELEMETRY DATA for {self.name} =====")
                LOGGER.debug(f"Processed {len(instance_records)} records for instance {self.device_instance}")
                LOGGER.debug(f"Battery telemetry: {json.dumps(battery_data, indent=2)}")
                LOGGER.debug(f"Temperature included: {'temperature' in battery_data}")
                LOGGER.debug(f"===== END BATTERY TELEMETRY DATA =====")
                return battery_data
            else:
                LOGGER.warning(f"No battery data extracted from {len(instance_records)} records for {self.name} instance {self.device_instance}")
                return None
                
        except Exception as ex:
            LOGGER.exception(f"Failed to get battery telemetry data for {self.name}: {ex}")
            return None



    def parse_overview_data(self, overview_data):
        """Parse system overview data for battery monitor"""
        try:
            LOGGER.debug(f"Parsing overview data for {self.name}: {overview_data}")
            
            # Look for battery-specific fields
            if 'soc' in overview_data:
                self.battery_percentage = float(overview_data['soc'])
                LOGGER.info(f"Updated {self.name} battery percentage: {self.battery_percentage}%")
            elif 'state_of_charge' in overview_data:
                self.battery_percentage = float(overview_data['state_of_charge'])
                LOGGER.info(f"Updated {self.name} battery percentage: {self.battery_percentage}%")
                
            if 'voltage' in overview_data:
                self.battery_voltage = float(overview_data['voltage'])
                LOGGER.info(f"Updated {self.name} battery voltage: {self.battery_voltage}V")
                
            if 'current' in overview_data:
                self.battery_current = float(overview_data['current'])
                LOGGER.info(f"Updated {self.name} battery current: {self.battery_current}A")
                
        except Exception as ex:
            LOGGER.exception(f"Failed to parse overview data for {self.name}: {ex}")

    def parse_device_data(self, device_data):
        """Parse device data from VRM diagnostics for battery monitor"""
        try:
            LOGGER.debug(f"===== BATTERY MONITOR PARSING DATA for {self.name} =====")
            LOGGER.debug(f"Raw device data JSON: {json.dumps(device_data, indent=2) if device_data else 'None'}")
            LOGGER.debug(f"Data type: {type(device_data)}")
            
            if not device_data:
                LOGGER.warning(f"No device data to parse for {self.name}")
                return
            
            # Handle diagnostics data format (direct value dictionary or records wrapper)
            if isinstance(device_data, dict):
                found_fields = []
                
                # Check if data is wrapped in records array
                if 'records' in device_data and isinstance(device_data['records'], list) and len(device_data['records']) > 0:
                    # Extract the first record for processing
                    actual_data = device_data['records'][0]
                else:
                    # Use data directly
                    actual_data = device_data
                
                # Extract telemetry values from diagnostics data
                if 'voltage' in actual_data:
                    self.battery_voltage = float(actual_data['voltage'])
                    found_fields.append(f"voltage: {self.battery_voltage}V")
                    LOGGER.debug(f"Updated {self.name} voltage: {self.battery_voltage}V")
                    
                if 'current' in actual_data:
                    self.battery_current = float(actual_data['current'])
                    found_fields.append(f"current: {self.battery_current}A")
                    LOGGER.debug(f"Updated {self.name} current: {self.battery_current}A")
                    
                if 'power' in actual_data:
                    self.battery_power = float(actual_data['power'])
                    found_fields.append(f"power: {self.battery_power}W")
                    LOGGER.debug(f"Updated {self.name} power: {self.battery_power}W")
                    
                if 'soc' in actual_data:
                    self.battery_percentage = float(actual_data['soc'])
                    found_fields.append(f"soc: {self.battery_percentage}%")
                    LOGGER.debug(f"Updated {self.name} SOC: {self.battery_percentage}%")
                    
                if 'temperature' in actual_data:
                    self.battery_temperature = float(actual_data['temperature'])
                    found_fields.append(f"temperature: {self.battery_temperature}°C")
                    LOGGER.debug(f"Updated {self.name} temperature: {self.battery_temperature}°C")
                    
                if 'consumed_ah' in actual_data:
                    # Store consumed Ah for reference (not used in driver update)
                    consumed_ah = float(actual_data['consumed_ah'])
                    found_fields.append(f"consumed_ah: {consumed_ah}Ah")
                    LOGGER.debug(f"Battery {self.name} consumed Ah: {consumed_ah}Ah")
                    
                if 'time_to_go' in actual_data:
                    # Store time to go for reference (not used in driver update)
                    time_to_go = float(actual_data['time_to_go'])
                    found_fields.append(f"time_to_go: {time_to_go}h")
                    LOGGER.debug(f"Battery {self.name} time to go: {time_to_go}h")
                
                # Update ISY drivers with new values (proper scaling)
                self.setDriver('ST', self.battery_percentage)              # State of Charge (%)
                self.setDriver('CV', self.battery_voltage)                 # Voltage in volts (V)
                self.setDriver('CC', self.battery_current)                 # Current in amperes (A)
                self.setDriver('CPW', self.battery_power)                   # Power in watts
                if hasattr(self, 'battery_temperature') and self.battery_temperature is not None:
                    self.set_temperature_driver(self.battery_temperature)   # Temperature with unit conversion
                self.reportDrivers()  # Report the updated drivers to ISY
                
                LOGGER.debug(f"Battery {self.name} parsed fields: {', '.join(found_fields) if found_fields else 'None'}")
                LOGGER.debug(f"Battery {self.name} final values - SOC: {self.battery_percentage}%, V: {self.battery_voltage}V, I: {self.battery_current}A, P: {self.battery_power}W")
                
                if found_fields:
                    LOGGER.debug(f"Successfully updated {self.name} with {len(found_fields)} values")
                else:
                    LOGGER.warning(f"No valid battery data found for {self.name}")
            else:
                LOGGER.error(f"Unknown device data format for {self.name}: {type(device_data)}")
            
            LOGGER.debug(f"===== END BATTERY MONITOR PARSING DATA for {self.name} =====")
            
        except Exception as ex:
            LOGGER.exception(f"Failed to parse battery device data for {self.name}: {ex}")
            LOGGER.debug(f"===== END BATTERY MONITOR PARSING (ERROR) for {self.name} =====")

    def parse_diagnostics_data(self, diagnostics_data):
        """Parse device data from VRM diagnostics for battery monitor"""
        try:
            LOGGER.debug(f"===== BATTERY MONITOR PARSING DIAGNOSTICS DATA for {self.name} =====")
            LOGGER.debug(f"Looking for device instance: {self.device_instance}")
            LOGGER.debug(f"Total diagnostics records received: {len(diagnostics_data.get('records', [])) if diagnostics_data else 0}")
            
            if not diagnostics_data or 'records' not in diagnostics_data:
                LOGGER.warning(f"No diagnostics records for {self.name}")
                return None
            
            # Collect ALL records for our device instance first
            instance_records = []
            for record in diagnostics_data['records']:
                if record.get('instance') == self.device_instance:
                    instance_records.append(record)
            
            LOGGER.debug(f"Found {len(instance_records)} records for instance {self.device_instance}")
            
            if not instance_records:
                LOGGER.warning(f"No records found for instance {self.device_instance}")
                return None
                
            # Look for our device instance in the diagnostics data
            device_data = {}
            found_device = False
            
            for record in instance_records:
                found_device = True
                LOGGER.debug(f"Processing diagnostics record for {self.name} instance {self.device_instance}")
                
                # Parse battery monitor specific fields
                raw_value = record.get('rawValue')
                description = record.get('description', '').lower()
                original_description = record.get('description', '')
                
                LOGGER.debug(f"Processing record: description='{description}', rawValue={raw_value}")
                
                if raw_value is not None:
                    # State of charge
                    if 'state of charge' in description or 'soc' in description:
                        device_data['soc'] = float(raw_value)
                        LOGGER.debug(f"Found SOC: {raw_value}")
                    # Battery voltage
                    elif 'voltage' in description and ('battery' in description or description == 'voltage'):
                        device_data['voltage'] = float(raw_value)
                        LOGGER.debug(f"Found voltage: {raw_value}")
                    # Battery current
                    elif 'current' in description and ('battery' in description or description == 'current'):
                        device_data['current'] = float(raw_value)
                        LOGGER.debug(f"Found current: {raw_value}")
                    # Battery power (calculated field not typically in diagnostics)
                    elif 'power' in description and 'battery' in description:
                        device_data['power'] = float(raw_value)
                        LOGGER.debug(f"Found power: {raw_value}")
                    # Battery temperature - only match actual temperature readings, not alarms
                    elif 'temperature' in description and 'alarm' not in description:
                        device_data['temperature'] = float(raw_value)
                        LOGGER.debug(f"Found temperature: {raw_value}°C (description: '{original_description}') - MATCHED!")
                    # Time to go
                    elif 'time to go' in description:
                        device_data['time_to_go'] = float(raw_value)
                        LOGGER.debug(f"Found time to go: {raw_value}")
                    # Consumed Ah
                    elif 'consumed ah' in description or 'consumed amphours' in description:
                        device_data['consumed_ah'] = float(raw_value)
                        LOGGER.debug(f"Found consumed Ah: {raw_value}")
                    # Alarm fields
                    elif 'low voltage alarm' in description:
                        device_data['low_voltage_alarm'] = int(raw_value)
                        LOGGER.debug(f"Found low voltage alarm: {raw_value}")
                    elif 'high voltage alarm' in description:
                        device_data['high_voltage_alarm'] = int(raw_value)
                        LOGGER.debug(f"Found high voltage alarm: {raw_value}")
                    elif 'low state-of-charge alarm' in description:
                        device_data['low_soc_alarm'] = int(raw_value)
                        LOGGER.debug(f"Found low SOC alarm: {raw_value}")
                    elif 'low battery temperature alarm' in description:
                        device_data['low_temp_alarm'] = int(raw_value)
                        LOGGER.debug(f"Found low temp alarm: {raw_value}")
                    elif 'high battery temperature alarm' in description:
                        device_data['high_temp_alarm'] = int(raw_value)
                        LOGGER.debug(f"Found high temp alarm: {raw_value}")
                    else:
                        # Log unmatched fields at debug level only
                        LOGGER.debug(f"Unmatched field: '{original_description}' = {raw_value}")
                            
            # Calculate power if we have voltage and current but no power reading
            if 'voltage' in device_data and 'current' in device_data and 'power' not in device_data:
                device_data['power'] = device_data['voltage'] * device_data['current']
                LOGGER.debug(f"Calculated power: {device_data['power']}W")
                            
            if found_device and device_data:
                LOGGER.debug(f"===== BATTERY DIAGNOSTICS DATA for {self.name} =====")
                LOGGER.debug(f"Processed {len(instance_records)} records for instance {self.device_instance}")
                LOGGER.debug(f"Battery diagnostics: {json.dumps(device_data, indent=2)}")
                LOGGER.debug(f"Temperature found: {'temperature' in device_data} - Value: {device_data.get('temperature', 'N/A')}")
                LOGGER.debug(f"===== END BATTERY DIAGNOSTICS DATA =====")
                
                # Update our properties
                if 'soc' in device_data:
                    self.battery_percentage = device_data['soc']
                if 'voltage' in device_data:
                    self.battery_voltage = device_data['voltage']
                if 'current' in device_data:
                    self.battery_current = device_data['current']
                if 'power' in device_data:
                    self.battery_power = device_data['power']
                if 'temperature' in device_data:
                    self.battery_temperature = device_data['temperature']
                # Update alarm properties
                if 'low_voltage_alarm' in device_data:
                    self.low_voltage_alarm = device_data['low_voltage_alarm']
                if 'high_voltage_alarm' in device_data:
                    self.high_voltage_alarm = device_data['high_voltage_alarm']
                if 'low_soc_alarm' in device_data:
                    self.low_soc_alarm = device_data['low_soc_alarm']
                if 'low_temp_alarm' in device_data:
                    self.low_temp_alarm = device_data['low_temp_alarm']
                if 'high_temp_alarm' in device_data:
                    self.high_temp_alarm = device_data['high_temp_alarm']
                
                # Update ISY drivers with proper scaling
                self.setDriver('ST', self.battery_percentage, 51)                     # State of Charge (%)
                self.setDriver('CV', self.battery_voltage, 72)                        # Voltage in volts (V)
                self.setDriver('CC', self.battery_current, 1)                         # Current in amperes (A)
                self.setDriver('CPW', self.battery_power, 73)                         # Power in watts
                # Update alarm drivers
                self.setDriver('GV0', self.low_voltage_alarm, 2)                      # Low Voltage Alarm
                self.setDriver('GV1', self.high_voltage_alarm, 2)                     # High Voltage Alarm
                self.setDriver('GV2', self.low_soc_alarm, 2)                          # Low SOC Alarm
                self.setDriver('GV3', self.low_temp_alarm, 2)                         # Low Temp Alarm
                self.setDriver('GV4', self.high_temp_alarm, 2)                        # High Temp Alarm
                if 'temperature' in device_data:
                    LOGGER.debug(f"Setting temperature: {self.battery_temperature}°C")
                    self.set_temperature_driver(self.battery_temperature)  # Temperature with unit conversion
                else:
                    LOGGER.debug(f"No temperature data available, setting to 0")
                    self.set_temperature_driver(0)  # Use helper method for consistency
                self.reportDrivers()  # Report the updated drivers to ISY
                
                LOGGER.info(f"Updated {self.name} from diagnostics - SOC: {self.battery_percentage}%, V: {self.battery_voltage}V, I: {self.battery_current}A, P: {self.battery_power}W, T: {self.battery_temperature}°C, Alarms: LV:{self.low_voltage_alarm} HV:{self.high_voltage_alarm} LS:{self.low_soc_alarm} LT:{self.low_temp_alarm} HT:{self.high_temp_alarm}")
                return device_data
            else:
                LOGGER.warning(f"No diagnostics data found for {self.name} device instance {self.device_instance}")
                return None
                
        except Exception as ex:
            LOGGER.exception(f"Failed to parse diagnostics data for {self.name}: {ex}")
            return None

    def query(self, command=None):
        """Called when ISY queries battery monitor"""
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
        
        # If VRM update failed, simulate slight changes for demo
        if not self.vrm_client:
            import random
            self.battery_percentage = max(80.0, min(90.0, self.battery_percentage + random.uniform(-1, 1)))
            self.battery_voltage = max(24.0, min(26.0, self.battery_voltage + random.uniform(-0.1, 0.1)))
        
        # Update drivers
        self.setDriver('ST', self.battery_percentage, 51)
        self.setDriver('CV', self.battery_voltage, 72)
        self.setDriver('CC', self.battery_current, 1)                      # Current in amperes (A)
        self.setDriver('CPW', self.battery_power, 73)  # Power in watts
        self.set_temperature_driver(self.battery_temperature)  # Temperature with unit conversion
        # Update alarm drivers
        self.setDriver('GV0', self.low_voltage_alarm, 2)   # Low Voltage Alarm
        self.setDriver('GV1', self.high_voltage_alarm, 2)  # High Voltage Alarm
        self.setDriver('GV2', self.low_soc_alarm, 2)       # Low SOC Alarm
        self.setDriver('GV3', self.low_temp_alarm, 2)      # Low Temp Alarm
        self.setDriver('GV4', self.high_temp_alarm, 2)     # High Temp Alarm
        self.reportDrivers()

    def shortPoll(self):
        """Called every shortPoll seconds"""
        LOGGER.debug(f"Battery monitor {self.name} - shortPoll triggered")
        self.query()

    def longPoll(self):
        """Called every longPoll seconds"""
        LOGGER.debug(f"Battery monitor {self.name} - longPoll triggered")
        self.query()



    # Define the drivers (status values) for this node - all zero until VRM connection
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 51},      # Battery percentage (0-100%) (SOC)
        {'driver': 'CV', 'value': 0, 'uom': 72},      # Voltage in volts (V)
        {'driver': 'CC', 'value': 0, 'uom': 1},       # Battery current in amperes (A)
        {'driver': 'CPW', 'value': 0, 'uom': 73},     # Battery power in watts
        {'driver': 'CLITEMP', 'value': 0, 'uom': 4},  # Battery temperature (UOM varies: 4=°C, 17=°F)
        {'driver': 'GV0', 'value': 0, 'uom': 2},      # Low Voltage Alarm (0=No Alarm, 1=Alarm)
        {'driver': 'GV1', 'value': 0, 'uom': 2},      # High Voltage Alarm (0=No Alarm, 1=Alarm)
        {'driver': 'GV2', 'value': 0, 'uom': 2},      # Low SOC Alarm (0=No Alarm, 1=Alarm)
        {'driver': 'GV3', 'value': 0, 'uom': 2},      # Low Temp Alarm (0=No Alarm, 1=Alarm)
        {'driver': 'GV4', 'value': 0, 'uom': 2}       # High Temp Alarm (0=No Alarm, 1=Alarm)
    ]

    # Define the node ID (must match nodedef)
    id = 'VicShunt'

    # Define the commands this node supports
    commands = {
        'QUERY': query
    }
