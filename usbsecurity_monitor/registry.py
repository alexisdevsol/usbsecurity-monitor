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
