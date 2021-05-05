#  This module belongs to the usbsecurity-monitor project.
#  Copyright (c) 2021 Alexis Torres Valdes
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2.1 of the License, or (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#   License along with this library; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
#   USA
#
#   Contact: alexis89.dev@gmail.com

import os
import logging
import sys
from subprocess import call

import win32api
import win32con
import win32gui
from typing import Callable, List
from threading import Thread

from psutil import disk_partitions
from re import match
from winreg import HKEY_LOCAL_MACHINE

from usbsecurity_monitor.registry import all_keys_values

logging.basicConfig(filename='usbsecurity-monitor.log',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Device:
    def __init__(self, device_id, vid, pid, hex_id):
        self._device_id = device_id
        self._vid = vid
        self._pid = pid
        self._hex_id = hex_id

    @property
    def device_id(self):
        return self._device_id

    @property
    def vid(self):
        return self._vid

    @property
    def pid(self):
        return self._pid

    @property
    def hex_id(self):
        return self._hex_id

    def __str__(self):
        return self.device_id

    def __lt__(self, other):
        return self.device_id.__lt__(other.device_id)

    def __gt__(self, other):
        return self.device_id.__gt__(other.device_id)

    def __le__(self, other):
        return self.device_id.__le__(other.device_id)

    def __ge__(self, other):
        return self.device_id.__ge__(other.device_id)

    def __eq__(self, other):
        return self.device_id == other.device_id

    def __ne__(self, other):
        return self.device_id != other.device_id


class DeviceListener:
    """
        Listens to Win32 `WM_DEVICECHANGE` messages
        and trigger a callback when a device has been plugged in or out

        See: https://docs.microsoft.com/en-us/windows/win32/devio/wm-devicechange
        """
    WM_DEVICECHANGE_EVENTS = {
        0x0019: ('DBT_CONFIGCHANGECANCELED',
                 'A request to change the current configuration (dock or undock) has been canceled.'),
        0x0018: ('DBT_CONFIGCHANGED', 'The current configuration has changed, due to a dock or undock.'),
        0x8006: ('DBT_CUSTOMEVENT', 'A custom event has occurred.'),
        0x8000: ('DBT_DEVICEARRIVAL', 'A device or piece of media has been inserted and is now available.'),
        0x8001: ('DBT_DEVICEQUERYREMOVE',
                 'Permission is requested to remove a device or piece of media. Any application can deny this request and cancel the removal.'),
        0x8002: ('DBT_DEVICEQUERYREMOVEFAILED', 'A request to remove a device or piece of media has been canceled.'),
        0x8004: ('DBT_DEVICEREMOVECOMPLETE', 'A device or piece of media has been removed.'),
        0x8003: ('DBT_DEVICEREMOVEPENDING', 'A device or piece of media is about to be removed. Cannot be denied.'),
        0x8005: ('DBT_DEVICETYPESPECIFIC', 'A device-specific event has occurred.'),
        0x0007: ('DBT_DEVNODES_CHANGED', 'A device has been added to or removed from the system.'),
        0x0017: (
            'DBT_QUERYCHANGECONFIG', 'Permission is requested to change the current configuration (dock or undock).'),
        0xFFFF: ('DBT_USERDEFINED', 'The meaning of this message is user-defined.'),
    }

    @staticmethod
    def unbind(device: Device):
        is_64bits = 2 ** 32 < sys.maxsize
        if not is_64bits:
            rd_app = os.path.join(BASE_DIR, 'RemoveDrive.exe')
        else:
            rd_app = os.path.join(BASE_DIR, 'RemoveDrive-x64.exe')
        cmd = '{rd_app} "{device_id}" -L -dbg'.format(rd_app=rd_app, device_id=device.device_id)
        rc = call(cmd, shell=True)

        if rc != 0:
            logger.info('Could not disable the device %s' % device.device_id)
        else:
            logger.info('Unlinked device %s' % device.device_id)

    @staticmethod
    def bind(device: Device):
        is_64bits = 2 ** 32 < sys.maxsize
        if not is_64bits:
            rd_app = os.path.join(BASE_DIR, 'RestartSrDev.exe')
        else:
            rd_app = os.path.join(BASE_DIR, 'RestartSrDev-x64.exe')
        cmd = '{rd_app} "{device_id}"'.format(rd_app=rd_app, device_id=device.device_id)
        rc = call(cmd, shell=True)

        if rc != 0:
            logger.info('Could not disable the device %s' % device.device_id)
        else:
            logger.info('Linked device %s' % device.device_id)

    @staticmethod
    def list_devices() -> List[Device]:
        devices = []

        _all_keys_values = all_keys_values(HKEY_LOCAL_MACHINE, 'SYSTEM\\CurrentControlSet\\services\\USBSTOR\\Enum')
        for k in _all_keys_values.keys():
            value = _all_keys_values[k]
            if isinstance(value, str):
                _match = match(
                    r'USB\\VID_(?P<vid>[0-9A-F]{4})&PID_(?P<pid>[0-9A-F]{4})\\(?P<hex_id>[0-9A-F]{8})',
                    value)
                if _match:
                    _dict = _match.groupdict()
                    device = Device(device_id=value, vid=_dict['vid'], pid=_dict['pid'],
                                    hex_id=_dict['hex_id'])
                    devices.append(device)

        return devices

    def __init__(self, on_add: Callable[[Device], None], on_remove: Callable[[Device], None]):
        self.on_add = on_add
        self.on_remove = on_remove
        self._disk_partitions = disk_partitions(all=True)

    def _create_window(self):
        """
        Create a window for listening to messages
        https://docs.microsoft.com/en-us/windows/win32/learnwin32/creating-a-window#creating-the-window

        See also: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createwindoww

        :return: window hwnd
        """
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._on_message
        wc.lpszClassName = self.__class__.__name__
        wc.hInstance = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(class_atom, self.__class__.__name__, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)

    def start(self):
        logger.info('Listening to drive changes')
        hwnd = self._create_window()
        win32gui.PumpMessages()

    def _on_message(self, hwnd: int, msg: int, wparam: int, lparam: int):
        if msg != win32con.WM_DEVICECHANGE:
            return 0
        event, description = self.WM_DEVICECHANGE_EVENTS[wparam]
        if event == 'DBT_DEVICEARRIVAL':
            device = self._get_device_changed()
            if device:
                Thread(target=self.on_add, args=[device]).start()
        elif event == 'DBT_DEVICEREMOVECOMPLETE':
            device = self._get_device_changed()
            if device:
                Thread(target=self.on_remove, args=[device]).start()

        return 0

    def _get_device_changed(self):
        _disk_partitions = disk_partitions(all=True)

        disk_part = None
        if len(self._disk_partitions) < len(_disk_partitions):
            # Se ha insertado un dispositivo
            diff = set(_disk_partitions) - set(self._disk_partitions)
            if len(diff) == 1:
                disk_part = list(diff)[0]
            self._disk_partitions = _disk_partitions
        elif len(_disk_partitions) < len(self._disk_partitions):
            # Se ha quitado un dispositivo
            diff = set(self._disk_partitions) - set(_disk_partitions)
            if len(diff) == 1:
                disk_part = list(diff)[0]
            self._disk_partitions = _disk_partitions

        if disk_part:
            hex_devices = {}
            for dev in self.list_devices():
                hex_devices[dev.hex_id] = dev

            _all_keys_values = all_keys_values(HKEY_LOCAL_MACHINE, 'SYSTEM\\MountedDevices')
            for k in _all_keys_values.keys():
                pattern_vol = r'\\DosDevices\\(?P<mount_point>[A-Z]:)'
                _match = match(pattern_vol, k)
                if _match:
                    mount_point = '%s\\' % _match.groupdict()['mount_point']
                    value = _all_keys_values[k]
                    if mount_point == disk_part.mountpoint and isinstance(value, str):
                        value_s = value.split('#')
                        if 3 < len(value_s):
                            hex_id = value_s[2].split('&')[0]
                            return hex_devices.get(hex_id)

        return None
