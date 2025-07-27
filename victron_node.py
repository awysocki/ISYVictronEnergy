import udi_interface

LOGGER = udi_interface.LOGGER


class VictronNode(udi_interface.Node):
    """Base class for all Victron device nodes"""
    
    def __init__(self, polyglot, primary, address, name):
        super().__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.name = name
        self.address = address
        self.primary = primary
        
        # Subscribe to polling
        polyglot.subscribe(polyglot.POLL, self.poll)
        
        # Set initial driver values to zero (connection verification)
        self.set_initial_drivers()

    def set_initial_drivers(self):
        """Set all drivers to zero initially - override in subclasses"""
        self.setDriver('ST', 0, 25)  # Status - 0 until we get real data

    def poll(self, pollflag):
        """Handle polling requests"""
        if pollflag == 'shortPoll':
            self.query()
        elif pollflag == 'longPoll':
            self.query()

    def query(self, command=None):
        """Query device for current status - override in subclasses"""
        LOGGER.info(f"Querying {self.name}")
        # Base implementation - subclasses should override
        pass

    def update_from_vrm(self):
        """Update device data from VRM API - override in subclasses"""
        # Base implementation - subclasses should override
        pass

    def get_vrm_client(self):
        """Get VRM client from controller"""
        try:
            controller = self.poly.getNode(self.primary)
            if controller and hasattr(controller, 'vrm_client'):
                return controller.vrm_client
        except Exception as ex:
            LOGGER.error(f"Failed to get VRM client: {ex}")
        return None

    def parse_device_data(self, device_data):
        """Parse device data from VRM API - override in subclasses"""
        # Base implementation - subclasses should override
        pass

    # Default drivers - subclasses should override
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 25}  # Status
    ]

    # Default node ID - subclasses should override  
    id = 'victron_base'

    # Default commands - subclasses can add more
    commands = {
        'QUERY': query
    }
