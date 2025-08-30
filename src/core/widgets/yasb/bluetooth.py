"""
This is very experimental and may not work as expected. It uses ctypes to interact with the Windows Bluetooth API. We need to test this on more systems to ensure it works as expected.
"""

import ctypes
import logging
import os
import re
from ctypes import wintypes

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from core.utils.tooltip import set_tooltip
from core.utils.utilities import add_shadow, build_widget_label
from core.utils.widgets.animation_manager import AnimationManager
from core.validation.widgets.yasb.bluetooth import VALIDATION_SCHEMA
from core.widgets.base import BaseWidget
from settings import DEBUG

try:
    from winrt.windows.devices.bluetooth import BluetoothDevice
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.storage.streams import DataReader
    import uuid
    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False
    if DEBUG:
        logging.warning("WinRT Bluetooth APIs not available for battery monitoring")


# Windows SetupAPI constants and structures for device property access
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
ERROR_SUCCESS = 0
ERROR_NO_MORE_ITEMS = 259
CR_SUCCESS = 0x00000000

# HID Constants for Battery Service
HID_USAGE_PAGE_GENERIC_DESKTOP = 0x01
HID_USAGE_PAGE_BATTERY_SYSTEM = 0x85
HID_USAGE_BATTERY_SYSTEM_BATTERY_CAPACITY = 0x66
HID_USAGE_BATTERY_SYSTEM_CHARGING = 0x44
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3

class DEVPROPKEY(ctypes.Structure):
    _fields_ = [
        ("fmtid", ctypes.c_ubyte * 16),  # GUID as byte array
        ("pid", wintypes.ULONG),
    ]

class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", ctypes.c_ubyte * 16),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]

class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", ctypes.c_ubyte * 16),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]

class SP_DEVICE_INTERFACE_DETAIL_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1),
    ]

class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]

# Device property keys for battery-related information
# Based on extensive testing, we found multiple sources of battery data
DEVICE_PROPERTY_KEYS = [
    # FOUND: The actual battery level Windows Settings uses (70%)
    {"name": "DEVPKEY_HandsFree_BatteryLevel", "guid": b'\x19\xA3\x4E\x10\xE2\x6E\x01\x47\xBD\x47\x8D\xDB\xF4\x25\xBB\xE5', "pid": 2},
    # PowerData contains cached/older battery data (56%)
    {"name": "DEVPKEY_Device_PowerData", "guid": b'\x4E\x25\x5C\xA4\x1C\xDF\xFD\x4E\x80\x20\x67\xD1\x46\xA8\x50\xE0', "pid": 32},
    # Additional battery-related property keys to check
    {"name": "DEVPKEY_Device_BatteryLife", "guid": b'\x4E\x25\x5C\xA4\x1C\xDF\xFD\x4E\x80\x20\x67\xD1\x46\xA8\x50\xE0', "pid": 10},
    {"name": "DEVPKEY_Device_BatteryPlusCharging", "guid": b'\x49\xCF\x32\x88\x7D\x6E\x96\x41\x80\xE2\xD2\x0A\x5B\x9E\x9C\x89', "pid": 22},
    {"name": "DEVPKEY_Device_BatteryPlusChargingText", "guid": b'\x49\xCF\x32\x88\x7D\x6E\x96\x41\x80\xE2\xD2\x0A\x5B\x9E\x9C\x89', "pid": 23},
]


