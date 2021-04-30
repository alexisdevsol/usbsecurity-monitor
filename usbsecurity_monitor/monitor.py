#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import argparse
import logging
import platform
import sys
import textwrap
import re
from urllib.parse import urljoin

import webview
from json import loads as json_loads
from re import match

from requests import HTTPError, ConnectionError
from requests import get as requests_get
from sortedcontainers import SortedSet
from subprocess import call, check_output, CalledProcessError

from usbsecurity_monitor.constants import ACTION_REMOVE, ACTION_ADD, DEVICE_REMOVED
from usbsecurity_monitor.exceptions import UnsupportedPlatform, UndefinedError, AuthorizeError, BadResponse

if platform.system() == 'Linux':
    from usbsecurity_monitor.linux import DeviceListener, Device
elif platform.system() == 'Windows':
    from usbsecurity_monitor.win32 import DeviceListener, Device
else:
    sys.exit('Unsupported platform. Only Linux and Windows are supported.')


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

about = {}
with open(os.path.join(BASE_DIR, '__version__.py')) as f:
    exec(f.read(), about)


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


def has_cef():
    if platform.system() == 'Linux':
        try:
            output = check_output('chromium-browser --version', shell=True)
            _match = match('Chromium (?P<version>\d+).\d+.\d+.\d+ .*', output.decode())
            if _match:
                return 66 < int(_match.groupdict()['version'])
        except CalledProcessError:
            pass

        try:
            output = check_output('google-chrome --version', shell=True)
            _match = match('Google Chrome (?P<version>\d+).\d+.\d+.\d+ .*', output.decode())
            if _match:
                return 66 < int(_match.groupdict()['version'])
        except CalledProcessError:
            pass

    if platform.system() == 'Windows':
        try:
            output = check_output('dir /B/AD "C:\Program Files (x86)\Google\Chrome\Application\"|findstr /R /C:"^[0-9].*\..*[0-9]$"', shell=True)
            _match = match('(?P<version>\d+).\d+.\d+.\d+', output.decode())
            if _match:
                return 66 < int(_match.groupdict()['version'])
        except CalledProcessError:
            pass

        try:
            output = check_output('dir /B/AD "C:\Program Files\Google\Chrome\Application\"|findstr /R /C:"^[0-9].*\..*[0-9]$"', shell=True)
            _match = match('(?P<version>\d+).\d+.\d+.\d+', output.decode())
            if _match:
                return 66 < int(_match.groupdict()['version'])
        except CalledProcessError:
            pass

        try:
            output = check_output(
                'dir /B/AD "C:\Program Files (x86)\Google\Chromium\Application\"|findstr /R /C:"^[0-9].*\..*[0-9]$"',
                shell=True)
            _match = match('(?P<version>\d+).\d+.\d+.\d+', output.decode())
            if _match:
                return 66 < int(_match.groupdict()['version'])
        except CalledProcessError:
            pass

        try:
            output = check_output(
                'dir /B/AD "C:\Program Files\Google\Chromium\Application\"|findstr /R /C:"^[0-9].*\..*[0-9]$"',
                shell=True)
            _match = match('(?P<version>\d+).\d+.\d+.\d+', output.decode())
            if _match:
                return 66 < int(_match.groupdict()['version'])
        except CalledProcessError:
            pass

    return False


def open_gui():
    if platform.system() == 'Linux':
        username = os.getlogin()
        cmd = 'cp -a /home/%s/.Xauthority /root/.Xauthority' % username
        rc = call(cmd, shell=True)
        if rc != 0:
            logger.error('Error when executing the command "%s"' % cmd)
            return False

        cmd = 'chown root: /root/.Xauthority'
        rc = call(cmd, shell=True)
        if rc != 0:
            logger.error('Error when executing the command "%s"' % cmd)
            return False

        cmd = 'XAUTHORITY=/root/.Xauthority'
        rc = call(cmd, shell=True)
        if rc != 0:
            logger.error('Error when executing the command "%s"' % cmd)
            return False

    window = webview.create_window('USBSecurity', urljoin('http://%s:%s' % (host, port), 'account'),
                                   width=1024, height=600)
    window.loaded += on_loaded

    if has_cef():
        try:
            webview.start(gui='cef')
            return True
        except Exception as e:
            logger.warning(e)
    webview.start()

    return True


def permissions(action, device: Device=None):
    if not url_api:
        raise UndefinedError('URL of api not defined')

    if not device:
        device_id = DEVICE_REMOVED
    else:
        device_id = '%s:%s' % (device.vid, device.pid)

    resp = requests_get(url_api.replace('{action}', action).replace('{id}', device_id))
    if not resp.ok:
        raise HTTPError('HTTPError. Response status code %s' % resp.status_code)

    data = json_loads(resp.content.decode())
    error = data.get('error')
    if error:
        raise AuthorizeError(error)

    is_authorized = data.get('is_authorized', None)
    if is_authorized is None or not isinstance(is_authorized, bool):
        raise BadResponse('The boolean field "is_authenticated" is expected in the JSON response.')

    return data


