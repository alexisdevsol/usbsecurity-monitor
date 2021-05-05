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

import logging
import re
from subprocess import check_output, call
from typing import Callable

from pyudev import Context, Monitor
from pyudev import Device as PydevDevice

from usbsecurity_monitor.constants import ACTION_ADD, ACTION_REMOVE

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


class Device:
    def __init__(self, bus_port, device_node, driver, bus, device, device_id, tag, vid, pid):
        self._bus_port = bus_port
        self._device_node = device_node
        self._driver = driver
        self._bus = bus
        self._device = device
        self._device_id = device_id
        self._vid = vid
        self._pid = pid
        self._tag = tag

    def __str__(self):
        return self.device_id

    @property
    def bus_port(self):
        return self._bus_port

    @property
    def device_node(self):
        return self._device_node

    @property
    def driver(self):
        return self._driver

    @property
    def bus(self):
        return self._bus

    @property
    def device(self):
        return self._device

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
    def tag(self):
        return self._tag


class DeviceListener:
    @staticmethod
    def unbind(device: Device):
        cmd = "echo '{bus_port}' | sudo tee /sys/bus/usb/drivers/usb/unbind".format(bus_port=device.bus_port)
        rc = call(cmd, shell=True)
        if rc != 0:
            logger.info('Could not disable the device %s' % device)
        else:
            logger.info('Unbind device %s' % device)

    @staticmethod
    def bind(device: Device):
        cmd = "echo '{bus_port}' | sudo tee /sys/bus/usb/drivers/usb/bind".format(bus_port=device.bus_port)
        rc = call(cmd, shell=True)
        if rc != 0:
            logger.info('Could not enable the device %s' % device)
        else:
            logger.info('Bind device %s' % device)

    def __init__(self, on_add: Callable[[Device], None], on_remove: Callable[[Device], None]):
        self.on_add = on_add
        self.on_remove = on_remove
        self.context = Context()
        self.monitor = Monitor.from_netlink(self.context)

    def start(self):
        self.monitor.filter_by(subsystem='usb')
        self.monitor.start()
        logger.info(f'Listening to drive changes')
        for device in iter(self.monitor.poll, None):
            if device.device_node:
                if device.action == ACTION_ADD:
                    self.on_add(self._device(device))
                elif device.action == ACTION_REMOVE:
                    self.on_remove(self._device(device))

    def stop(self):
        self.monitor.stop()
        logger.info('Stopped monitor.')

    @staticmethod
    def _device_info(bus, device):
        device_re = re.compile('Bus\s+(?P<bus>\d+)\s+Device\s+(?P<device>\d+).+ID\s(?P<id>\w+:\w+)\s(?P<tag>.+)$', re.I)
        df = check_output('lsusb')

        for i in df.decode().split('\n'):
            if i:
                info = device_re.match(i)
                if info:
                    dinfo = info.groupdict()
                    _bus = dinfo.pop('bus')
                    _device = dinfo.pop('device')
                    if _bus != bus or _device != device:
                        continue
                    dinfo['device'] = '/dev/bus/usb/%s/%s' % (_bus, _device)
                    return dinfo
        return None

    @staticmethod
    def _device(device: PydevDevice) -> Device:
        _bus_port = device.sys_name.split(':')[0]
        _device_node = None
        _driver = None
        _bus = None
        _device = None
        _device_id = None
        _vid = None
        _pid = None
        _tag = None

        if device.device_node:
            _device_node = device.device_node
            device_node_s = device.device_node.split('/')
            _device = device_node_s[-1]
            _bus = device_node_s[-2]
            lsusb_result = DeviceListener._device_info(_bus, _device)
            if lsusb_result:
                _device_id = lsusb_result['id']
                _device_id_s = _device_id.split(':')
                _vid = _device_id_s[0]
                _pid = _device_id_s[1]
                _tag = lsusb_result['tag']

        return Device(bus_port=_bus_port,
                      device_node=_device_node,
                      driver=_driver,
                      bus=_bus,
                      device=_device,
                      device_id=_device_id,
                      vid=_vid,
                      pid=_pid,
                      tag=_tag)