class WindowsDevicePropertyReader:
    """Windows SetupAPI wrapper for reading device properties."""
    
    def __init__(self):
        # Load required DLLs
        try:
            self.setupapi = ctypes.windll.setupapi
            self.cfgmgr32 = ctypes.windll.cfgmgr32
            self.kernel32 = ctypes.windll.kernel32
            # HID APIs for battery service
            try:
                self.hid = ctypes.windll.hid
                self.hid_available = True
            except:
                self.hid = None
                self.hid_available = False
                if DEBUG:
                    logging.debug("HID API not available")
        except Exception as e:
            if DEBUG:
                logging.error(f"Failed to load Windows APIs for device properties: {e}")
            raise
    
    def get_device_battery_level(self, device_address):
        """
        Get battery level for a Bluetooth device using multiple detection methods.
        Priority: HID Battery Service > Device Properties > Registry
        Args:
            device_address: Bluetooth address in format "F4:B6:2D:F5:94:38"
        Returns:
            Battery level percentage (int) or None if not available
        """
        try:
            # Convert MAC address to the format used in device instance IDs
            device_addr_clean = device_address.replace(":", "").upper()
            
            # Priority 1: Try HID Battery Service (most accurate, used by Windows Settings)
            if self.hid_available:
                battery_level = self._get_battery_from_hid(device_addr_clean)
                if battery_level is not None:
                    if DEBUG:
                        logging.debug(f"Found battery {battery_level}% via HID Battery Service")
                    return battery_level
            
            # Priority 2: Device properties approach with refresh - check ALL device instances
            device_instances = self._find_bluetooth_device_instance(device_addr_clean)
            if device_instances:
                # Prioritize Hands-Free AG instance since that's where Windows Settings gets the real battery level
                hands_free_instances = [inst for inst in device_instances if "111e" in inst.lower()]  # Hands-Free AG UUID
                other_instances = [inst for inst in device_instances if "111e" not in inst.lower()]
                
                # Check hands-free instances first, then others
                for device_instance_id in hands_free_instances + other_instances:
                    if DEBUG:
                        logging.debug(f"Checking device instance: {device_instance_id}")
                    
                    dev_node = self._get_device_node(device_instance_id)
                    if dev_node:
                        # Try to refresh device properties first
                        self._refresh_device_properties(dev_node)
                        
                        battery_level = self._read_battery_properties(dev_node)
                        if battery_level is not None:
                            if DEBUG:
                                logging.debug(f"Found battery {battery_level}% via device properties from {device_instance_id}")
                            return battery_level
            
            # Priority 3: Registry approach (fallback)
            battery_level = self._get_battery_from_registry(device_addr_clean)
            if battery_level is not None:
                if DEBUG:
                    logging.debug(f"Found battery {battery_level}% via registry")
                return battery_level
            
            if DEBUG:
                logging.debug(f"No battery level found for {device_address}")
            return None
            
        except Exception as e:
            if DEBUG:
                logging.error(f"Error getting battery level for {device_address}: {e}")
            return None
    
    def _find_bluetooth_device_instance(self, device_address):
        """Find the device instance ID for a Bluetooth device."""
        try:
            # Common patterns for Bluetooth device instance IDs
            possible_patterns = [
                f"BTHENUM\\DEV_{device_address}",
                f"BTHENUM\\{{*}}\\DEV_{device_address}",
                f"USB\\VID_*\\{device_address}",
            ]
            
            # Use CM_Get_Device_ID_List to enumerate devices
            buffer_size = wintypes.ULONG(0)
            
            # Get required buffer size
            result = self.cfgmgr32.CM_Get_Device_ID_List_SizeW(
                ctypes.byref(buffer_size),
                None,
                0
            )
            
            if result != CR_SUCCESS:
                return None
            
            # Allocate buffer and get device list
            buffer = (wintypes.WCHAR * buffer_size.value)()
            result = self.cfgmgr32.CM_Get_Device_ID_ListW(
                None,
                buffer,
                buffer_size,
                0
            )
            
            if result != CR_SUCCESS:
                return None
            
            # Parse the device ID list (null-terminated strings)
            device_ids = []
            current_id = ""
            for char in buffer:
                if char == '\0':
                    if current_id:
                        device_ids.append(current_id)
                        current_id = ""
                    else:
                        break  # Double null terminates the list
                else:
                    current_id += char
            
            # Search for our device, prioritizing the main Bluetooth device instance
            matching_devices = []
            for device_id in device_ids:
                if device_address.lower() in device_id.lower():
                    matching_devices.append(device_id)
                    if DEBUG:
                        logging.debug(f"Found matching device ID: {device_id}")
            
            if not matching_devices:
                return None
            
            # For battery detection, we need to check all instances since battery info
            # might be in service-specific instances (like Hands-Free AG)
            # Return all matching instances for comprehensive battery search
            if DEBUG:
                logging.debug(f"Found {len(matching_devices)} matching device instances")
            return matching_devices
            
        except Exception as e:
            if DEBUG:
                logging.error(f"Error finding device instance for {device_address}: {e}")
            return None
    
    def _get_device_node(self, device_instance_id):
        """Get device node handle for a device instance ID."""
        try:
            dev_node = wintypes.DWORD()
            
            # Convert string to wide string
            instance_id_w = ctypes.create_unicode_buffer(device_instance_id)
            
            result = self.cfgmgr32.CM_Locate_DevNodeW(
                ctypes.byref(dev_node),
                instance_id_w,
                0
            )
            
            if result != CR_SUCCESS:
                if DEBUG:
                    logging.debug(f"CM_Locate_DevNodeW failed with result: {result}")
                return None
            
            return dev_node.value
            
        except Exception as e:
            if DEBUG:
                logging.error(f"Error getting device node for {device_instance_id}: {e}")
            return None
    
    def _read_battery_properties(self, dev_node):
        """Read battery-related properties from device node."""
        try:
            # Try each battery-related property key
            for prop_key in DEVICE_PROPERTY_KEYS:
                try:
                    # Create DEVPROPKEY structure
                    key = DEVPROPKEY()
                    ctypes.memmove(key.fmtid, prop_key["guid"], 16)
                    key.pid = prop_key["pid"]
                    
                    # Get property value
                    prop_type = wintypes.ULONG()
                    buffer_size = wintypes.ULONG(0)
                    
                    # First call to get required buffer size
                    result = self.cfgmgr32.CM_Get_DevNode_PropertyW(
                        dev_node,
                        ctypes.byref(key),
                        ctypes.byref(prop_type),
                        None,
                        ctypes.byref(buffer_size),
                        0
                    )
                    
                    if DEBUG:
                        logging.debug(f"Property {prop_key['name']} initial result: {result}, buffer_size: {buffer_size.value}")
                    
                    # Result 26 = ERROR_MORE_DATA, which means we need to allocate buffer
                    if (result == 26 or result == 0) and buffer_size.value > 0:
                        # Allocate buffer and get actual data
                        buffer = (ctypes.c_ubyte * buffer_size.value)()
                        result = self.cfgmgr32.CM_Get_DevNode_PropertyW(
                            dev_node,
                            ctypes.byref(key),
                            ctypes.byref(prop_type),
                            buffer,
                            ctypes.byref(buffer_size),
                            0
                        )
                        
                        if DEBUG:
                            logging.debug(f"Property {prop_key['name']} final result: {result}, prop_type: {prop_type.value}")
                        
                        if result == CR_SUCCESS:
                            # Parse the property value based on type
                            battery_level = self._parse_property_value(buffer, prop_type.value, buffer_size.value)
                            if battery_level is not None:
                                if DEBUG:
                                    logging.debug(f"Found battery level {battery_level} from property {prop_key['name']}")
                                return battery_level
                
                except Exception as prop_error:
                    if DEBUG:
                        logging.debug(f"Error reading property {prop_key['name']}: {prop_error}")
                    continue
            
            # Also try reading from device registry properties
            return self._read_registry_battery_properties(dev_node)
            
        except Exception as e:
            if DEBUG:
                logging.error(f"Error reading battery properties: {e}")
            return None
    
    def _parse_property_value(self, buffer, prop_type, buffer_size):
        """Parse property value based on its type."""
        try:
            # Property types from Windows SDK
            DEVPROP_TYPE_UINT32 = 0x00000007
            DEVPROP_TYPE_STRING = 0x00000012
            DEVPROP_TYPE_BYTE = 0x00000003
            DEVPROP_TYPE_BINARY = 0x00000005
            
            if DEBUG:
                # Log the raw data for analysis
                raw_data = [buffer[i] for i in range(min(buffer_size, 64))]  # First 64 bytes
                logging.debug(f"Raw property data (type={prop_type}, size={buffer_size}): {raw_data}")
            
            if prop_type == DEVPROP_TYPE_BYTE and buffer_size >= 1:
                # Single byte value - likely battery percentage (this is what Windows Settings uses!)
                battery_level = buffer[0]
                if 0 <= battery_level <= 100:
                    if DEBUG:
                        logging.debug(f"Found byte battery level: {battery_level}%")
                    return battery_level
            elif prop_type == DEVPROP_TYPE_UINT32 and buffer_size >= 4:
                # 32-bit integer value
                value = ctypes.c_uint32.from_buffer(buffer).value
                if 0 <= value <= 100:
                    return value
            elif prop_type == DEVPROP_TYPE_BINARY or prop_type == DEVPROP_TYPE_UINT32 or prop_type == 4099:
                # Binary data or special property type 4099 (PowerData)
                # Property type 4099 is what we see for PowerData
                return self._parse_power_data_binary(buffer, buffer_size)
            elif prop_type == DEVPROP_TYPE_STRING:
                # String value - might contain battery info
                try:
                    string_val = ctypes.wstring_at(ctypes.addressof(buffer))
                    # Look for percentage in the string
                    import re
                    match = re.search(r'(\d+)%', string_val)
                    if match:
                        return int(match.group(1))
                except:
                    pass
            
            return None
            
        except Exception as e:
            if DEBUG:
                logging.debug(f"Error parsing property value: {e}")
            return None
    
    def _parse_power_data_binary(self, buffer, buffer_size):
        """
        Parse PowerData binary format for battery information.
        Based on analysis, PowerData contains battery percentage at byte offset 0.
        """
        try:
            if buffer_size < 1:
                return None
            
            # Convert buffer to list of bytes for analysis
            data = [buffer[i] for i in range(buffer_size)]
            
            if DEBUG:
                logging.debug(f"PowerData binary analysis: {data[:16]} (showing first 16 bytes)")
            
            # Based on testing with soundcore R50i NC:
            # - Battery level appears to be at byte offset 0
            # - Format: [battery_level, 0, 0, 0, flags, 0, 0, 0, secondary_battery?, ...]
            # - First byte (offset 0) contains the main battery percentage
            
            main_battery = data[0]
            if 0 < main_battery <= 100:  # Reasonable battery range
                if DEBUG:
                    logging.debug(f"Found main battery level: {main_battery}%")
                
                # Check if there's a secondary battery (e.g., charging case)
                if buffer_size >= 9:
                    secondary_battery = data[8]
                    if 0 < secondary_battery <= 100:
                        if DEBUG:
                            logging.debug(f"Found secondary battery level: {secondary_battery}%")
                        # For now, return the main battery level
                        # Future enhancement could return both values
                
                return main_battery
            
            # Fallback: search for reasonable battery values at other offsets
            potential_offsets = [1, 4, 8, 12, 16]  # Common structure offsets
            for offset in potential_offsets:
                if offset < buffer_size:
                    value = data[offset]
                    if 10 <= value <= 100:  # More restrictive range for fallback
                        if DEBUG:
                            logging.debug(f"Found fallback battery level {value}% at offset {offset}")
                        return value
            
            if DEBUG:
                logging.debug("No valid battery level found in PowerData")
            return None
            
        except Exception as e:
            if DEBUG:
                logging.debug(f"Error parsing PowerData binary: {e}")
            return None
    
    def _validate_battery_value(self, data, offset, value):
        """
        Validate that a potential battery value is likely correct.
        This helps avoid false positives from random binary data.
        """
        try:
            # Simple validation rules:
            # 1. Value should be reasonable (not too close to common binary patterns)
            # 2. Surrounding data shouldn't be all zeros or all 255s
            # 3. Value shouldn't be part of a sequence (like 1,2,3,4...)
            
            if value in [255, 0, 1]:  # Too common in binary data
                return False
            
            # Check surrounding bytes aren't all the same
            start = max(0, offset - 2)
            end = min(len(data), offset + 3)
            surrounding = data[start:end]
            if len(set(surrounding)) <= 2:  # Too uniform
                return False
            
            return True
            
        except Exception:
            return False
    
    def _read_registry_battery_properties(self, dev_node):
        """Try to read battery info from device registry properties."""
        try:
            # Common device registry properties that might contain battery info
            reg_properties = [
                0x00000001,  # SPDRP_DEVICEDESC
                0x00000000,  # SPDRP_DEVICENAME  
                0x0000000C,  # SPDRP_FRIENDLYNAME
                0x00000020,  # SPDRP_PHYSICAL_DEVICE_OBJECT_NAME
            ]
            
            for prop in reg_properties:
                try:
                    buffer_size = wintypes.DWORD(0)
                    prop_type = wintypes.DWORD()
                    
                    # Get required buffer size
                    result = self.setupapi.SetupDiGetDeviceRegistryPropertyW(
                        None,  # We'll use CM API instead
                        None,
                        prop,
                        ctypes.byref(prop_type),
                        None,
                        0,
                        ctypes.byref(buffer_size)
                    )
                    
                    # This approach requires SetupDi device info, skip for now
                    # We've already tried the main property keys above
                    
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            if DEBUG:
                logging.debug(f"Error reading registry battery properties: {e}")
            return None
    
    def _get_battery_from_registry(self, device_address):
        """
        Get battery level from Windows Registry for Bluetooth devices.
        This accesses the same registry location that Windows Settings uses.
        """
        try:
            import winreg
            
            # Registry path where Bluetooth device information is stored
            registry_path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
            
            try:
                # Open the Bluetooth devices registry key
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, registry_path) as devices_key:
                    # Look for our device by address
                    device_key_name = device_address.lower()
                    
                    try:
                        # Open the specific device key
                        with winreg.OpenKey(devices_key, device_key_name) as device_key:
                            # Try to read various battery-related values
                            battery_keys_to_try = [
                                "BatteryLevel", "Battery", "BatteryPercent", "Power", 
                                "BatteryLife", "Charge", "PowerLevel", "BatteryStatus"
                            ]
                            
                            for key_name in battery_keys_to_try:
                                try:
                                    value, reg_type = winreg.QueryValueEx(device_key, key_name)
                                    if DEBUG:
                                        logging.debug(f"Found registry value {key_name}: {value} (type: {reg_type})")
                                    
                                    # Try to parse battery level from the value
                                    if isinstance(value, int) and 0 <= value <= 100:
                                        return value
                                    elif isinstance(value, bytes):
                                        # Try to extract percentage from binary data
                                        if len(value) >= 1:
                                            byte_val = value[0]
                                            if 0 <= byte_val <= 100:
                                                return byte_val
                                    elif isinstance(value, str):
                                        # Try to extract percentage from string
                                        import re
                                        match = re.search(r'(\d+)%?', str(value))
                                        if match:
                                            percent = int(match.group(1))
                                            if 0 <= percent <= 100:
                                                return percent
                                        
                                except FileNotFoundError:
                                    continue  # This value doesn't exist, try the next one
                                except Exception as val_error:
                                    if DEBUG:
                                        logging.debug(f"Error reading registry value {key_name}: {val_error}")
                                    continue
                                    
                            # Also try to enumerate all values to see what's available
                            if DEBUG:
                                try:
                                    i = 0
                                    logging.debug(f"All registry values for device {device_address}:")
                                    while True:
                                        try:
                                            name, value, reg_type = winreg.EnumValue(device_key, i)
                                            # Look for battery-related names or values
                                            name_lower = name.lower()
                                            if any(term in name_lower for term in ['battery', 'power', 'charge', 'level']):
                                                logging.debug(f"  Battery-related: {name} = {value} (type: {reg_type})")
                                            else:
                                                logging.debug(f"  {name} = {value} (type: {reg_type})")
                                            i += 1
                                        except OSError:
                                            break
                                except Exception as enum_error:
                                    logging.debug(f"Error enumerating registry values: {enum_error}")
                            
                    except FileNotFoundError:
                        if DEBUG:
                            logging.debug(f"Device registry key not found: {device_key_name}")
                        return None
                        
            except FileNotFoundError:
                if DEBUG:
                    logging.debug(f"Bluetooth devices registry path not found: {registry_path}")
                return None
                
        except ImportError:
            if DEBUG:
                logging.debug("winreg module not available")
            return None
        except Exception as e:
            if DEBUG:
                logging.error(f"Error reading battery from registry: {e}")
            return None
    
    def _get_battery_from_hid(self, device_address):
        """
        Get battery level from HID Battery Service.
        This is the method Windows Settings likely uses for accurate battery readings.
        """
        try:
            if not self.hid_available:
                return None
            
            # HID Class GUID for battery devices
            hid_guid = ctypes.c_ubyte * 16
            hid_class_guid = hid_guid()
            
            # Get HID Class GUID
            self.hid.HidD_GetHidGuid(ctypes.byref(hid_class_guid))
            
            # Get device info set for HID devices
            device_info_set = self.setupapi.SetupDiGetClassDevsW(
                ctypes.byref(hid_class_guid),
                None,
                None,
                DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
            )
            
            if device_info_set == -1:  # INVALID_HANDLE_VALUE
                return None
            
            try:
                device_index = 0
                while True:
                    # Enumerate device interfaces
                    device_interface_data = SP_DEVICE_INTERFACE_DATA()
                    device_interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
                    
                    if not self.setupapi.SetupDiEnumDeviceInterfaces(
                        device_info_set,
                        None,
                        ctypes.byref(hid_class_guid),
                        device_index,
                        ctypes.byref(device_interface_data)
                    ):
                        break  # No more devices
                    
                    # Get device interface details
                    required_size = wintypes.DWORD(0)
                    self.setupapi.SetupDiGetDeviceInterfaceDetailW(
                        device_info_set,
                        ctypes.byref(device_interface_data),
                        None,
                        0,
                        ctypes.byref(required_size),
                        None
                    )
                    
                    if required_size.value > 0:
                        # Allocate buffer for device path
                        detail_size = required_size.value
                        detail_buffer = ctypes.create_string_buffer(detail_size)
                        detail_data = ctypes.cast(detail_buffer, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA))
                        detail_data.contents.cbSize = 6 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8
                        
                        if self.setupapi.SetupDiGetDeviceInterfaceDetailW(
                            device_info_set,
                            ctypes.byref(device_interface_data),
                            detail_data,
                            detail_size,
                            None,
                            None
                        ):
                            # Get device path
                            device_path_addr = ctypes.addressof(detail_data.contents.DevicePath)
                            device_path = ctypes.wstring_at(device_path_addr)
                            
                            # Check if this HID device belongs to our Bluetooth device
                            if device_address.lower() in device_path.lower():
                                battery_level = self._read_hid_battery(device_path)
                                if battery_level is not None:
                                    return battery_level
                    
                    device_index += 1
                    
            finally:
                self.setupapi.SetupDiDestroyDeviceInfoList(device_info_set)
            
            return None
            
        except Exception as e:
            if DEBUG:
                logging.debug(f"Error getting battery from HID: {e}")
            return None
    
    def _read_hid_battery(self, device_path):
        """Read battery level from a HID device path."""
        try:
            # Open HID device
            device_handle = self.kernel32.CreateFileW(
                device_path,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None
            )
            
            if device_handle == -1:  # INVALID_HANDLE_VALUE
                return None
            
            try:
                # Get device attributes
                attributes = HIDD_ATTRIBUTES()
                attributes.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
                
                if not self.hid.HidD_GetAttributes(device_handle, ctypes.byref(attributes)):
                    return None
                
                # Get preparsed data
                preparsed_data = ctypes.c_void_p()
                if not self.hid.HidD_GetPreparsedData(device_handle, ctypes.byref(preparsed_data)):
                    return None
                
                try:
                    # Get device capabilities
                    caps = HIDP_CAPS()
                    if self.hid.HidP_GetCaps(preparsed_data, ctypes.byref(caps)) != 0x110000:  # HIDP_STATUS_SUCCESS
                        return None
                    
                    # Check if this device has battery usage page
                    if caps.UsagePage == HID_USAGE_PAGE_BATTERY_SYSTEM:
                        # Try to read battery report
                        report_buffer = ctypes.create_string_buffer(caps.FeatureReportByteLength)
                        report_buffer[0] = 0  # Report ID
                        
                        if self.hid.HidD_GetFeature(device_handle, report_buffer, caps.FeatureReportByteLength):
                            # Parse battery report - typically battery percentage is in the second byte
                            if len(report_buffer) >= 2:
                                battery_level = ord(report_buffer[1])
                                if 0 <= battery_level <= 100:
                                    if DEBUG:
                                        logging.debug(f"HID battery report: {[ord(b) for b in report_buffer[:8]]}")
                                    return battery_level
                
                finally:
                    self.hid.HidD_FreePreparsedData(preparsed_data)
                    
            finally:
                self.kernel32.CloseHandle(device_handle)
            
            return None
            
        except Exception as e:
            if DEBUG:
                logging.debug(f"Error reading HID battery from {device_path}: {e}")
            return None
    
    def _refresh_device_properties(self, dev_node):
        """Refresh device properties to get the latest battery information."""
        try:
            # Use CM_Reenumerate_DevNode to refresh device properties
            result = self.cfgmgr32.CM_Reenumerate_DevNode(dev_node, 0)
            if DEBUG and result != CR_SUCCESS:
                logging.debug(f"Device property refresh result: {result}")
        except Exception as e:
            if DEBUG:
                logging.debug(f"Error refreshing device properties: {e}")