def on_added(device: Device):
    logger.info('Add device %s' % device.device_id)

    if len(black_list) and device.device_id not in black_list:
        logger.info('Device %s is not on the blacklist' % device.device_id)
        return

    if len(white_list) and device.device_id in white_list:
        logger.info('Device %s is whitelisted' % device.device_id)
        return

    try:
        if url_api:
            _permissions = permissions(ACTION_ADD, device)
            if _permissions.get('is_authorized', False):
                logger.info('The device with ID %s has been authorized' % device.device_id)
                return
            logger.info('The device with ID %s has not been authorized.' % device.device_id)
    except AuthorizeError as e:
        logger.error(e)
        DeviceListener.unbind(device)
        if open_gui():
            _permissions = permissions(ACTION_ADD, device)
            if _permissions.get('is_authorized', False):
                logger.info('The device with ID %s has been authorized' % device.device_id)
                DeviceListener.bind(device)
                return
            logger.info('The device with ID %s has not been authorized.' % device.device_id)
    except (ConnectionError,
            HTTPError,
            UndefinedError,
            BadResponse) as e:
        logger.error(e)

    DeviceListener.unbind(device)


def on_removed(device: Device):
    logger.info('Remove device')

    if url_api:
        try:
            _permissions = permissions(ACTION_REMOVE)
            if not _permissions.get('is_authorized', False):
                logger.info('Unauthorized device')
        except (ConnectionError,
                HTTPError,
                UndefinedError,
                AuthorizeError,
                BadResponse) as err:
            logger.error(err)
            return


def on_loaded():
    url_account = urljoin('http://%s:%s' % (host, port), 'account/')
    if webview.windows[0].get_current_url() == url_account:
        webview.windows[0].destroy()


def read_devices(filename):
    with open(filename) as f:
        uncomment_lines = filter(lambda ln: not ln.startswith('#'), f.readlines())
        lines = map(lambda ln: ln.rstrip('\n'), uncomment_lines)
        devices = filter(lambda ln: re.match('[a-fA-F0-9]{4}:[a-fA-F0-9]{4}$', ln) is not None, lines)
        return devices


def parse_args():
    __version__ = about['__version__']

    parser = argparse.ArgumentParser(prog='usbsecurity-monitor',
                                     description='usbsecurity-monitor is the program to control USB ports.')

    parser.add_argument('-v',
                        '--version',
                        action='version',
                        version=f'%(prog)s {__version__}')
    parser.add_argument('-a',
                        '--author',
                        action='version',
                        version='%(prog)s was created by software developer Alexis Torres Valdes <alexis89.dev@gmail.com>',
                        help="show program's author and exit")

    parser.add_argument('--host',
                        default='127.0.0.1',
                        help='Host where usbsecurity-server runs. Default: 127.0.0.1')
    parser.add_argument('--port',
                        type=int,
                        default=8888,
                        help='Port where usbsecurity-server runs. Default: 8888')
    parser.add_argument('--white-list',
                        help='File path with the list of allowed devices')
    parser.add_argument('--black-list',
                        help='File path with the list of not allowed devices')
    parser.add_argument('--url-api',
                        help=textwrap.dedent('''
                        Access control api URL. The URL should expect two parameters {action} and {id}.
                        Example: http://127.0.0.1:8888/api/action/{action}/{id}/. 
                        * Local policies are applied first, followed by remote policies
                        '''))

    return parser.parse_args()


def main():
    global host
    global port
    global white_list
    global black_list
    global url_api

    args = parse_args()
    host = args.host
    port = args.port
    white_list_path = args.white_list
    black_list_path = args.black_list
    url_api = args.url_api

    white_list = SortedSet([])
    if white_list_path:
        if not os.path.exists(white_list_path):
            msg = 'The file with the list of allowed devices does not exist.'
            logger.error(msg)
            sys.exit(msg)
        else:
            devices = read_devices(white_list_path)
            white_list = SortedSet(devices)

    black_list = SortedSet([])
    if black_list_path:
        if not os.path.exists(black_list_path):
            msg = 'The file with the list of disallowed devices does not exist.'
            logger.error(msg)
            sys.exit(msg)
        else:
            devices = read_devices(black_list_path)
            white_list = SortedSet(devices)

    listener = DeviceListener(on_add=on_added, on_remove=on_removed)
    while True:
        try:
            listener.start()
        except UnsupportedPlatform as e:
            logger.error(e)
            sys.exit(e)
        except Exception as e:
            logger.error(e)
            continue


if __name__ == '__main__':
    main()
