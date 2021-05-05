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

from winreg import OpenKey, QueryValueEx, CloseKey, EnumValue, KEY_READ


def get_value(key, sub_key, name):
    try:
        registry_key = OpenKey(key, sub_key, 0, KEY_READ)
        value, regtype = QueryValueEx(registry_key, name)
        CloseKey(registry_key)
        return value[::2][:value[::2].find(b'\x00')].decode() if regtype == 3 else value
    except UnicodeDecodeError:
        return None
    except WindowsError:
        return None


def all_keys_values(key, sub_key):
    _dict = {}

    registry_key = OpenKey(key, sub_key, 0, KEY_READ)

    i = 0
    while True:
        try:
            name, value, regtype = EnumValue(registry_key, i)
            _dict[name] = value[::2][:value[::2].find(b'\x00')].decode() if regtype == 3 else value
        except UnicodeDecodeError:
            pass
        except WindowsError:
            CloseKey(registry_key)
            break
        i += 1

    return _dict