def get_bluetooth_api():
    """Get Bluetooth API with fallbacks since the DLL may not be in the same location on all systems."""
    possible_paths = [
        "BluetoothAPIs.dll",
        os.path.join(os.environ["SystemRoot"], "System32", "BluetoothAPIs.dll"),
        os.path.join(os.environ["SystemRoot"], "SysWOW64", "BluetoothAPIs.dll"),  # For 32-bit Python on 64-bit Windows
    ]

    for path in possible_paths:
        try:
            return ctypes.WinDLL(path)
        except (WindowsError, OSError) as e:
            last_error = e
            continue

    raise RuntimeError(f"Failed to load BluetoothAPIs.dll. Error: {last_error}")


# Define SYSTEMTIME structure
class SYSTEMTIME(ctypes.Structure):
    _fields_ = [
        ("wYear", wintypes.WORD),
        ("wMonth", wintypes.WORD),
        ("wDayOfWeek", wintypes.WORD),
        ("wDay", wintypes.WORD),
        ("wHour", wintypes.WORD),
        ("wMinute", wintypes.WORD),
        ("wSecond", wintypes.WORD),
        ("wMilliseconds", wintypes.WORD),
    ]


# Define BLUETOOTH_DEVICE_INFO structure
class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("Address", ctypes.c_ulonglong),
        ("ulClassofDevice", wintypes.ULONG),
        ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL),
        ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", SYSTEMTIME),
        ("stLastUsed", SYSTEMTIME),
        ("szName", ctypes.c_wchar * 248),
    ]


