
import requests
import json
import udi_interface
LOGGER = udi_interface.LOGGER

URI = 'https://vrmapi.victronenergy.com/v2'

class VictronAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = URI
        self.installation_id = None
        self.user_id = None  # Store user ID for installations search        
        self.headers = {
            "X-Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def devices(self, fields="*"):
        LOGGER.debug("Retrieving device list from VRM")
        
        # Get user info first
        response = requests.get(f"{self.base_url}/users/me", headers=self.headers, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        
        if 'user' in response_data:
            user_data = response_data['user']
            self.user_id = user_data.get('id')        
            LOGGER.debug(f"User ID: {self.user_id}")
        else:
            LOGGER.error("No user data found in response")
            return None

        # Get installations
        endpoint = f"{self.base_url}/users/{self.user_id}/installations"            
        response = requests.get(endpoint, headers=self.headers, timeout=10)
        response.raise_for_status()
        installations_data = response.json()
        
        self.installation_id = None
        if 'records' in installations_data:
            installations = installations_data['records']
            if installations:
                # Use the first installation
                self.installation_id = installations[0].get('idSite')
                LOGGER.info(f"Found installation ID: {self.installation_id}")
            else:
                LOGGER.warning("No installations found in records")
                return None
        else:
            LOGGER.warning("No 'records' key in installations response")
            return None

        if self.installation_id:
            # Get system overview to find devices
            endpoint = f"{self.base_url}/installations/{self.installation_id}/system-overview"
            response = requests.get(endpoint, headers=self.headers, timeout=10)
            response.raise_for_status()
            overview_data = response.json()
            
            # Extract actual devices from system overview
            devices = []
            if 'records' in overview_data and 'devices' in overview_data['records']:
                real_devices = overview_data['records']['devices']
                
                for device in real_devices:
                    # Create device entry from real VRM data
                    device_entry = {
                        'productName': device.get('productName', 'Unknown Device'),
                        'machineSerialNumber': device.get('machineSerialNumber', ''),
                        'productCode': device.get('productCode', '').lower(),
                        'identifier': device.get('machineSerialNumber', f"device_{self.installation_id}")
                    }
                    
                    # Preserve the instance field if available (needed for battery monitors, solar chargers, etc.)
                    if 'instance' in device:
                        device_entry['instance'] = device['instance']
                        LOGGER.debug(f"Preserved instance {device['instance']} for {device_entry['productName']}")
                    
                    # Map device types based on product codes and names
                    product_code = device.get('productCode', '').lower()
                    device_name = device.get('name', '').lower()
                    
                    if product_code == 'c012' or 'gateway' in device_name:
                        device_entry['identifier'] = f"gateway_{self.installation_id}"
                    elif product_code == 'c038' or 'battery monitor' in device_name or 'smartshunt' in device.get('productName', '').lower():
                        device_entry['identifier'] = f"battery_{self.installation_id}"
                    elif product_code == 'a055' or 'solar charger' in device_name or 'mppt' in device.get('productName', '').lower():
                        device_entry['identifier'] = f"solar_{self.installation_id}"
                    elif 'inverter' in device_name or 'multiplus' in device.get('productName', '').lower():
                        device_entry['identifier'] = f"inverter_{self.installation_id}"
                    
                    devices.append(device_entry)
                    LOGGER.debug(f"Found device: {device_entry['productName']} ({device_entry['productCode']}) - {device_entry['identifier']}")
            
            LOGGER.info(f"Created {len(devices)} device entries from system overview")
            return {
                'records': {
                    'devices': devices
                }
            }
        else:
            LOGGER.warning("No installation_id found.")
            return None

    def get_diagnostics_data(self, installation_id):
        """Get live diagnostics data for all devices"""
        try:
            endpoint = f"{self.base_url}/installations/{installation_id}/diagnostics"
            
            LOGGER.debug(f"Getting diagnostics data for installation {installation_id}")
            LOGGER.debug(f"Diagnostics endpoint URL: {endpoint}")
            
            response = requests.get(endpoint, headers=self.headers, timeout=15)
            response.raise_for_status()
            diagnostics_data = response.json()
            
            LOGGER.debug(f"===== DIAGNOSTICS DATA =====")
            LOGGER.debug(f"Diagnostics response with {len(diagnostics_data.get('records', []))} records")
            LOGGER.debug(f"===== END DIAGNOSTICS DATA =====")
            
            return diagnostics_data
            
        except Exception as ex:
            LOGGER.error(f"Failed to get diagnostics data: {ex}")
            return None

    def get_system_overview(self, installation_id):
        """Get system overview data for a specific installation"""
        try:
            endpoint = f"{self.base_url}/installations/{installation_id}/system-overview"
            response = requests.get(endpoint, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as ex:
            LOGGER.error(f"Failed to get system overview: {ex}")
            return None

    def get_widgets(self, installation_id, widget_types=None):
        """Get widget data for specific installation"""
        try:
            endpoint = f"{self.base_url}/installations/{installation_id}/widgets"
            params = {}
            if widget_types:
                params['type'] = ','.join(widget_types)
            
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as ex:
            LOGGER.error(f"Failed to get widgets: {ex}")
            return None

    def get_diagnostics(self, installation_id):
        """Get diagnostics data for specific installation"""
        try:
            endpoint = f"{self.base_url}/installations/{installation_id}/diagnostics"
            response = requests.get(endpoint, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_ex:
            if http_ex.response.status_code == 404:
                LOGGER.warning(f"Diagnostics endpoint not available for installation {installation_id}")
            else:
                LOGGER.error(f"HTTP error getting diagnostics: {http_ex}")
            return None
        except Exception as ex:
            LOGGER.error(f"Failed to get diagnostics: {ex}")
            return None

    def get_device_data(self, installation_id, device_id):
        """Get specific device data using system overview and diagnostics"""
        try:
            LOGGER.debug(f"Getting device data for {device_id} from installation {installation_id}")
            
            # First try to get system overview
            overview_data = self.get_system_overview(installation_id)
            LOGGER.debug(f"===== SYSTEM OVERVIEW RAW DATA for {device_id} =====")
            LOGGER.debug(f"Overview data JSON: {json.dumps(overview_data, indent=2) if overview_data else 'None'}")
            LOGGER.debug(f"===== END SYSTEM OVERVIEW DATA =====")
            
            if overview_data and 'records' in overview_data:
                # Look for the specific device in the overview
                devices = overview_data['records'].get('devices', [])
                for device in devices:
                    if (device.get('machineSerialNumber') == device_id or 
                        device.get('identifier') == device_id):
                        LOGGER.info(f"Found device data in system overview: {device.get('productName')}")
                        device_result = {
                            'records': [device],
                            'success': True,
                            'source': 'system_overview'
                        }
                        LOGGER.debug(f"===== RETURNING DEVICE DATA for {device_id} =====")
                        LOGGER.debug(f"Device result JSON: {json.dumps(device_result, indent=2)}")
                        LOGGER.debug(f"===== END DEVICE DATA =====")
                        return device_result
            
            # If not found in overview, try diagnostics
            try:
                diagnostics_data = self.get_diagnostics(installation_id)
                LOGGER.debug(f"===== DIAGNOSTICS RAW DATA for {device_id} =====")
                LOGGER.debug(f"Diagnostics data JSON: {json.dumps(diagnostics_data, indent=2) if diagnostics_data else 'None'}")
                LOGGER.debug(f"===== END DIAGNOSTICS DATA =====")
                
                if diagnostics_data and 'records' in diagnostics_data:
                    LOGGER.debug(f"Using diagnostics data for device {device_id}")
                    diagnostics_result = {
                        'records': diagnostics_data['records'],
                        'success': True,
                        'source': 'diagnostics'
                    }
                    LOGGER.debug(f"===== RETURNING DIAGNOSTICS DATA for {device_id} =====")
                    LOGGER.debug(f"Diagnostics result JSON: {json.dumps(diagnostics_result, indent=2)}")
                    LOGGER.debug(f"===== END DIAGNOSTICS RESULT =====")
                    return diagnostics_result
            except Exception as diag_ex:
                LOGGER.warning(f"Diagnostics also failed for {device_id}: {diag_ex}")
            
            LOGGER.warning(f"No device data found for {device_id}")
            return None
            
        except Exception as ex:
            LOGGER.error(f"Failed to get device data for {device_id}: {ex}")
            return None
