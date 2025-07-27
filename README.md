# ISY Victron Energy NodeServer (PG3x)

A comprehensive Polyglot v3 NodeServer for integrating Victron Energy | API Access | Depends on endpoint | Rate-limited to ~3 req/sec |

### Configure the NodeServer Universal Devices ISY home automation controllers.

## What is this?

This NodeServer provides complete integration of Victron Energy solar power systems with your [Universal Devices ISY](https://www.universal-devices.com/) home automation system. It monitors battery monitors (SmartShunt, BMV), solar charge controllers (MPPT), inverters (MultiPlus, Quattro, Phoenix), and system gateways (Cerbo GX, Venus GX) through the VRM Portal API.

## Prerequisites

- Universal Devices ISY controller
- Polyglot v3 system (IoP or standalone)
- Python 3.6+ (handled by Polyglot)
- **Developer Account**: Only required if you want to modify the code - regular users can install from the NodeServer Store
- Victron Energy devices with a **Cerbo GX** or **Venus GX** device connected to VRM Portal
- **VRM API Token**: Required for accessing your Victron device data (see Configuration below)

## Quick Start

**Get up and running in 5 minutes:**

1. **Install**: Look for "ISY Victron Energy NodeServer" in your Polyglot v3 NodeServer Store and install it
2. **Get API Token**: 
   - Go to https://vrm.victronenergy.com
   - Click **Preferences** (gear icon) → **Integrations** 
   - Create a new **API Token** and copy it
3. **Configure NodeServer**:
   - In Polyglot, go to your ISYVictronEnergy NodeServer → **Configuration**
   - Enter your **VRM API Token**
   - **Optional**: Set temperature units (Celsius/Fahrenheit) if desired
   - Save and restart the NodeServer
4. **Done**: Your Victron devices will automatically appear as nodes in your ISY

**Need help?** See the detailed Configuration section below.

## Features

### Device Monitoring
- **Battery Monitors** (SmartShunt, BMV series) - State of charge, voltage, current, power, temperature
- **Solar Charge Controllers** (MPPT series) - PV voltage/current/power, battery voltage/current, charge state, daily yield, peak power
- **Inverters** (MultiPlus, Quattro, Phoenix) - AC voltage/current/power/frequency, inverter state, temperature
- **System Gateway** (Cerbo GX, Venus GX) - System status, active alarms, device counts, VRM connection status

### System Integration
- **Real-time monitoring** via VRM Portal API with 2-minute update intervals
- **Automatic device discovery** - finds all compatible devices in your Victron installation
- **Connection verification** - all values default to zero until successful VRM connection
- **Comprehensive status tracking** - system health, device states, and alarm conditions
- **ISY-native integration** - appears as standard ISY devices with proper status indicators

## Installation

**For Regular Users**: This NodeServer will be available in the ISY NodeServer Store for easy installation. No developer access required.

**For Developers**: If you want to modify the code or install from source, you must first become a registered developer with Universal Devices. Open a support ticket at [Universal Devices Support](https://www.universal-devices.com/support/) and request developer access.

### Easy Installation (Recommended):

1. **Install from Store**: Look for "ISY Victron Energy NodeServer" in your Polyglot v3 NodeServer Store
2. **Install**: Click install from the store
3. **Start**: Start the NodeServer through Polyglot
4. **Configure**: Add your VRM API token (see Configuration below)
5. **Verify**: The Victron Energy system node and device nodes will appear in your ISY

### Developer Installation (Advanced):

**Note**: This method requires developer access and is only needed if you want to modify the code or install from source.

### Steps for Developer Installation:

1. **Become a Developer**: Request developer access from Universal Devices (see above)
2. **Get the Code**: Download or clone this repository from GitHub to your local machine
3. **Choose Installation Method**:

   **Method A: ZIP File Upload**
   - Create a ZIP file of the entire project directory
   - Log into your Polyglot v3 system web interface
   - Go to the NodeServer Store
   - Create a new LOCAL store item
   - Upload your ZIP file

   **Method B: Direct Copy to Device (Development Mode)**
   - Copy the entire `ISYVictronEnergy` directory to your ISY device (eisy or Polisy)
   - Default location: `/home/admin/plugins/ISYVictronEnergy/`
   - Log into your Polyglot v3 system web interface
   - Go to the NodeServer Store
   - Create a new LOCAL store item in development mode
   - Point the store to the directory location: `/home/admin/plugins/ISYVictronEnergy/`

4. **Install**: Install the NodeServer from your LOCAL store
5. **Start**: Start the NodeServer through Polyglot
6. **Configure**: Add your VRM API token (see Configuration below)
7. **Verify**: The Victron Energy system node and device nodes will appear in your ISY

## Configuration

### Getting Your VRM API Token

1. **Log into VRM Portal**: Go to https://vrm.victronenergy.com
2. **Navigate to Preferences**: Click on "Preferences" (gear icon) in the main interface
3. **Go to Integrations**: Click on "Integrations" in the Preferences menu
4. **Generate Token**: Create a new API token (may be called "Personal Access Token" or "API Token")
5. **Copy Token**: Save this token - you'll need it for the NodeServer

**Note**: If you don't see API token options in Integrations, your VRM Portal account may need additional permissions. Contact Victron support if API access is not available.

### 🔄 VRM Data Update Frequency

Understanding how VRM Portal updates data helps optimize your NodeServer polling settings:

#### 🧭 Default Logging Interval
- Most systems log data to VRM at a default interval of **15 minutes**
- This can be adjusted in the GX device under:
  - **Settings** → **VRM Portal** → **Interval**

#### ⚡ Real-Time Data (Dashboard Mode)
- When viewing the VRM dashboard in real-time mode, data updates every **2 seconds**
- This mode increases CPU and bandwidth usage and is only active while the dashboard is open

#### 📡 API Rate Limits
- The VRM API allows up to **3 requests per second** on average
- Rate limiting uses a rolling window of 200 requests, with one request removed every 0.33 seconds
- If exceeded, you'll get a `429 Too Many Requests` response with a `Retry-After` header

#### 🧠 Summary

| Mode | Update Frequency | Notes |
|------|------------------|-------|
| Standard Logging | Every 15 minutes | Configurable in GX settings |
| Real-Time Dashboard | Every 2 seconds | Only while dashboard is open |
| API Access | Depends on endpoint | Rate-limited to ~3 req/sec |

🔄 VRM Data Update Frequency
🧭 Default Logging Interval
- Most systems log data to VRM at a default interval of 15 minutes
- This can be adjusted in the GX device under:
- Settings → VRM Portal → Interval
⚡ Real-Time Data (Dashboard Mode)
- When viewing the VRM dashboard in real-time mode, data updates every 2 seconds
- This mode increases CPU and bandwidth usage and is only active while the dashboard is open
📡 API Rate Limits
- The VRM API allows up to 3 requests per second on average
- Rate limiting uses a rolling window of 200 requests, with one request removed every 0.33 seconds
- If exceeded, you’ll get a 429 Too Many Requests response with a Retry-After header

### Configure the NodeServer

1. **In Polyglot**: Go to your ISYVictronEnergy NodeServer
2. **Configuration**: Click on "Configuration" 
3. **Add API Token**: Enter your VRM API token in the "VRM API Token" field
   - **Example**: `e03ec962d5209774e8b48e501396e2a8eddf073284dfb82086c6ba479a8b69a7`
   - **Important**: Save this token somewhere safe - you can only view it once in VRM Portal!
4. **Temperature Units** (Optional): Choose Celsius or Fahrenheit for battery temperature displays
5. **Save**: Save the configuration
6. **Restart**: Restart the NodeServer to apply changes

The NodeServer will automatically:
- **Without API token**: Create only the main "Victron Energy" node showing "Disconnected" status
- **With invalid token**: Show "Authentication Failed" status  
- **With valid token**: Connect to your VRM Portal, discover your installations, and find all devices
- **After connection**: Create nodes for Gateway, Battery Monitors, Solar Chargers, and Inverters
- **During operation**: Update all device data every 2 minutes with zero values indicating connection issues

### For Development:
```bash
git clone https://github.com/awysocki/ISYVictronEnergy.git

# Method A: Create ZIP for upload
# Method B: Copy to device
scp -r ISYVictronEnergy admin@your-device-ip:/home/admin/plugins/
```

**Note**: Replace `your-device-ip` with your ISY device's IP address.

## Usage

The NodeServer creates nodes for each device type found in your Victron system:

### **Controller Node** (Main System Node)
- **System Status**: Overall VRM connection and system health
- **Installation Count**: Number of installations accessible with your API token

### **Gateway Node** (Cerbo GX / Venus GX)
- **Gateway Status**: Device online/offline status
- **System Status**: Overall system health and active alarms
- **Active Alarms**: Count of active system alarms
- **Device Count**: Total number of connected Victron devices
- **VRM Connection**: Connection status to VRM Portal

### **Battery Monitor Nodes** (SmartShunt, BMV series)
- **Battery Status**: Current operating state (charging/discharging/idle)
- **State of Charge**: Battery charge percentage (0-100%)
- **Voltage**: Battery voltage in volts
- **Current**: Current flow in amps (positive = charging, negative = discharging)
- **Power**: Power flow in watts
- **Temperature**: Battery temperature in Celsius

### **Solar Charger Nodes** (MPPT series)
- **Charger Status**: Current charge state (off/bulk/absorption/float/etc.)
- **PV Voltage**: Solar panel voltage
- **PV Current**: Solar panel current
- **PV Power**: Solar panel power
- **Battery Voltage**: Battery voltage seen by charger
- **Battery Current**: Current to battery
- **Yield Today**: Daily energy harvest in kWh
- **Peak Power Today**: Maximum power generated today

### **Inverter Nodes** (MultiPlus, Quattro, Phoenix)
- **Inverter Status**: Current operating state
- **AC Voltage**: AC output voltage
- **AC Current**: AC output current  
- **AC Power**: AC output power
- **AC Frequency**: AC output frequency
- **Temperature**: Inverter temperature

### **Automatic Updates**
- All data refreshes every 2 minutes from VRM Portal
- Zero values indicate connection or communication issues
- Responds to Query commands for immediate updates
- Connection status clearly visible in Controller node

### **Testing API Access**
You can test your VRM API access using these commands (replace YOUR_TOKEN with your actual token):

**Windows (PowerShell):**
```powershell
curl -X GET "https://vrmapi.victronenergy.com/v2/users/me" -H "accept: application/json" -H "X-Authorization: Token YOUR_TOKEN"
```

**Linux/FreeBSD:**
```bash
curl -X GET "https://vrmapi.victronenergy.com/v2/users/me" -H "accept: application/json" -H "X-Authorization: Token YOUR_TOKEN"
```

## Development

If you want to use this as a starting point for your own NodeServer:

1. Fork this repository
2. Modify `victron_energy.py` to add your custom functionality
3. Update `server.json` with your NodeServer details
4. Modify the profile files in `profile/` to match your nodes and capabilities
5. Test with your Polyglot system

## Files Structure

```
ISYVictronEnergy/
├── victron_energy.py          # Main NodeServer controller
├── victron_api.py             # VRM Portal API client
├── victron_node.py            # Base node class for all devices
├── devices/                   # Device-specific implementations
│   ├── __init__.py
│   ├── battery_monitor.py     # SmartShunt/BMV battery monitoring
│   ├── gateway.py             # Cerbo GX/Venus GX system gateway
│   ├── inverter.py            # MultiPlus/Quattro/Phoenix inverters
│   └── solar_charger.py       # MPPT solar charge controllers
├── profile/                   # ISY profile definitions
│   ├── version.txt            # Profile version
│   ├── editor/
│   │   └── editors.xml        # UI editor definitions
│   ├── nls/
│   │   └── en_us.txt          # Text labels and enumerations
│   └── nodedef/
│       └── nodedef.xml        # Node structure definitions
├── server.json                # NodeServer metadata
├── requirements.txt           # Python dependencies
├── install.sh                 # Installation script
├── README.md                  # This documentation
└── LICENSE                    # MIT License
```

### Key Components
- **victron_energy.py**: Main controller that manages all device nodes
- **victron_api.py**: Handles all VRM Portal API communication and authentication
- **victron_node.py**: Base class providing common node functionality
- **devices/**: Modular device classes for each Victron device type
- **profile/**: ISY-specific configuration files for UI integration

## Contributing

Contributions are welcome! If you find bugs or have suggestions for improvements, feel free to open an issue or submit a pull request.

## Resources

- [Universal Devices ISY](https://www.universal-devices.com/)
- [Polyglot v3 Documentation](https://polyglot.universal-devices.com/)
- [UDI Interface Library](https://github.com/UniversalDevicesInc/udi-interface)
- [Victron VRM API Documentation](https://vrm-api-docs.victronenergy.com/)
- [VRM Portal API Reference](https://vrm-api-docs.victronenergy.com/#/)
- [Victron Energy Developer Resources](https://www.victronenergy.com/live/open_source:start)

## Troubleshooting

### **NodeServer Installation Issues**
- Ensure you have developer access from Universal Devices
- Check that all files are included in your installation package
- Verify Python dependencies install correctly (check Polyglot System Logs)
- Ensure the NodeServer is started and running in Polyglot

### **VRM Connection Issues**
**Controller shows "Disconnected" or "Authentication Failed":**
- Verify your VRM API token is correct and active
- Test API access using curl commands (see Testing API Access section)
- Ensure your Polyglot system has internet connectivity

**All device values show zero:**
- This is normal behavior when VRM connection fails
- Check Controller node status for connection state
- Verify your Cerbo GX/Venus GX is online in VRM Portal
- Check VRM Portal for any account or permission issues

### **Device Discovery Issues**
**Expected devices not appearing:**
- Verify devices are connected and visible in VRM Portal
- Check that devices are properly configured in your Victron system
- Some devices may require specific firmware versions for VRM data
- Battery monitors require proper shunt configuration

**Incomplete device data:**
- Some data points may not be available on all device models
- Check your specific device documentation for supported metrics
- Older firmware versions may have limited data availability

### **Data Update Issues**
**Stale or non-updating data:**
- Check NodeServer logs for API errors or rate limiting
- Verify your VRM Portal account has proper access to the installation
- Try restarting the NodeServer to reset API connections
- Check for VRM Portal maintenance or outages

### **Debug Information**
**Log Files** (accessible through Polyglot web interface):
- **System Logs**: Initial loading and Python errors
- **NodeServer Logs**: Runtime VRM API communication and device updates
- **VRM API Responses**: Detailed API response analysis for troubleshooting

**Manual Testing**: Use ISY Query commands on individual nodes to trigger immediate updates

**Connection Verification**: Check Controller node status first - all other issues stem from VRM connection problems

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Version

1.0.0 - First public release for home Victron Energy system integration

### Changes in 1.0.0
- **First Public Release**: Initial stable release suitable for home solar systems
- **Temperature Monitoring**: Battery monitors (SmartShunt, BMV) provide accurate temperature readings
- **Solar Charger Optimization**: Removed temperature displays from solar chargers (no temperature sensors available)
- **ISY Integration**: Complete profile system with proper node definitions and status indicators
- **VRM API Integration**: Full authentication, error handling, and connection management
- **Device Support**: Battery monitors, solar chargers, inverters, and system gateways

## Current Status (July 2025)

This NodeServer provides **comprehensive monitoring** of complete Victron Energy solar power systems:

### ✅ Fully Implemented Features
- **Complete device support**: Battery monitors, solar chargers, inverters, and system gateways
- **Robust VRM API integration**: Full authentication, error handling, and connection management
- **Comprehensive monitoring**: All major device parameters with proper ISY integration
- **Connection verification**: Zero-default values clearly indicate VRM connection status
- **Professional ISY integration**: Complete profile with proper editors, labels, and node definitions
- **Modular architecture**: Separate device classes for maintainable and extensible code

### 🔧 Device Monitoring Capabilities
- **Battery Monitors**: SOC, voltage, current, power, temperature, and charge states
- **Solar Chargers**: PV and battery metrics, charge states, daily yield, peak power tracking  
- **Inverters**: AC voltage/current/power/frequency, operating states, temperature monitoring
- **System Gateway**: Overall status, alarm monitoring, device counts, VRM connectivity

### 📋 Ready for Home Use
1. **Core functionality operational** - all major features working for home solar systems
2. **Good quality implementation** - proper error handling, logging, and status reporting
3. **ISY native integration** - appears as standard ISY devices with full functionality
4. **Comprehensive documentation** - complete setup and troubleshooting guides
5. **Automatic device discovery** - detects all compatible devices in your system

### 🚀 Installation Ready for Home Systems
The NodeServer is ready for installation with home Victron Energy systems that include:
- Cerbo GX or Venus GX gateway device
- VRM Portal account with API access
- Any combination of compatible Victron devices (battery monitors, MPPT controllers, inverters)

**Note**: This is version 1.0.0 - suitable for home use but still evolving. Please report any issues you encounter.