# Define BLUETOOTH_DEVICE_SEARCH_PARAMS structure
class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL),
        ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL),
        ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", wintypes.HANDLE),
    ]


# Define BLUETOOTH_FIND_RADIO_PARAMS structure
class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
    ]


class BluetoothThread(QThread):
    status_signal = pyqtSignal(object)  # Changed to object to pass device data

    def __init__(self, bt_api):
        super().__init__()
        self.bt_api = bt_api
        # Initialize Windows device property reader for battery info
        try:
            self.device_property_reader = WindowsDevicePropertyReader()
        except Exception as e:
            if DEBUG:
                logging.warning(f"Windows device property reader not available: {e}")
            self.device_property_reader = None

    def run(self):
        bluetooth_data = self.get_bluetooth_data()
        self.status_signal.emit(bluetooth_data)

    def is_bluetooth_enabled(self):
        find_radio_params = BLUETOOTH_FIND_RADIO_PARAMS(dwSize=ctypes.sizeof(BLUETOOTH_FIND_RADIO_PARAMS))
        radio_handle = wintypes.HANDLE()
        find_first_radio = self.bt_api.BluetoothFindFirstRadio
        find_first_radio.argtypes = [
            ctypes.POINTER(BLUETOOTH_FIND_RADIO_PARAMS),
            ctypes.POINTER(wintypes.HANDLE),
        ]
        find_first_radio.restype = wintypes.HANDLE  # Correct restype for a handle
        radio_finder = find_first_radio(ctypes.byref(find_radio_params), ctypes.byref(radio_handle))
        if radio_finder and radio_finder != wintypes.HANDLE(0):
            # Define argtypes and restype for BluetoothFindRadioClose
            self.bt_api.BluetoothFindRadioClose.argtypes = [wintypes.HANDLE]
            self.bt_api.BluetoothFindRadioClose.restype = wintypes.BOOL
            self.bt_api.BluetoothFindRadioClose.argtypes = [wintypes.HANDLE]
            self.bt_api.BluetoothFindRadioClose.restype = wintypes.BOOL
            self.bt_api.BluetoothFindRadioClose(radio_finder)
            ctypes.windll.kernel32.CloseHandle(radio_handle)
            return True
        return False

    async def get_battery_level_async(self, device_address):
        """Get battery level for a Bluetooth device using WinRT APIs."""
        if not WINRT_AVAILABLE:
            return None
        
        try:
            # Format address for WinRT (convert MAC address)
            formatted_address = device_address.replace(":", "").lower()
            device_selector = f"System.DeviceInterface.Bluetooth.DeviceInstanceId:\"BTHENUM\\\\DEV_{formatted_address}\""
            
            # Find the device using Bluetooth device selector
            device_info_collection = await DeviceInformation.find_all_async(
                BluetoothDevice.get_device_selector()
            )
            
            bluetooth_device = None
            for device_info in device_info_collection:
                try:
                    temp_device = await BluetoothDevice.from_id_async(device_info.id)
                    if temp_device and temp_device.bluetooth_address:
                        device_addr = f"{temp_device.bluetooth_address:012X}"
                        device_addr_formatted = ":".join([device_addr[i:i+2] for i in range(0, 12, 2)]).upper()
                        if device_addr_formatted == device_address.upper():
                            bluetooth_device = temp_device
                            break
                except:
                    continue
            
            if not bluetooth_device:
                return None
            
            # Get GATT services for Battery Service UUID
            from winrt.windows.devices.bluetooth.genericattributeprofile import GattDeviceService
            battery_service_uuid = uuid.UUID("0000180f-0000-1000-8000-00805f9b34fb")
            
            gatt_result = await bluetooth_device.get_gatt_services_for_uuid_async(
                battery_service_uuid
            )
            
            if not gatt_result or not gatt_result.services or gatt_result.services.size == 0:
                return None
            
            battery_service = gatt_result.services.get_at(0)
            
            # Get Battery Level characteristic (0x2A19)
            battery_level_uuid = uuid.UUID("00002a19-0000-1000-8000-00805f9b34fb")
            char_result = await battery_service.get_characteristics_for_uuid_async(
                battery_level_uuid
            )
            
            if not char_result or not char_result.characteristics or char_result.characteristics.size == 0:
                return None
            
            battery_characteristic = char_result.characteristics.get_at(0)
            
            # Read battery level
            read_result = await battery_characteristic.read_value_async()
            if read_result and read_result.status == 0:  # GattCommunicationStatus.Success
                reader = DataReader.from_buffer(read_result.value)
                if reader.unconsumed_buffer_length > 0:
                    battery_level = reader.read_byte()
                    return battery_level
            
        except Exception as e:
            if DEBUG:
                logging.debug(f"Failed to get battery level for {device_address}: {e}")
            return None
        
        return None

    def get_battery_level(self, device_address):
        """Get battery level for a Bluetooth device using Windows device properties."""
        if not self.device_property_reader:
            if DEBUG:
                logging.debug(f"Device property reader not available for {device_address}")
            return None
        
        try:
            battery_level = self.device_property_reader.get_device_battery_level(device_address)
            if battery_level is not None:
                if DEBUG:
                    logging.info(f"Found battery level {battery_level}% for device {device_address}")
                return battery_level
            else:
                if DEBUG:
                    logging.debug(f"No battery info available for device {device_address}")
                return None
        except Exception as e:
            if DEBUG:
                logging.error(f"Error getting battery level for {device_address}: {e}")
            return None

    def get_bluetooth_devices(self):
        devices = []
        find_radio_params = BLUETOOTH_FIND_RADIO_PARAMS(dwSize=ctypes.sizeof(BLUETOOTH_FIND_RADIO_PARAMS))
        radio_handle = wintypes.HANDLE()
        find_first_radio = self.bt_api.BluetoothFindFirstRadio
        find_first_radio.argtypes = [
            ctypes.POINTER(BLUETOOTH_FIND_RADIO_PARAMS),
            ctypes.POINTER(wintypes.HANDLE),
        ]
        find_first_radio.restype = wintypes.HANDLE
        radio_finder = find_first_radio(ctypes.byref(find_radio_params), ctypes.byref(radio_handle))
        if not radio_finder or radio_finder == wintypes.HANDLE(0):
            return devices
        try:
            while True:
                device_search_params = BLUETOOTH_DEVICE_SEARCH_PARAMS(
                    dwSize=ctypes.sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS),
                    fReturnAuthenticated=True,
                    fReturnRemembered=True,
                    fReturnUnknown=False,
                    fReturnConnected=True,
                    fIssueInquiry=False,
                    cTimeoutMultiplier=1,
                    hRadio=radio_handle,
                )
                device_info = BLUETOOTH_DEVICE_INFO()
                device_info.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_INFO)
                find_first_device = self.bt_api.BluetoothFindFirstDevice
                find_first_device.argtypes = [
                    ctypes.POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS),
                    ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
                ]
                find_first_device.restype = wintypes.HANDLE
                device_finder = find_first_device(ctypes.byref(device_search_params), ctypes.byref(device_info))
                if not device_finder or device_finder == wintypes.HANDLE(0):
                    break
                try:
                    while True:
                        address = ":".join(["%02X" % ((device_info.Address >> (8 * i)) & 0xFF) for i in range(6)][::-1])
                        
                        # Get battery level for connected devices
                        battery_level = None
                        if bool(device_info.fConnected):
                            battery_level = self.get_battery_level(address)
                        
                        devices.append(
                            {
                                "name": device_info.szName,
                                "address": address,
                                "connected": bool(device_info.fConnected),
                                "authenticated": bool(device_info.fAuthenticated),
                                "battery_level": battery_level,
                            }
                        )
                        next_device = self.bt_api.BluetoothFindNextDevice
                        next_device.argtypes = [
                            wintypes.HANDLE,
                            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
                        ]
                        next_device.restype = wintypes.BOOL
                        if not next_device(device_finder, ctypes.byref(device_info)):
                            break
                finally:
                    self.bt_api.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
                    self.bt_api.BluetoothFindDeviceClose.restype = wintypes.BOOL
                    self.bt_api.BluetoothFindDeviceClose(device_finder)
                # Move to the next radio (if any)
                next_radio = self.bt_api.BluetoothFindNextRadio
                next_radio.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(wintypes.HANDLE),
                ]
                next_radio.restype = wintypes.BOOL
                if not next_radio(radio_finder, ctypes.byref(radio_handle)):
                    break
        finally:
            self.bt_api.BluetoothFindRadioClose(radio_finder)
            ctypes.windll.kernel32.CloseHandle(radio_handle)
        return devices

    def get_bluetooth_data(self):
        """Return bluetooth data with device information and battery levels."""
        if self.is_bluetooth_enabled():
            devices = self.get_bluetooth_devices()
            connected_devices = [
                device
                for device in devices
                if device["connected"] and device["authenticated"]
            ]
            
            if connected_devices:
                return {
                    "enabled": True,
                    "status": "connected",
                    "devices": connected_devices
                }
            else:
                return {
                    "enabled": True,
                    "status": "no_devices",
                    "devices": []
                }
        else:
            return {
                "enabled": False,
                "status": "disabled",
                "devices": []
            }

    def get_bluetooth_status(self):
        if self.is_bluetooth_enabled():
            devices = self.get_bluetooth_devices()
            if devices:
                # Only show devices that are both connected AND authenticated (paired)
                connected_devices = [
                    device
                    for device in devices
                    if device["connected"] and device["authenticated"]  # Add authenticated check
                ]
                if connected_devices:
                    return f"Connected to: {connected_devices}"
            return "Bluetooth is on, but no paired devices connected."
        return "Bluetooth is disabled."


