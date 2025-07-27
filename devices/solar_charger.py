#!/usr/bin/env python3
"""
Victron Solar Charger Node Class for Polyglot v3
Contains solar charger/MPPT controller node definition
"""
import udi_interface
import requests
import json

LOGGER = udi_interface.LOGGER

class VictronSolarCharger(udi_interface.Node):
    """Solar charger node (MPPT controllers) that gets data from VRM API"""
    
    def __init__(self, polyglot, primary, address, name):
        super().__init__(polyglot, primary, address, name)
        self.name = name
        self.poly = polyglot
        
        # === SOLAR (PV) SECTION ===
        self.solar_voltage = 0.0        # Solar panel voltage
        self.solar_current = 0.0        # Solar current (calculated from PV power/voltage)
        self.solar_power = 0.0          # Solar power output
        self.solar_yield_today = 0.0    # Today's solar yield in kWh
        self.max_power_today = 0.0      # Maximum power today
        
        # === BATTERY SECTION ===
        self.battery_voltage = 0.0      # Battery voltage from MPPT
        self.battery_current = 0.0      # Battery current (positive=charging, negative=discharging)
        self.battery_power = 0.0        # Battery power from MPPT (positive=charging, negative=discharging)
        self.battery_temperature = 0.0  # Battery temperature (if available)
        self.charge_state = 0           # MPPT charge state (0=Off, 3=Bulk, 4=Absorption, 5=Float)
        
        # === LOAD OUTPUT SECTION ===
        self.load_output_state = 2      # Load output state (0=Off, 1=On, 2=Unknown)
        self.load_current = 0.0         # Load output current
        self.load_power = 0.0           # Load output power
        self.load_voltage = 0.0         # Load output voltage
        
        # === ADDITIONAL VRM FIELDS (may not be available on all units) ===
        self.mppt_temperature = 0.0     # MPPT controller temperature
        self.error_code = 0             # Error code (if any)
        self.relay_state = 0            # Relay state (if applicable)
        self.off_reason = 0             # Off reason code
        self.tracker_operation_mode = 0 # Tracker operation mode
        self.yield_yesterday = 0.0      # Yesterday's yield
        self.yield_user = 0.0           # User resettable yield counter
        self.max_power_yesterday = 0.0  # Yesterday's max power
        self.device_id = None           # Will be set by parent controller
        self.device_data = None         # Will be set by parent controller
        self._temp_unit = 'C'            # Temperature unit preference (C or F)
        self.device_info = None         # Device info from system overview
        self.device_instance = None     # Device instance number
        self.overview_data = None       # Will be set for overview-based nodes
        self.vrm_client = None          # Will be set by parent controller
        self.installation_id = None     # Will be set by parent controller

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

    def get_charge_state_text(self, charge_state_num):
        """Convert numeric charge state to descriptive text"""
        charge_states = {
            0: "Off",
            1: "Low Power", 
            2: "Fault",
            3: "Bulk",
            4: "Absorption",
            5: "Float",
            6: "Storage",  # Some MPPT controllers have additional states
            7: "Equalize",
            8: "Other"
        }
        return charge_states.get(charge_state_num, f"Unknown({charge_state_num})")

    def set_temperature_driver(self, celsius_temp, driver_name='CLITEMP'):
        """Set temperature driver with proper unit conversion based on user preference"""
        try:
            # Only set temperature if we have meaningful data (not 0 or None)
            if celsius_temp is None or celsius_temp <= 0:
                LOGGER.debug(f"Skipping temperature update for {self.name} - no temperature data available (value: {celsius_temp})")
                return
                
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
        """Called when Victron Solar Charger starts"""
        LOGGER.info(f"Starting Solar Charger: {self.name}")
        
        # Try to get real data from VRM API
        self.update_from_vrm()
        
        # Set initial values (either from VRM or defaults)
        self.setDriver('ST', self.solar_power, 73)      # Power in watts
        self.setDriver('GV0', self.charge_state, 68)    # Charge state
        self.setDriver('CV', self.solar_voltage, 72)    # Solar voltage in volts (V)
        self.setDriver('CC', self.battery_current, 1)   # Battery current in amperes (A)
        self.setDriver('CPW', self.battery_voltage, 72) # Battery voltage in volts (V)
        # Note: Temperature driver removed - SmartSolar MPPT doesn't provide temperature data
        self.setDriver('GV1', round(self.solar_yield_today, 2), 33) # Yield today in kWh
        self.setDriver('GV2', self.max_power_today, 73) # Max power today in watts
        self.setDriver('GV7', int(self.battery_power), 73) # Battery power in watts
        # Load output drivers (initialized to defaults)
        self.setDriver('GV3', self.load_output_state, 68) # Load output state (0=Off, 1=On, 2=Unknown)
        self.setDriver('GV4', self.load_current, 1)       # Load current in amperes (A)
        self.setDriver('GV5', self.load_voltage, 72)      # Load voltage in volts (V)
        self.setDriver('GV6', int(self.load_power), 73)   # Load power in watts
        self.reportDrivers()
        LOGGER.info(f"Solar Charger {self.name} started successfully")

    def update_from_vrm(self):
        """Update solar charger data from VRM API"""
        try:
            # First priority: Use telemetry data (more reliable for field mapping)
            if self.device_instance and self.vrm_client and self.installation_id:
                LOGGER.info(f"Getting status from Victron for {self.name}")
                
                # Use telemetry method first (more reliable field mapping)
                LOGGER.debug(f"Using telemetry data for {self.name}")
                telemetry_data = self.get_solar_telemetry_data()
                if telemetry_data:
                    self.parse_device_data(telemetry_data)
                    return
                
                # Fallback to diagnostics if telemetry unavailable
                LOGGER.debug(f"Falling back to diagnostics data for {self.name}")
                diagnostics_data = self.vrm_client.get_diagnostics_data(self.installation_id)
                if diagnostics_data:
                    parsed_data = self.parse_diagnostics_data(diagnostics_data)
                    if parsed_data:
                        LOGGER.debug(f"Successfully updated {self.name} from diagnostics data")
                        return
                    else:
                        LOGGER.warning(f"No diagnostics data found for {self.name} device instance {self.device_instance}")
            
            # If we have overview data, use that
            if self.overview_data:
                LOGGER.debug(f"Updating {self.name} from system overview data")
                self.parse_overview_data(self.overview_data)
                return
                
            # If we have device info, log it but use defaults
            if self.device_info:
                LOGGER.info(f"Device info available for {self.name}: {self.device_info.get('productName', 'Unknown')}")
                
            # Fall back to device ID approach
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
            
            # For solar charger, the diagnostics parsing has field mapping issues
            # Fall back to the working individual VRM call path that uses telemetry
            LOGGER.debug(f"Solar charger falling back to individual VRM call for {self.name}")
            self.update_from_vrm()
            
        except Exception as ex:
            LOGGER.exception(f"Failed to update {self.name} from shared data: {ex}")
            # Final fallback to individual update
            try:
                self.update_from_vrm()
            except Exception as fallback_ex:
                LOGGER.error(f"Fallback update also failed for {self.name}: {fallback_ex}")

    def get_solar_telemetry_data(self):
        """Get real-time solar charger telemetry data from VRM diagnostics"""
        try:
            if not self.device_instance or not self.vrm_client or not self.installation_id:
                LOGGER.warning(f"Missing instance/client/installation data for {self.name}")
                return None
                
            LOGGER.debug(f"Getting solar telemetry for {self.name} using instance {self.device_instance}")
            
            # Get diagnostics data which contains live telemetry
            diagnostics_data = self.vrm_client.get_diagnostics_data(self.installation_id)
            
            if not diagnostics_data or 'records' not in diagnostics_data:
                LOGGER.warning(f"No diagnostics data received for {self.name}")
                return None
            
            # Parse diagnostics data to extract solar charger values
            solar_data = {}
            
            for record in diagnostics_data['records']:
                if (record.get('Device') == 'Solar Charger' and 
                    record.get('instance') == self.device_instance):
                    
                    # Map VRM data attributes to our values
                    description = record.get('description', '').lower()
                    raw_value = record.get('rawValue')
                    
                    if 'pv voltage' in description and raw_value is not None:
                        solar_data['pv_voltage'] = float(raw_value)
                    elif 'pv power' in description and raw_value is not None:
                        solar_data['pv_power'] = float(raw_value)
                    elif description == 'voltage' and raw_value is not None:
                        solar_data['battery_voltage'] = float(raw_value)
                    elif description == 'current' and raw_value is not None:
                        solar_data['current'] = float(raw_value)
                    elif 'charge state' in description and raw_value is not None:
                        solar_data['charge_state'] = int(raw_value)
                    elif 'yield today' in description and raw_value is not None:
                        solar_data['yield_today'] = float(raw_value)
                    elif 'maximum charge power today' in description and raw_value is not None:
                        solar_data['max_power_today'] = float(raw_value)
                    elif 'battery watts' in description and raw_value is not None:
                        solar_data['battery_power'] = float(raw_value)
                    # Load output field parsing for MPPT controllers with load outputs
                    elif 'load output state' in description and raw_value is not None:
                        solar_data['load_output_state'] = int(raw_value)
                    elif 'load state' in description and raw_value is not None:
                        solar_data['load_output_state'] = int(raw_value)
                    elif 'load current' in description and raw_value is not None:
                        solar_data['load_current'] = float(raw_value)
                    elif 'load voltage' in description and raw_value is not None:
                        solar_data['load_voltage'] = float(raw_value)
                    elif 'load power' in description and raw_value is not None:
                        solar_data['load_power'] = float(raw_value)
                    # Additional VRM fields (comprehensive support)
                    elif 'temperature' in description and raw_value is not None:
                        # Could be battery temperature or MPPT temperature
                        if 'battery' in description:
                            solar_data['battery_temperature'] = float(raw_value)
                        else:
                            solar_data['mppt_temperature'] = float(raw_value)
                    elif 'error code' in description and raw_value is not None:
                        solar_data['error_code'] = int(raw_value)
                    elif 'relay state' in description and raw_value is not None:
                        solar_data['relay_state'] = int(raw_value)
                    elif 'off reason' in description and raw_value is not None:
                        solar_data['off_reason'] = int(raw_value)
                    elif 'tracker operation' in description and raw_value is not None:
                        solar_data['tracker_operation_mode'] = int(raw_value)
                    elif 'yield yesterday' in description and raw_value is not None:
                        solar_data['yield_yesterday'] = float(raw_value)
                    elif 'yield user' in description and raw_value is not None:
                        solar_data['yield_user'] = float(raw_value)
                    elif 'maximum charge power yesterday' in description and raw_value is not None:
                        solar_data['max_power_yesterday'] = float(raw_value)
            
            if solar_data:
                LOGGER.debug(f"===== SOLAR TELEMETRY DATA for {self.name} =====")
                LOGGER.debug(f"Solar telemetry: {json.dumps(solar_data, indent=2)}")
                LOGGER.debug(f"===== END SOLAR TELEMETRY DATA =====")
                return solar_data
            else:
                LOGGER.warning(f"No solar data found for {self.name} with instance {self.device_instance}")
                return None
                
        except Exception as ex:
            LOGGER.exception(f"Failed to get solar telemetry data for {self.name}: {ex}")
            return None



    def parse_telemetry_data(self, telemetry_data):
        """Parse structured telemetry data from get_solar_telemetry_data"""
        try:
            LOGGER.debug(f"===== PARSING SOLAR TELEMETRY DATA for {self.name} =====")
            LOGGER.debug(f"Telemetry data: {json.dumps(telemetry_data, indent=2)}")
            
            # Organize parsing by VRM sections: Solar -> Battery -> Load Output
            solar_fields = []
            battery_fields = []
            load_fields = []
            
            # === SOLAR (PV) SECTION ===
            if 'pv_power' in telemetry_data:
                self.solar_power = float(telemetry_data['pv_power'])
                solar_fields.append(f"power: {self.solar_power}W")
                LOGGER.debug(f"Updated {self.name} solar power: {self.solar_power}W")
                
            if 'pv_voltage' in telemetry_data:
                self.solar_voltage = float(telemetry_data['pv_voltage'])
                solar_fields.append(f"voltage: {self.solar_voltage}V")
                LOGGER.debug(f"Updated {self.name} solar voltage: {self.solar_voltage}V")
                
            # Calculate solar current from PV power and voltage
            if 'pv_power' in telemetry_data and 'pv_voltage' in telemetry_data:
                if self.solar_voltage > 0 and self.solar_power > 0:
                    self.solar_current = self.solar_power / self.solar_voltage
                    solar_fields.append(f"current: {self.solar_current:.2f}A")
                    LOGGER.debug(f"Calculated {self.name} solar current: {self.solar_current:.2f}A")
                else:
                    self.solar_current = 0.0
                    solar_fields.append(f"current: {self.solar_current}A")
                    LOGGER.debug(f"Set {self.name} solar current to 0A (no solar generation)")
                    
            if 'yield_today' in telemetry_data:
                self.solar_yield_today = float(telemetry_data['yield_today'])
                solar_fields.append(f"yield_today: {self.solar_yield_today}kWh")
                LOGGER.debug(f"Updated {self.name} yield today: {self.solar_yield_today}kWh")
                
            if 'max_power_today' in telemetry_data:
                self.max_power_today = float(telemetry_data['max_power_today'])
                solar_fields.append(f"max_power_today: {self.max_power_today}W")
                LOGGER.debug(f"Updated {self.name} max power today: {self.max_power_today}W")
            
            # === BATTERY SECTION ===   
            if 'current' in telemetry_data:
                self.battery_current = float(telemetry_data['current'])
                battery_fields.append(f"current: {self.battery_current}A")
                LOGGER.debug(f"Updated {self.name} battery current: {self.battery_current}A")
                
            if 'battery_voltage' in telemetry_data:
                self.battery_voltage = float(telemetry_data['battery_voltage'])
                battery_fields.append(f"voltage: {self.battery_voltage}V")
                LOGGER.debug(f"Updated {self.name} battery voltage: {self.battery_voltage}V")
                
            if 'battery_power' in telemetry_data:
                self.battery_power = float(telemetry_data['battery_power'])
                battery_fields.append(f"power: {self.battery_power}W")
                LOGGER.debug(f"Updated {self.name} battery power: {self.battery_power}W")
                
            if 'battery_temperature' in telemetry_data:
                self.battery_temperature = float(telemetry_data['battery_temperature'])
                battery_fields.append(f"temperature: {self.battery_temperature}°C")
                LOGGER.debug(f"Updated {self.name} battery temperature: {self.battery_temperature}°C")
                
            if 'charge_state' in telemetry_data:
                self.charge_state = int(telemetry_data['charge_state'])
                charge_state_text = self.get_charge_state_text(self.charge_state)
                battery_fields.append(f"state: {charge_state_text}")
                LOGGER.debug(f"Updated {self.name} charge state: {self.charge_state} ({charge_state_text})")
            
            # === ADDITIONAL VRM FIELDS (comprehensive support) ===
            additional_fields = []
            if 'mppt_temperature' in telemetry_data:
                self.mppt_temperature = float(telemetry_data['mppt_temperature'])
                additional_fields.append(f"mppt_temp: {self.mppt_temperature}°C")
                LOGGER.debug(f"Updated {self.name} MPPT temperature: {self.mppt_temperature}°C")
                
            if 'error_code' in telemetry_data:
                self.error_code = int(telemetry_data['error_code'])
                if self.error_code != 0:
                    additional_fields.append(f"error: {self.error_code}")
                    LOGGER.warning(f"Updated {self.name} error code: {self.error_code}")
                    
            if 'yield_yesterday' in telemetry_data:
                self.yield_yesterday = float(telemetry_data['yield_yesterday'])
                additional_fields.append(f"yield_yesterday: {self.yield_yesterday}kWh")
                LOGGER.debug(f"Updated {self.name} yield yesterday: {self.yield_yesterday}kWh")
                
            if 'max_power_yesterday' in telemetry_data:
                self.max_power_yesterday = float(telemetry_data['max_power_yesterday'])
                additional_fields.append(f"max_power_yesterday: {self.max_power_yesterday}W")
                LOGGER.debug(f"Updated {self.name} max power yesterday: {self.max_power_yesterday}W")
            
            # === LOAD OUTPUT SECTION ===
            load_data_found = False
            if 'load_output_state' in telemetry_data:
                self.load_output_state = int(telemetry_data['load_output_state'])
                load_state_text = "On" if self.load_output_state == 1 else ("Off" if self.load_output_state == 0 else "Unknown")
                load_fields.append(f"state: {load_state_text}")
                LOGGER.debug(f"Updated {self.name} load output state: {self.load_output_state}")
                load_data_found = True
                
            if 'load_current' in telemetry_data:
                self.load_current = float(telemetry_data['load_current'])
                load_fields.append(f"current: {self.load_current}A")
                LOGGER.debug(f"Updated {self.name} load current: {self.load_current}A")
                load_data_found = True
                
            if 'load_voltage' in telemetry_data:
                self.load_voltage = float(telemetry_data['load_voltage'])
                load_fields.append(f"voltage: {self.load_voltage}V")
                LOGGER.debug(f"Updated {self.name} load voltage: {self.load_voltage}V")
                load_data_found = True
                
            if 'load_power' in telemetry_data:
                self.load_power = float(telemetry_data['load_power'])
                load_fields.append(f"power: {self.load_power}W")
                LOGGER.debug(f"Updated {self.name} load power: {self.load_power}W")
                load_data_found = True
                
                # Calculate missing load values if we have enough data
                # For MPPT controllers, load voltage is typically battery voltage when load is on
                if self.load_output_state == 1 and self.load_current > 0:  # Load is ON and has current
                    # If load_voltage wasn't provided but we have battery voltage, use it
                    if 'load_voltage' not in telemetry_data and self.battery_voltage > 0:
                        self.load_voltage = self.battery_voltage
                        load_fields.append(f"voltage: {self.load_voltage}V (calculated from battery)")
                        LOGGER.debug(f"Calculated {self.name} load voltage from battery: {self.load_voltage}V")
                        
                    # If load_power wasn't provided but we have voltage and current, calculate it
                    if 'load_power' not in telemetry_data and self.load_voltage > 0 and self.load_current > 0:
                        self.load_power = self.load_voltage * self.load_current
                        load_fields.append(f"power: {self.load_power}W (calculated)")
                        LOGGER.debug(f"Calculated {self.name} load power: {self.load_power}W")
                elif self.load_output_state == 0:  # Load is OFF
                    # When load is off, voltage and power should be 0
                    if 'load_voltage' not in telemetry_data:
                        self.load_voltage = 0.0
                        LOGGER.debug(f"Set {self.name} load voltage to 0V (load is OFF)")
                    if 'load_power' not in telemetry_data:
                        self.load_power = 0.0
                        LOGGER.debug(f"Set {self.name} load power to 0W (load is OFF)")
                
                # If no load output data was found, keep load state as Unknown for MPPT with load capability
                if not load_data_found:
                    # Don't change load_output_state - keep it as initialized (2=Unknown)
                    # Only reset the values if they weren't found in telemetry data
                    if 'load_current' not in telemetry_data:
                        self.load_current = 0.0
                    if 'load_voltage' not in telemetry_data:
                        self.load_voltage = 0.0  
                    if 'load_power' not in telemetry_data:
                        self.load_power = 0.0
                    LOGGER.debug(f"No load output data found for {self.name}, keeping load output state as Unknown")
            
            # Update ISY drivers with new values - organized by VRM sections
            
            # === SOLAR (PV) DRIVERS ===
            self.setDriver('ST', self.solar_power)           # Solar power in watts
            self.setDriver('CV', self.solar_voltage)         # Solar voltage in volts (V)
            self.setDriver('GV1', round(self.solar_yield_today, 2)) # Yield today in kWh
            self.setDriver('GV2', self.max_power_today)      # Max power today in watts
            
            # === BATTERY DRIVERS ===
            self.setDriver('CPW', self.battery_voltage)      # Battery voltage in volts (V)
            self.setDriver('CC', self.battery_current)       # Battery current in amperes (A)
            self.setDriver('GV7', int(self.battery_power), 73) # Battery power in watts
            self.setDriver('GV0', self.charge_state, 68)     # Charge state
            # Note: Temperature driver removed - SmartSolar MPPT doesn't provide temperature data
            
            # === LOAD OUTPUT DRIVERS ===
            self.setDriver('GV3', self.load_output_state, 68) # Load output state (0=Off, 1=On, 2=Unknown)
            self.setDriver('GV4', self.load_current, 1)       # Load current in amperes (A)
            self.setDriver('GV5', self.load_voltage, 72)      # Load voltage in volts (V)
            self.setDriver('GV6', int(self.load_power), 73)   # Load power in watts
            self.reportDrivers()  # Report the updated drivers to ISY
            
            # === VRM-STYLE SUMMARY LOGGING ===
            LOGGER.info(f"=== {self.name} Status Update ===")
            if solar_fields:
                LOGGER.info(f"  Solar: {', '.join(solar_fields)}")
            if battery_fields:
                LOGGER.info(f"  Battery: {', '.join(battery_fields)}")
            if load_fields:
                LOGGER.info(f"  Load Output: {', '.join(load_fields)}")
            if additional_fields:
                LOGGER.info(f"  Additional: {', '.join(additional_fields)}")
            
            # Legacy single-line summary for compatibility
            all_fields = solar_fields + battery_fields + load_fields + additional_fields
            if all_fields:
                # Single concise summary message
                charge_state_text = self.get_charge_state_text(self.charge_state)
                load_status = ""
                if load_fields:
                    load_state_text = "On" if self.load_output_state == 1 else ("Off" if self.load_output_state == 0 else "Unknown")
                    load_status = f", Load: {load_state_text} ({self.load_power}W)"
                LOGGER.info(f"Solar {self.name}: {self.solar_power}W ({charge_state_text}), PV {self.solar_voltage}V, Batt {self.battery_voltage}V{load_status}")
            else:
                LOGGER.warning(f"No valid telemetry data found for {self.name}")
                
            LOGGER.debug(f"===== END PARSING SOLAR TELEMETRY DATA for {self.name} =====")
            
        except Exception as ex:
            LOGGER.exception(f"Failed to parse telemetry data for {self.name}: {ex}")

    def parse_overview_data(self, overview_data):
        """Parse system overview data for solar charger"""
        try:
            LOGGER.debug(f"Parsing overview data for {self.name}: {overview_data}")
            
            # Look for solar-specific fields
            if 'power' in overview_data:
                self.solar_power = float(overview_data['power'])
                LOGGER.debug(f"Updated {self.name} solar power: {self.solar_power}W")
                
            if 'voltage' in overview_data:
                self.solar_voltage = float(overview_data['voltage'])
                LOGGER.debug(f"Updated {self.name} solar voltage: {self.solar_voltage}V")
                
            if 'current' in overview_data:
                self.solar_current = float(overview_data['current'])
                LOGGER.debug(f"Updated {self.name} solar current: {self.solar_current}A")
                
            if 'state' in overview_data or 'charge_state' in overview_data:
                self.charge_state = int(overview_data.get('state', overview_data.get('charge_state', 0)))
                charge_state_text = self.get_charge_state_text(self.charge_state)
                LOGGER.debug(f"Updated {self.name} charge state: {self.charge_state} ({charge_state_text})")
                
            if 'battery_voltage' in overview_data:
                self.battery_voltage = float(overview_data['battery_voltage'])
                LOGGER.debug(f"Updated {self.name} battery voltage: {self.battery_voltage}V")
                
            if 'yield_today' in overview_data:
                self.solar_yield_today = float(overview_data['yield_today'])
                LOGGER.debug(f"Updated {self.name} yield today: {self.solar_yield_today}kWh")
                
            if 'max_power_today' in overview_data:
                self.max_power_today = float(overview_data['max_power_today'])
                LOGGER.debug(f"Updated {self.name} max power today: {self.max_power_today}W")
                
        except Exception as ex:
            LOGGER.exception(f"Failed to parse overview data for {self.name}: {ex}")

    def parse_device_data(self, device_data):
        """Parse device data from VRM diagnostics for solar charger"""
        try:
            LOGGER.debug(f"===== SOLAR CHARGER PARSING DATA for {self.name} =====")
            LOGGER.debug(f"Raw device data JSON: {json.dumps(device_data, indent=2) if device_data else 'None'}")
            LOGGER.debug(f"Data type: {type(device_data)}")
            
            if not device_data:
                LOGGER.warning(f"No device data to parse for {self.name}")
                return
            
            # First, try to extract device instance from the records if available
            if isinstance(device_data, dict) and 'records' in device_data:
                records = device_data['records']
                if isinstance(records, list) and len(records) > 0:
                    device_record = records[0]
                    if 'instance' in device_record:
                        self.device_instance = device_record['instance']
                        LOGGER.info(f"Found device instance {self.device_instance} for {self.name}")
                        
                        # Now try to get actual telemetry data using the instance
                        if self.vrm_client and self.installation_id:
                            LOGGER.debug(f"Attempting to get solar telemetry data using instance {self.device_instance}")
                            telemetry_data = self.get_solar_telemetry_data()
                            if telemetry_data:
                                LOGGER.debug(f"Successfully retrieved telemetry data for {self.name}")
                                # Parse the telemetry data instead of the metadata
                                self.parse_telemetry_data(telemetry_data)
                                return
                            else:
                                LOGGER.warning(f"No telemetry data available for {self.name} instance {self.device_instance}")
            
            # Handle diagnostics data format (direct value dictionary)
            if isinstance(device_data, dict):
                # Organize parsing by VRM sections: Solar -> Battery -> Load Output
                solar_fields = []
                battery_fields = []
                load_fields = []
                
                # === SOLAR (PV) SECTION ===
                if 'pv_power' in device_data:
                    self.solar_power = float(device_data['pv_power'])
                    solar_fields.append(f"power: {self.solar_power}W")
                    LOGGER.debug(f"Updated {self.name} solar power: {self.solar_power}W")
                    
                if 'pv_voltage' in device_data:
                    self.solar_voltage = float(device_data['pv_voltage'])
                    solar_fields.append(f"voltage: {self.solar_voltage}V")
                    LOGGER.debug(f"Updated {self.name} solar voltage: {self.solar_voltage}V")
                    
                # Calculate solar current from PV power and voltage
                if 'pv_power' in device_data and 'pv_voltage' in device_data:
                    if self.solar_voltage > 0 and self.solar_power > 0:
                        self.solar_current = self.solar_power / self.solar_voltage
                        solar_fields.append(f"current: {self.solar_current:.2f}A")
                        LOGGER.debug(f"Calculated {self.name} solar current: {self.solar_current:.2f}A")
                    else:
                        self.solar_current = 0.0
                        solar_fields.append(f"current: {self.solar_current}A")
                        LOGGER.debug(f"Set {self.name} solar current to 0A (no solar generation)")
                        
                if 'yield_today' in device_data:
                    self.solar_yield_today = float(device_data['yield_today'])
                    solar_fields.append(f"yield_today: {self.solar_yield_today}kWh")
                    LOGGER.debug(f"Updated {self.name} yield today: {self.solar_yield_today}kWh")
                    
                if 'max_power_today' in device_data:
                    self.max_power_today = float(device_data['max_power_today'])
                    solar_fields.append(f"max_power_today: {self.max_power_today}W")
                    LOGGER.debug(f"Updated {self.name} max power today: {self.max_power_today}W")
                
                # === BATTERY SECTION ===
                if 'current' in device_data:
                    self.battery_current = float(device_data['current'])
                    battery_fields.append(f"current: {self.battery_current}A")
                    LOGGER.debug(f"Updated {self.name} battery current: {self.battery_current}A")
                    
                if 'battery_voltage' in device_data:
                    self.battery_voltage = float(device_data['battery_voltage'])
                    battery_fields.append(f"voltage: {self.battery_voltage}V")
                    LOGGER.debug(f"Updated {self.name} battery voltage: {self.battery_voltage}V")
                    
                if 'charge_state' in device_data:
                    self.charge_state = int(device_data['charge_state'])
                    charge_state_text = self.get_charge_state_text(self.charge_state)
                    battery_fields.append(f"state: {charge_state_text}")
                    LOGGER.debug(f"Updated {self.name} charge state: {self.charge_state} ({charge_state_text})")
                    
                if 'battery_power' in device_data:
                    # Battery power from solar charger (for reference)
                    self.battery_power = float(device_data['battery_power'])
                    battery_fields.append(f"power: {self.battery_power}W")
                    LOGGER.debug(f"Solar charger {self.name} battery power: {self.battery_power}W")
                
                if 'battery_temperature' in device_data:
                    self.battery_temperature = float(device_data['battery_temperature'])
                    battery_fields.append(f"temperature: {self.battery_temperature}°C")
                    LOGGER.debug(f"Updated {self.name} battery temperature: {self.battery_temperature}°C")
                
                # === ADDITIONAL VRM FIELDS (comprehensive support) ===
                additional_fields = []
                if 'mppt_temperature' in device_data:
                    self.mppt_temperature = float(device_data['mppt_temperature'])
                    additional_fields.append(f"mppt_temp: {self.mppt_temperature}°C")
                    LOGGER.debug(f"Updated {self.name} MPPT temperature: {self.mppt_temperature}°C")
                    
                if 'error_code' in device_data:
                    self.error_code = int(device_data['error_code'])
                    if self.error_code != 0:
                        additional_fields.append(f"error: {self.error_code}")
                        LOGGER.warning(f"Updated {self.name} error code: {self.error_code}")
                        
                if 'yield_yesterday' in device_data:
                    self.yield_yesterday = float(device_data['yield_yesterday'])
                    additional_fields.append(f"yield_yesterday: {self.yield_yesterday}kWh")
                    LOGGER.debug(f"Updated {self.name} yield yesterday: {self.yield_yesterday}kWh")
                    
                if 'max_power_yesterday' in device_data:
                    self.max_power_yesterday = float(device_data['max_power_yesterday'])
                    additional_fields.append(f"max_power_yesterday: {self.max_power_yesterday}W")
                    LOGGER.debug(f"Updated {self.name} max power yesterday: {self.max_power_yesterday}W")
                
                # === LOAD OUTPUT SECTION ===
                # Handle load output fields from telemetry data
                load_data_found = False
                if 'load_output_state' in device_data:
                    self.load_output_state = int(device_data['load_output_state'])
                    load_state_text = "On" if self.load_output_state == 1 else ("Off" if self.load_output_state == 0 else "Unknown")
                    load_fields.append(f"state: {load_state_text}")
                    LOGGER.debug(f"Updated {self.name} load output state: {self.load_output_state}")
                    load_data_found = True
                    
                if 'load_current' in device_data:
                    self.load_current = float(device_data['load_current'])
                    load_fields.append(f"current: {self.load_current}A")
                    LOGGER.debug(f"Updated {self.name} load current: {self.load_current}A")
                    load_data_found = True
                    
                if 'load_voltage' in device_data:
                    self.load_voltage = float(device_data['load_voltage'])
                    load_fields.append(f"voltage: {self.load_voltage}V")
                    LOGGER.debug(f"Updated {self.name} load voltage: {self.load_voltage}V")
                    load_data_found = True
                    
                if 'load_power' in device_data:
                    self.load_power = float(device_data['load_power'])
                    load_fields.append(f"power: {self.load_power}W")
                    LOGGER.debug(f"Updated {self.name} load power: {self.load_power}W")
                    load_data_found = True
                
                # Calculate missing load values if we have enough data
                # For MPPT controllers, load voltage is typically battery voltage when load is on
                if self.load_output_state == 1 and self.load_current > 0:  # Load is ON and has current
                    # If load_voltage wasn't provided but we have battery voltage, use it
                    if 'load_voltage' not in device_data and self.battery_voltage > 0:
                        self.load_voltage = self.battery_voltage
                        load_fields.append(f"voltage: {self.load_voltage}V (calculated from battery)")
                        LOGGER.debug(f"Calculated {self.name} load voltage from battery: {self.load_voltage}V")
                        
                    # If load_power wasn't provided but we have voltage and current, calculate it
                    if 'load_power' not in device_data and self.load_voltage > 0 and self.load_current > 0:
                        self.load_power = self.load_voltage * self.load_current
                        load_fields.append(f"power: {self.load_power}W (calculated)")
                        LOGGER.debug(f"Calculated {self.name} load power: {self.load_power}W")
                elif self.load_output_state == 0:  # Load is OFF
                    # When load is off, voltage and power should be 0
                    if 'load_voltage' not in device_data:
                        self.load_voltage = 0.0
                        LOGGER.debug(f"Set {self.name} load voltage to 0V (load is OFF)")
                    if 'load_power' not in device_data:
                        self.load_power = 0.0
                        LOGGER.debug(f"Set {self.name} load power to 0W (load is OFF)")
                
                # If no load output data was found in telemetry, keep state as Unknown for MPPT with load capability
                if not load_data_found:
                    # Don't change load_output_state - keep it as initialized (2=Unknown)  
                    # Only reset the values if they weren't found in telemetry data
                    LOGGER.debug(f"No load output data found for {self.name}, keeping load output state as Unknown")
                
                # Update ISY drivers with new values - organized by VRM sections
                
                # === SOLAR (PV) DRIVERS ===
                self.setDriver('ST', self.solar_power)           # Solar power in watts
                self.setDriver('CV', self.solar_voltage)         # Solar voltage in volts (V)
                self.setDriver('GV1', round(self.solar_yield_today, 2)) # Yield today in kWh
                self.setDriver('GV2', self.max_power_today)      # Max power today in watts
                
                # === BATTERY DRIVERS ===
                self.setDriver('CPW', self.battery_voltage)      # Battery voltage in volts (V)
                self.setDriver('CC', self.battery_current)       # Battery current in amperes (A)
                self.setDriver('GV7', int(self.battery_power), 73) # Battery power in watts
                self.setDriver('GV0', self.charge_state, 68)     # Charge state
                # Note: Temperature driver removed - SmartSolar MPPT doesn't provide temperature data
                
                # === LOAD OUTPUT DRIVERS ===
                self.setDriver('GV3', self.load_output_state, 68) # Load output state (0=Off, 1=On, 2=Unknown)
                self.setDriver('GV4', self.load_current, 1)       # Load current in amperes (A)
                self.setDriver('GV5', self.load_voltage, 72)      # Load voltage in volts (V)
                self.setDriver('GV6', int(self.load_power), 73)   # Load power in watts
                self.reportDrivers()  # Report the updated drivers to ISY
                
                # === VRM-STYLE SUMMARY LOGGING ===
                LOGGER.info(f"=== {self.name} Status Update ===")
                if solar_fields:
                    LOGGER.info(f"  Solar: {', '.join(solar_fields)}")
                if battery_fields:
                    LOGGER.info(f"  Battery: {', '.join(battery_fields)}")
                if load_fields:
                    LOGGER.info(f"  Load Output: {', '.join(load_fields)}")
                if additional_fields:
                    LOGGER.info(f"  Additional: {', '.join(additional_fields)}")
                
                # Legacy single-line summary for compatibility
                all_fields = solar_fields + battery_fields + load_fields + additional_fields
                LOGGER.debug(f"Solar charger {self.name} final values - Power: {self.solar_power}W, PV_V: {self.solar_voltage}V, Batt_V: {self.battery_voltage}V, State: {self.charge_state}")
                
                if all_fields:
                    LOGGER.debug(f"Successfully updated {self.name} with {len(all_fields)} values")
                else:
                    LOGGER.warning(f"No valid solar charger data found for {self.name}")
            else:
                LOGGER.error(f"Unknown device data format for {self.name}: {type(device_data)}")
            
            LOGGER.debug(f"===== END SOLAR CHARGER PARSING DATA for {self.name} =====")
            
        except Exception as ex:
            LOGGER.exception(f"Failed to parse solar charger device data for {self.name}: {ex}")
                
            if 'solar_yield_today' in device_data:
                self.solar_yield_today = float(device_data['solar_yield_today'])
                LOGGER.info(f"Updated {self.name} yield today: {self.solar_yield_today}kWh")
            elif 'yield_today' in device_data:
                self.solar_yield_today = float(device_data['yield_today'])
                LOGGER.info(f"Updated {self.name} yield today: {self.solar_yield_today}kWh")
                
            if 'solar_max_power_today' in device_data:
                self.max_power_today = float(device_data['solar_max_power_today'])
                LOGGER.info(f"Updated {self.name} max power today: {self.max_power_today}W")
            elif 'max_power_today' in device_data:
                self.max_power_today = float(device_data['max_power_today'])
                LOGGER.debug(f"Updated {self.name} max power today: {self.max_power_today}W")
            
            # Handle legacy data format (fallback)
            if 'power' in device_data:
                self.solar_power = float(device_data['power'])
                LOGGER.debug(f"Updated {self.name} solar power: {self.solar_power}W")
                
            if 'voltage' in device_data:
                self.solar_voltage = float(device_data['voltage'])
                LOGGER.debug(f"Updated {self.name} solar voltage: {self.solar_voltage}V")
                
            if 'current' in device_data:
                self.solar_current = float(device_data['current'])
                LOGGER.debug(f"Updated {self.name} solar current: {self.solar_current}A")
                
            if 'state' in device_data:
                self.charge_state = int(device_data['state'])
                LOGGER.debug(f"Updated {self.name} charge state: {self.charge_state}")
                
            # Look for nested data structures
            if isinstance(device_data, dict):
                for key, value in device_data.items():
                    if isinstance(value, dict):
                        self.parse_device_data(value)
                        
        except Exception as ex:
            LOGGER.exception(f"Failed to parse device data for {self.name}: {ex}")

    def query(self, command=None):
        """Called when ISY queries solar charger"""
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
        
        # Remove demo simulation since we want zeros when no connection
        # Update drivers
        self.setDriver('ST', self.solar_power, 73)
        self.setDriver('GV0', self.charge_state, 68)
        self.setDriver('CV', self.solar_voltage, 72)
        self.setDriver('CC', self.battery_current, 1)
        self.setDriver('CPW', self.battery_voltage, 72)
        # Note: Temperature driver removed - SmartSolar MPPT doesn't provide temperature data
        self.setDriver('GV1', round(self.solar_yield_today, 2), 33)
        self.setDriver('GV2', self.max_power_today, 73)
        self.setDriver('GV7', int(self.battery_power), 73)
        # Load output drivers
        self.setDriver('GV3', self.load_output_state, 68)
        self.setDriver('GV4', self.load_current, 1)
        self.setDriver('GV5', self.load_voltage, 72)
        self.setDriver('GV6', int(self.load_power), 73)
        self.reportDrivers()

    def shortPoll(self):
        """Called every shortPoll seconds"""
        LOGGER.debug(f"Solar charger {self.name} - shortPoll triggered")
        self.query()

    def longPoll(self):
        """Called every longPoll seconds"""
        LOGGER.debug(f"Solar charger {self.name} - longPoll triggered")
        self.query()



    def parse_diagnostics_data(self, diagnostics_data):
        """Parse device data from VRM diagnostics for solar charger"""
        try:
            LOGGER.debug(f"===== SOLAR CHARGER PARSING DIAGNOSTICS DATA for {self.name} =====")
            LOGGER.debug(f"Looking for device instance: {self.device_instance}")
            
            if not diagnostics_data or 'records' not in diagnostics_data:
                LOGGER.warning(f"No diagnostics records for {self.name}")
                return None
                
            # Look for our device instance in the diagnostics data
            device_data = {}
            found_device = False
            
            for record in diagnostics_data['records']:
                if record.get('instance') == self.device_instance:
                    found_device = True
                    LOGGER.debug(f"Found diagnostics data for {self.name} instance {self.device_instance}")
                    
                    # Parse solar charger specific fields
                    raw_value = record.get('rawValue')
                    description = record.get('description', '').lower()
                    
                    if raw_value is not None:
                        # Solar power output (to battery)
                        if 'yield power' in description or 'battery power' in description:
                            device_data['power'] = float(raw_value)
                        # PV voltage  
                        elif 'pv voltage' in description or 'solar voltage' in description:
                            device_data['pv_voltage'] = float(raw_value)
                        # PV current
                        elif 'pv current' in description or 'solar current' in description:
                            device_data['pv_current'] = float(raw_value)
                        # Battery voltage from solar charger perspective
                        elif 'battery voltage' in description:
                            device_data['battery_voltage'] = float(raw_value)
                        # Battery current (charging current from MPPT)
                        elif description == 'current' or 'battery current' in description:
                            device_data['current'] = float(raw_value)
                        # Charge state
                        elif 'state' in description and 'charge' in description:
                            device_data['charge_state'] = int(raw_value)
                        # Yield today
                        elif 'yield today' in description:
                            device_data['yield_today'] = float(raw_value)
                        # Load output fields (for MPPT controllers with load outputs)
                        elif 'load output state' in description or 'load state' in description:
                            device_data['load_output_state'] = int(raw_value)
                        elif 'load current' in description:
                            device_data['load_current'] = float(raw_value)
                        elif 'load voltage' in description:
                            device_data['load_voltage'] = float(raw_value)
                        elif 'load power' in description:
                            device_data['load_power'] = float(raw_value)
                        # Additional comprehensive VRM field support
                        elif 'temperature' in description:
                            # Could be battery temperature or MPPT temperature
                            if 'battery' in description:
                                device_data['battery_temperature'] = float(raw_value)
                            else:
                                device_data['mppt_temperature'] = float(raw_value)
                        elif 'error code' in description:
                            device_data['error_code'] = int(raw_value)
                        elif 'yield yesterday' in description:
                            device_data['yield_yesterday'] = float(raw_value)
                        elif 'maximum charge power yesterday' in description:
                            device_data['max_power_yesterday'] = float(raw_value)
                            
            if found_device and device_data:
                LOGGER.debug(f"===== SOLAR DIAGNOSTICS DATA for {self.name} =====")
                LOGGER.debug(f"Solar diagnostics: {json.dumps(device_data, indent=2)}")
                LOGGER.debug(f"===== END SOLAR DIAGNOSTICS DATA =====")
                
                # Update our properties
                if 'power' in device_data:
                    self.solar_power = device_data['power']
                if 'pv_voltage' in device_data:
                    self.solar_voltage = device_data['pv_voltage']
                if 'pv_current' in device_data:
                    self.solar_current = device_data['pv_current']
                if 'current' in device_data:
                    self.battery_current = device_data['current']
                if 'battery_voltage' in device_data:
                    self.battery_voltage = device_data['battery_voltage']
                if 'charge_state' in device_data:
                    self.charge_state = device_data['charge_state']
                if 'yield_today' in device_data:
                    self.yield_today = device_data['yield_today']
                # Update load output properties
                if 'load_output_state' in device_data:
                    self.load_output_state = device_data['load_output_state']
                if 'load_current' in device_data:
                    self.load_current = device_data['load_current']
                if 'load_voltage' in device_data:
                    self.load_voltage = device_data['load_voltage']
                if 'load_power' in device_data:
                    self.load_power = device_data['load_power']
                
                # Update ISY drivers with proper scaling
                self.setDriver('ST', int(self.solar_power), 73)                      # Solar power in watts
                self.setDriver('GV0', self.charge_state, 68)                         # Charge state
                self.setDriver('CV', self.solar_voltage, 72)                         # Solar voltage in volts (V)
                self.setDriver('CC', self.battery_current, 1)                        # Battery current in amperes (A)
                self.setDriver('CPW', self.battery_voltage, 72)                      # Battery voltage in volts (V)
                self.setDriver('GV1', round(self.yield_today, 2), 33)                # Yield today in kWh
                # Update load output drivers
                self.setDriver('GV3', self.load_output_state, 68)                   # Load output state (0=Off, 1=On, 2=Unknown)
                self.setDriver('GV4', self.load_current, 1)                         # Load current in amperes (A)
                self.setDriver('GV5', self.load_voltage, 72)                        # Load voltage in volts (V)
                self.setDriver('GV6', int(self.load_power), 73)                     # Load power in watts
                self.reportDrivers()  # Report the updated drivers to ISY
                
                # Create load output status message
                load_status = ""
                if any(['load_output_state' in device_data, 'load_current' in device_data, 'load_voltage' in device_data, 'load_power' in device_data]):
                    load_state_text = "On" if self.load_output_state == 1 else ("Off" if self.load_output_state == 0 else "Unknown")
                    load_status = f", Load: {load_state_text} ({self.load_power}W, {self.load_voltage}V, {self.load_current}A)"
                else:
                    # Solar charger doesn't have load output or no load data available
                    load_status = ""
                
                LOGGER.info(f"Updated {self.name} from diagnostics - Power: {self.solar_power}W, PV: {self.solar_voltage}V/{self.solar_current}A, Battery: {self.battery_voltage}V, State: {self.charge_state} ({self.get_charge_state_text(self.charge_state)}){load_status}")
                return device_data
            else:
                LOGGER.warning(f"No diagnostics data found for {self.name} device instance {self.device_instance}")
                return None
                
        except Exception as ex:
            LOGGER.exception(f"Failed to parse diagnostics data for {self.name}: {ex}")
            return None

    # Define the drivers (status values) for this node
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 73},       # Solar power in watts
        {'driver': 'GV0', 'value': 0, 'uom': 68},      # Charge state (0=Off, 1=Bulk, 2=Absorption, 3=Float)
        {'driver': 'CV', 'value': 0, 'uom': 72},       # Solar voltage in volts (V)
        {'driver': 'CC', 'value': 0, 'uom': 1},        # Battery current in amperes (A) - positive=charging, negative=discharging
        {'driver': 'CPW', 'value': 0, 'uom': 72},      # Battery voltage in volts (V)
        # Note: CLITEMP (temperature) driver removed - SmartSolar MPPT 100/15 doesn't provide temperature data via VRM API
        {'driver': 'GV1', 'value': 0, 'uom': 33},      # Yield today in kWh
        {'driver': 'GV2', 'value': 0, 'uom': 73},      # Max power today in watts
        {'driver': 'GV7', 'value': 0, 'uom': 73},      # Battery power in watts
        # Load output drivers (for MPPT controllers with load outputs)
        {'driver': 'GV3', 'value': 2, 'uom': 68},       # Load output state (0=Off, 1=On, 2=Unknown)
        {'driver': 'GV4', 'value': 0, 'uom': 1},        # Load current in amperes (A)
        {'driver': 'GV5', 'value': 0, 'uom': 72},       # Load voltage in volts (V)
        {'driver': 'GV6', 'value': 0, 'uom': 73}        # Load power in watts
    ]

    # Define the node ID (must match nodedef) - we'll use VicBatt for now
    id = 'VicSolar'

    # Define the commands this node supports
    commands = {
        'QUERY': query
    }
