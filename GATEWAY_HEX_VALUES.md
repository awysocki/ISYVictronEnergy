# Gateway Hex Value Reference

The Victron Gateway node displays several dynamic enum values in hexadecimal format for easier interpretation.

## ESS Battery Life State (GV6)
Shows the current ESS (Energy Storage System) battery life state:
- `0x00` = External control or BL disabled
- `0x01` = Restarting  
- `0x02` = Self-consumption
- `0x03` = Self-consumption
- `0x04` = Self-consumption
- `0x05` = Discharged
- `0x06` = Slow charge
- `0x07` = Sustain
- `0x08` = Auto-recharge
- `0x09` = Keep batteries charged
- `0x0A` = BL Disabled
- `0x0B` = BL Disabled (Low SoC)
- `0x0C` = BL Disabled (Auto-recharge)

## Services Status Bitmask (GV8)
Shows which system services are currently enabled:
- Bit 0 (`0x01`) = MQTT Local (secure MQTT broker)
- Bit 1 (`0x02`) = VNC Internet (remote desktop access)
- Bit 2 (`0x04`) = Remote Support (Victron support access)
- Bit 3 (`0x08`) = SignalK (marine data protocol)

Examples:
- `0x00` = No services enabled
- `0x01` = Only MQTT enabled
- `0x03` = MQTT + VNC enabled
- `0x0F` = All services enabled

## Relay States Bitmask (GV11)
Shows the current state of the gateway's relays:
- Bit 0 (`0x01`) = Relay 1 state (1=closed/active, 0=open/inactive)
- Bit 1 (`0x02`) = Relay 2 state (1=closed/active, 0=open/inactive)

Examples:
- `0x00` = Both relays open
- `0x01` = Relay 1 closed, Relay 2 open
- `0x02` = Relay 1 open, Relay 2 closed  
- `0x03` = Both relays closed

## Network Type (GV5)
Shows how the gateway is connected to the network:
- `0` = Not connected
- `1` = Ethernet
- `2` = WiFi
- `3` = Modem

## Other Useful Values
- **Free Disk Space (GV4)**: Shown in megabytes (MB)
- **ESS SOC Limit (GV7)**: Battery minimum state of charge in percentage
- **System Errors (GV9)**: Count of hung + zombie processes
- **Grid Setpoint (GV10)**: ESS grid setpoint in watts