class BluetoothWidget(BaseWidget):
    validation_schema = VALIDATION_SCHEMA

    def __init__(
        self,
        label: str,
        label_alt: str,
        class_name: str,
        label_no_device: str,
        label_device_separator: str,
        max_length: int,
        max_length_ellipsis: str,
        tooltip: bool,
        icons: dict[str, str],
        device_aliases: list[dict[str, str]],
        animation: dict[str, str],
        container_padding: dict[str, int],
        callbacks: dict[str, str],
        show_battery: bool = True,
        battery_format: str = " ({battery}%)",
        battery_threshold_low: int = 20,
        battery_threshold_critical: int = 10,
        label_shadow: dict = None,
        container_shadow: dict = None,
    ):
        super().__init__(class_name=f"bluetooth-widget {class_name}")
        self._show_alt_label = False
        self._label_content = label
        self._label_alt_content = label_alt
        self._label_no_device = label_no_device
        self._label_devices_separator = label_device_separator
        self._max_length = max_length
        self._max_length_ellipsis = max_length_ellipsis
        self._device_aliases = device_aliases
        self._tooltip = tooltip
        self._padding = container_padding
        self._label_shadow = label_shadow
        self._container_shadow = container_shadow
        self._show_battery = show_battery
        self._battery_format = battery_format
        self._battery_threshold_low = battery_threshold_low
        self._battery_threshold_critical = battery_threshold_critical
        try:
            self.bt_api = get_bluetooth_api()
        except RuntimeError as e:
            if DEBUG:
                logging.error(f"Bluetooth support unavailable: {e}")
            self.bt_api = None
        self.current_status = None
        self._icons = icons
        self._animation = animation
        self.bluetooth_icon = None
        self.connected_devices = None

        self._widget_container_layout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(
            self._padding["left"], self._padding["top"], self._padding["right"], self._padding["bottom"]
        )
        self._widget_container = QFrame()
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "widget-container")
        add_shadow(self._widget_container, self._container_shadow)
        self.widget_layout.addWidget(self._widget_container)

        build_widget_label(self, self._label_content, self._label_alt_content, self._label_shadow)

        self.register_callback("toggle_label", self._toggle_label)

        self.callback_left = callbacks["on_left"]
        self.callback_right = callbacks["on_right"]
        self.callback_middle = callbacks["on_middle"]

        self.current_status = None  # Store the current Bluetooth status
        self.bluetooth_thread = BluetoothThread(self.bt_api)
        self.bluetooth_thread.status_signal.connect(self._update_state)

        # Setup QTimer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_bluetooth_thread)
        self.timer.start(3000)

        self.start_bluetooth_thread()
        self._update_label(self._icons["bluetooth_off"])

    def start_bluetooth_thread(self):
        if not self.bluetooth_thread.isRunning():
            self.bluetooth_thread = BluetoothThread(self.bt_api)
            self.bluetooth_thread.status_signal.connect(self._update_state)
            self.bluetooth_thread.start()

    def stop(self):
        self.timer.stop()
        if self.bluetooth_thread.isRunning():
            self.bluetooth_thread.terminate()
            self.bluetooth_thread.wait()

    def _toggle_label(self):
        if self._animation["enabled"]:
            AnimationManager.animate(self, self._animation["type"], self._animation["duration"])
        self._show_alt_label = not self._show_alt_label
        for widget in self._widgets:
            widget.setVisible(not self._show_alt_label)
        for widget in self._widgets_alt:
            widget.setVisible(self._show_alt_label)
        self._update_label(self.bluetooth_icon, self.connected_devices)

    def _update_label(self, icon, connected_devices=None):
        active_widgets = self._widgets_alt if self._show_alt_label else self._widgets
        active_label_content = self._label_alt_content if self._show_alt_label else self._label_content
        label_parts = re.split("(<span.*?>.*?</span>)", active_label_content)
        label_parts = [part for part in label_parts if part]
        widget_index = 0

        if connected_devices:
            device_names_list = []
            tooltip_lines = ["Connected devices"]
            
            for device in connected_devices:
                device_name = device["name"]
                
                # Apply device aliases
                if self._device_aliases:
                    device_name = next(
                        (alias["alias"] for alias in self._device_aliases if alias["name"].strip() == device["name"].strip()),
                        device_name,
                    )
                
                # Add battery information if available and enabled
                if self._show_battery and device.get("battery_level") is not None:
                    battery_text = self._battery_format.format(battery=device["battery_level"])
                    device_display_name = device_name + battery_text
                else:
                    device_display_name = device_name
                
                device_names_list.append(device_display_name)
                
                # Build tooltip info
                if device.get("battery_level") is not None:
                    tooltip_lines.append(f"• {device_name} ({device['battery_level']}%)")
                else:
                    tooltip_lines.append(f"• {device_name}")
            
            device_names = self._label_devices_separator.join(device_names_list)
            tooltip_text = "\n".join(tooltip_lines) if device_names_list else "No devices connected"
        else:
            device_names = self._label_no_device
            tooltip_text = self._label_no_device

        # Get battery info for the {battery} placeholder
        battery_info = ""
        if connected_devices:
            # Find the first device with battery info
            for device in connected_devices:
                if device.get("battery_level") is not None:
                    battery_info = f"{device['battery_level']}%"
                    break
            # If no device has battery, show the first device name
            if not battery_info and connected_devices:
                battery_info = connected_devices[0]["name"]

        label_options = {
            "{icon}": icon,
            "{device_name}": device_names,
            "{device_count}": len(connected_devices) if connected_devices else 0,
            "{battery}": battery_info,
        }

        for part in label_parts:
            part = part.strip()
            if part:
                formatted_text = part
                for option, value in label_options.items():
                    formatted_text = formatted_text.replace(option, str(value))
                if "<span" in part and "</span>" in part:
                    if widget_index < len(active_widgets) and isinstance(active_widgets[widget_index], QLabel):
                        active_widgets[widget_index].setText(formatted_text)
                else:
                    if self._max_length and len(formatted_text) > self._max_length:
                        formatted_text = formatted_text[: self._max_length] + self._max_length_ellipsis
                    if widget_index < len(active_widgets) and isinstance(active_widgets[widget_index], QLabel):
                        active_widgets[widget_index].setText(formatted_text)
                widget_index += 1

        if self._tooltip:
            set_tooltip(self._widget_container, tooltip_text)

    def _update_state(self, bluetooth_data):
        self.current_bluetooth_data = bluetooth_data
        
        if DEBUG and bluetooth_data["status"] != "disabled":
            logging.info(f"Bluetooth: {bluetooth_data}")

        if not bluetooth_data["enabled"]:
            bluetooth_icon = self._icons["bluetooth_off"]
            connected_devices = []
        elif bluetooth_data["status"] == "connected":
            bluetooth_icon = self._icons["bluetooth_connected"]
            connected_devices = bluetooth_data["devices"]
        else:
            bluetooth_icon = self._icons["bluetooth_on"]
            connected_devices = []
        
        self.bluetooth_icon = bluetooth_icon
        self.connected_devices = connected_devices
        self._update_label(bluetooth_icon, connected_devices)
