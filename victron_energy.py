#!/usr/bin/env python3

import udi_interface
import json
import sys
import time
from victron_api import VictronAPI

# Version information
VERSION = '1.0.0'

LOGGER = udi_interface.LOGGER

# Configuration help for custom parameters (HTML formatted for PG3)
configurationHelp = """
<h2>Victron Energy NodeServer Configuration</h2>
<p>Configure your Victron VRM connection and preferences:</p>

<h3>api_key - Victron VRM API Key</h3>
<p><strong>Required:</strong> Your Victron VRM API key from the VRM portal. 
<br>Get this from: <a href="https://vrm.victronenergy.com" target="_blank">VRM Portal</a> → Settings → API Keys</p>

<h3>temp_unit - Temperature Unit</h3>
<p><strong>Optional:</strong> Enter <code>C</code> or <code>Celsius</code> for Celsius (default), anything else for Fahrenheit.
<br>This affects all temperature readings displayed by the nodeserver.</p>

<h3>cache_ttl - Cache Duration (seconds)</h3>
<p><strong>Optional:</strong> How long to cache VRM data (1-999 seconds, default: 30).
<br>Reduces API calls when multiple queries happen quickly. Higher values reduce API usage but may delay updates.</p>

<hr>
<p><em>Version: """ + VERSION + """</em></p>
"""

class Controller(udi_interface.Node):
    # Define the drivers for the controller node
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 25},  # Connection status (0=Disconnected, 1=Connected)
        {'driver': 'GV0', 'value': 0, 'uom': 56}  # Cache status: seconds until next refresh (0=no cache)
    ]

    # Define the node ID 
    id = 'controller'

    def __init__(self, polyglot):
        super(Controller, self).__init__(polyglot, 'controller', 'controller', 'Victron Energy')
        self.poly = polyglot
        self.name = 'Victron Energy'
        self.address = 'controller'
        self.primary = 'controller'
        self.api_key = ''
        self.installation_id = ''
        self.temp_unit = 'C'  # Default to Celsius
        self.scanning = False
        self.private = None
        self.id = 'controller'
        self.hint = ''
        self.vrm_client = None
        
        # VRM data caching to reduce API calls
        self.vrm_cache = None
        self.vrm_cache_timestamp = None
        self.vrm_cache_ttl = 30  # Default cache for 30 seconds (configurable)
        
        # Set initial status to disconnected
        self.setDriver('ST', 0, 25)  # 0 = Disconnected
        self.setDriver('GV0', 0, 56)  # 0 = No cache
        
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.DISCOVER, self.discover)
        polyglot.subscribe(polyglot.POLL, self.poll)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.addNodeDone)
        
        # Set the configuration help
        polyglot.setCustomParamsDoc(configurationHelp)
        polyglot.updateProfile()
        polyglot.ready()
        self.poly.addNode(self)
    
    def parameterHandler(self, params):
        self.poly.Notices.clear()

        # Get temperature unit preference with simplified logic
        # C or "celsius" (any case) = Celsius, anything else = Fahrenheit  
        temp_unit_param = params.get('temp_unit', 'C').upper().strip()
        self.temp_unit = 'C' if (temp_unit_param == 'C' or temp_unit_param == 'CELSIUS') else 'F'
        LOGGER.debug(f"Temperature unit parameter: '{params.get('temp_unit', 'not set')}' -> Using: {self.temp_unit}")

        # Get cache TTL parameter (1-999 seconds, default 30)
        cache_ttl_param = params.get('cache_ttl', '30')
        try:
            cache_ttl = int(cache_ttl_param)
            if 1 <= cache_ttl <= 999:
                self.vrm_cache_ttl = cache_ttl
                LOGGER.debug(f"Cache TTL set to {self.vrm_cache_ttl} seconds")
            else:
                LOGGER.warning(f"Cache TTL {cache_ttl} out of range (1-999), using default 30 seconds")
                self.vrm_cache_ttl = 30
        except (ValueError, TypeError):
            LOGGER.warning(f"Invalid cache TTL '{cache_ttl_param}', using default 30 seconds")
            self.vrm_cache_ttl = 30

        # Get API key - this is the only required parameter
        if 'api_key' in params and params['api_key'] != '':
            self.api_key = params['api_key']
            LOGGER.info("API key received, connecting to Victron VRM")
            self.vrm_client = VictronAPI(self.api_key)
            self.discover()
        else:
            LOGGER.info('Missing api_key value.')
            self.poly.Notices['api'] = 'Please define Victron API key'
            return

    def get_cached_vrm_data(self):
        """Get VRM diagnostics data with caching to reduce API calls"""
        if not self.vrm_client or not self.installation_id:
            self.setDriver('GV0', 0, 56)  # No cache when no client
            return None
            
        now = time.time()
        
        # Check if we have valid cached data
        if (self.vrm_cache and self.vrm_cache_timestamp and 
            (now - self.vrm_cache_timestamp) < self.vrm_cache_ttl):
            cache_age = now - self.vrm_cache_timestamp
            seconds_left = max(0, int(self.vrm_cache_ttl - cache_age))
            self.setDriver('GV0', seconds_left, 56)  # Show seconds until refresh
            LOGGER.debug(f"Using cached VRM data (age: {cache_age:.1f}s, {seconds_left}s left)")
            return self.vrm_cache
            
        # Fetch fresh data and cache it
        LOGGER.debug("Fetching fresh VRM data")
        try:
            self.vrm_cache = self.vrm_client.get_diagnostics_data(self.installation_id)
            self.vrm_cache_timestamp = now
            self.setDriver('GV0', self.vrm_cache_ttl, 56)  # Full cache time available
            return self.vrm_cache
        except Exception as ex:
            LOGGER.exception(f"Failed to fetch VRM data: {ex}")
            self.setDriver('GV0', 0, 56)  # No cache on error
            return None

    def clear_vrm_cache(self):
        """Clear the VRM data cache to force fresh data on next request"""
        LOGGER.debug("Clearing VRM cache")
        self.vrm_cache = None
        self.vrm_cache_timestamp = None
        self.setDriver('GV0', 0, 56)  # No cache available

    def discover(self, *args, **kwargs):
        self.scanning = True
        LOGGER.info('Discovering Victron devices')
        
        # Set status to "connecting" 
        self.setDriver('ST', 0, 25)  # 0 = Disconnected/Connecting

        try:
            if not self.vrm_client:
                self.vrm_client = VictronAPI(self.api_key)
                
            devices = self.vrm_client.devices()
            LOGGER.debug(f"Raw devices record: {devices}")
            
            # Get the installation_id that was retrieved during devices() call
            if hasattr(self.vrm_client, 'installation_id') and self.vrm_client.installation_id:
                self.installation_id = self.vrm_client.installation_id
                LOGGER.info(f"Installation ID retrieved and stored: {self.installation_id}")
            else:
                LOGGER.warning(f"VRM client has no installation_id: hasattr={hasattr(self.vrm_client, 'installation_id')}, value={getattr(self.vrm_client, 'installation_id', 'N/A')}")
                
            # Double-check our stored installation_id
            LOGGER.debug(f"Controller installation_id after retrieval: {self.installation_id}")
            
            if devices:
                records = devices.get('records', {})
                devices_list = records.get('devices', [])
                LOGGER.debug(f"Devices found: {json.dumps(devices_list, indent=2)}")
                
                # If we got a valid response with devices, show good connection
                if self.api_key != '' and devices_list:
                    LOGGER.info(f"Connected to VRM - found {len(devices_list)} devices")
                    self.setDriver('ST', 1, 25)  # 1 = Connected/OK
                    self.reportDrivers()
                    
                    for dv in devices_list:
                        name = dv.get('productName', 'Unknown')
                        device_id = dv.get('machineSerialNumber', dv.get('identifier', 'unknown_id'))
                        product_code = dv.get('productCode', '').lower()
                        product_name = dv.get('productName', '').lower()
                        
                        LOGGER.debug(f"Device ID: {device_id}, Name: {name}, Product Code: {product_code}")
                        
                        # Determine node type based on product code or product name
                        node_type = None
                        if product_code in ['c012'] or 'cerbo' in product_name or 'gateway' in product_name:
                            from devices.gateway import VictronGateway
                            node_type = VictronGateway
                            LOGGER.info(f"Creating Gateway node: {name}")
                        elif product_code in ['c038'] or 'smartshunt' in product_name or 'battery monitor' in product_name:
                            from devices.battery_monitor import VictronBatteryMonitor
                            node_type = VictronBatteryMonitor
                            LOGGER.info(f"Creating Battery Monitor node: {name}")
                        elif product_code in ['a055'] or 'mppt' in product_name or 'solar charger' in product_name:
                            from devices.solar_charger import VictronSolarCharger
                            node_type = VictronSolarCharger
                            LOGGER.info(f"Creating Solar Charger node: {name}")
                        else:
                            LOGGER.debug(f"Unknown device type for {name} (product code: {product_code}), skipping")
                            continue
                        
                        # Create the node if we don't already have it
                        if not self.poly.getNode(device_id.lower()) and node_type:
                            LOGGER.info(f"Creating node with address: {device_id.lower()}")
                            device_node = node_type(self.poly, device_id.lower(), device_id.lower(), name)
                            
                            # Pass VRM connection info to the device node
                            device_node.vrm_client = self.vrm_client
                            device_node.installation_id = self.installation_id
                            device_node.device_id = device_id
                            device_node.device_info = dv
                            
                            # Pass temperature unit preference to all nodes
                            if hasattr(device_node, 'temp_unit'):
                                device_node.temp_unit = self.temp_unit
                                LOGGER.debug(f"Set temperature unit {self.temp_unit} for {name}")
                            
                            # Set device instance if available (needed for diagnostics parsing)
                            if 'instance' in dv:
                                device_node.device_instance = dv['instance']
                                LOGGER.debug(f"Set device instance {dv['instance']} for {name}")
                            
                            LOGGER.info(f"Adding node to polyglot: {device_node.name} ({device_node.address})")
                            try:
                                self.poly.addNode(device_node)
                                LOGGER.info(f"Node added successfully: {device_node.address}")
                                # Trigger initial update for newly created node
                                device_node.start()
                            except Exception as add_ex:
                                LOGGER.error(f"Failed to add node {device_node.address}: {add_ex}")
                        else:
                            if self.poly.getNode(device_id.lower()):
                                LOGGER.debug(f"Node {device_id.lower()} already exists")
                                # For existing nodes, get the node and trigger update
                                existing_node = self.poly.getNode(device_id.lower())
                                if existing_node and hasattr(existing_node, 'start'):
                                    existing_node.start()
                            else:
                                LOGGER.debug(f"Node type is None for device {name}")
                
                elif self.api_key != '' and not devices_list:
                    LOGGER.warning("VRM API connection successful but no devices found")
                    self.setDriver('ST', 1, 25)  # Still connected, just no devices
                    self.reportDrivers()
                else:
                    LOGGER.error("No API key provided")
                    self.setDriver('ST', 0, 25)  # No connection
                    self.reportDrivers()
            else:
                LOGGER.error("No devices data received from VRM API")
                self.setDriver('ST', 0, 25)  # Connection failed
                self.reportDrivers()

        except Exception as err:
            LOGGER.error(f'VRM API connection failed: {err}')
            self.setDriver('ST', 0, 25)  # Connection failed
            self.reportDrivers()
        else:
            LOGGER.info('Device discovery completed successfully')

        self.scanning = False

    def poll(self, pollflag):
        """Handle polling - update all device nodes with minimal VRM API calls"""
        if pollflag == 'shortPoll':
            LOGGER.info("Short poll started")
            self.update_all_devices()
        elif pollflag == 'longPoll':
            LOGGER.info("Long poll started")
            self.update_all_devices()

    def addNodeDone(self, data):
        """Handle addNode completion - trigger immediate update for new device nodes"""
        try:
            LOGGER.info(f"addNodeDone callback triggered with data: {data}")
            node_address = data.get('address')
            if not node_address or node_address == 'controller':
                LOGGER.debug("Skipping controller node in addNodeDone")
                return  # Skip controller node
                
            node = self.poly.getNode(node_address)
            LOGGER.info(f"addNodeDone: Retrieved node {node_address}: {node}")
            if node and hasattr(node, 'query'):
                LOGGER.debug(f"Node {node.name} ({node_address}) added - triggering initial query")
                try:
                    node.query()
                    LOGGER.debug(f"Initial query completed for {node.name}")
                except Exception as ex:
                    LOGGER.error(f"Failed to update newly added node {node.name}: {ex}")
            else:
                LOGGER.warning(f"Node {node_address} not found or missing update_from_vrm method")
        except Exception as ex:
            LOGGER.error(f"Error in addNodeDone handler: {ex}")

    def update_all_devices(self):
        """Update all device nodes with a single VRM API call set"""
        try:
            LOGGER.debug(f"update_all_devices called - checking prerequisites...")
            LOGGER.debug(f"VRM client exists: {self.vrm_client is not None}")
            LOGGER.debug(f"Controller installation_id: {self.installation_id}")
            if hasattr(self.vrm_client, 'installation_id'):
                LOGGER.debug(f"VRM client installation_id: {getattr(self.vrm_client, 'installation_id', 'None')}")
            
            if not self.vrm_client or not self.installation_id:
                LOGGER.warning(f"No VRM client ({self.vrm_client is not None}) or installation ID ({self.installation_id}) - skipping device updates")
                LOGGER.debug(f"VRM client status: {self.vrm_client}")
                LOGGER.debug(f"Installation ID: {self.installation_id}")
                
                # Try to recover installation_id from VRM client if it exists there
                if (self.vrm_client and hasattr(self.vrm_client, 'installation_id') 
                    and self.vrm_client.installation_id and not self.installation_id):
                    LOGGER.info(f"Recovering installation_id from VRM client: {self.vrm_client.installation_id}")
                    self.installation_id = self.vrm_client.installation_id
                else:
                    return

            LOGGER.debug("Updating all devices from VRM API with shared data call...")
        
            # Get fresh device overview data to ensure instances are current
            device_info_by_serial = {}
            try:
                devices = self.vrm_client.devices()
                if devices and 'records' in devices and 'devices' in devices['records']:
                    for device in devices['records']['devices']:
                        serial = device.get('machineSerialNumber')
                        if serial:
                            device_info_by_serial[serial.upper()] = device
            except Exception as ex:
                LOGGER.warning(f"Failed to get fresh device overview data: {ex}")
            
            # Get all device nodes
            device_nodes = []
            all_nodes = list(self.poly.nodes())  # Convert generator to list
            LOGGER.debug(f"All nodes found: {[str(node) for node in all_nodes]}")
            
            # Check if polyglot connection is still active
            try:
                poly_status = hasattr(self.poly, 'isConnected') and self.poly.isConnected()
                LOGGER.debug(f"Polyglot connection status: {poly_status}")
            except Exception as conn_ex:
                LOGGER.warning(f"Unable to check polyglot connection: {conn_ex}")
            
            LOGGER.debug(f"Starting to check {len(all_nodes)} nodes for polling...")
            
            for i, node in enumerate(all_nodes):
                try:
                    node_address = getattr(node, 'address', 'MISSING')
                    node_name = getattr(node, 'name', 'MISSING')
                    LOGGER.debug(f"Node {i}: {node_name} with address: {node_address}")
                    
                    if node and node_address != 'controller':  # Skip controller node
                        device_nodes.append(node)
                        LOGGER.debug(f"✓ Added device node: {node_name} ({node_address})")
                    else:
                        LOGGER.debug(f"✗ Skipped node: {node_name} (address: {node_address})")
                except Exception as ex:
                    LOGGER.error(f"Error processing node {i}: {ex}")
                    
            LOGGER.debug(f"Finished checking nodes. Found {len(device_nodes)} device nodes for polling.")
            
            LOGGER.debug(f"Total device nodes found for polling: {len(device_nodes)}")
            if not device_nodes:
                LOGGER.warning("No device nodes to update - this may indicate nodes were removed or polyglot connection issues")
                return

            # Make a single VRM diagnostics call for all devices (with caching)
            LOGGER.debug("Making single VRM diagnostics call for all devices")
            shared_diagnostics_data = self.get_cached_vrm_data()
            
            if not shared_diagnostics_data:
                LOGGER.warning("No diagnostics data received from VRM - falling back to individual device queries")
                # Fall back to individual queries if shared call fails
                for device_node in device_nodes:
                    try:
                        if hasattr(device_node, 'query'):
                            device_node.query()
                    except Exception as ex:
                        LOGGER.error(f"Failed to update device {device_node.name}: {ex}")
                return

            # Update each device node with the shared diagnostics data
            for device_node in device_nodes:
                try:
                    # Update device_info and device_instance from fresh overview data
                    if (hasattr(device_node, 'device_id') and device_node.device_id and 
                        device_node.device_id.upper() in device_info_by_serial):
                        fresh_device_info = device_info_by_serial[device_node.device_id.upper()]
                        device_node.device_info = fresh_device_info
                        
                        # Set device instance if available and missing
                        if ('instance' in fresh_device_info and 
                            hasattr(device_node, 'device_instance')):
                            if device_node.device_instance != fresh_device_info['instance']:
                                device_node.device_instance = fresh_device_info['instance']
                                LOGGER.debug(f"Updated device instance for {device_node.name}: {device_node.device_instance}")
                    
                    # Check if device instance is missing and try to set it from overview data
                    elif (hasattr(device_node, 'device_instance') and 
                        device_node.device_instance is None and 
                        hasattr(device_node, 'device_info') and 
                        device_node.device_info and 
                        'instance' in device_node.device_info):
                        device_node.device_instance = device_node.device_info['instance']
                        LOGGER.debug(f"Fixed missing device instance for {device_node.name}: {device_node.device_instance}")
                    
                    # Pass the shared data to each device for parsing
                    if hasattr(device_node, 'update_from_shared_data'):
                        device_node.update_from_shared_data(shared_diagnostics_data)
                        # Log device update with key stats
                        device_status = "OK"
                        key_value = ""
                        if hasattr(device_node, 'battery_percentage') and device_node.battery_percentage > 0:
                            key_value = f"SOC: {device_node.battery_percentage}%"
                        elif hasattr(device_node, 'battery_voltage') and device_node.battery_voltage > 0:
                            key_value = f"V: {device_node.battery_voltage}V"
                        elif hasattr(device_node, 'solar_power') and device_node.solar_power > 0:
                            key_value = f"Solar: {device_node.solar_power}W"
                        elif hasattr(device_node, 'pv_voltage') and device_node.pv_voltage > 0:
                            key_value = f"PV: {device_node.pv_voltage}V"
                        
                        LOGGER.debug(f"  • {device_node.name}: {device_status} {key_value}".strip())
                    else:
                        # Fallback to individual query for devices that don't support shared data
                        if hasattr(device_node, 'query'):
                            device_node.query()
                            LOGGER.debug(f"  • {device_node.name}: Updated (individual query)")
                except Exception as ex:
                    LOGGER.error(f"Failed to update device {device_node.name}: {ex}")

            LOGGER.debug(f"Poll completed - updated {len(device_nodes)} devices")

        except Exception as ex:
            LOGGER.exception(f"Failed to update devices: {ex}")

    def stop(self):
        LOGGER.info('Victron NodeServer Stopped')

    def removeNoticesAll(self, data):
        """Handle removal of notices"""
        LOGGER.debug(f"removeNoticesAll called with: {data}")

    def removeNotice(self, data):
        """Handle removal of individual notice"""
        LOGGER.debug(f"removeNotice called with: {data}")

    def delete(self):
        """Handle node deletion"""
        LOGGER.warning("Controller delete() method called - nodes may be getting removed")

    def updateDrivers(self, drivers):
        """Update the node's drivers from Polyglot."""
        self.drivers = drivers

    # Define the commands this node supports
    commands = {
        'DISCOVER': discover
    }

if __name__ == '__main__':
    try:
        polyglot = udi_interface.Interface('VictronNodeServer')
        polyglot.start(VERSION)
        Controller(polyglot)
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
