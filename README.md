# How

usbsecurity-monitor is the program to control USB ports.

# Installation

pip3 install usbsecurity-monitor

# Usage

Is a console program and runs like a fiend. To get it running open a terminal and run the following command:

$ usbsecurity-monitor

## Local

By default the application runs in local mode blocking access to the computer's USB ports as a basic policy. You can configure device whitelists and blacklists.

## Client

In administration environments it would be good to manage permissions from a server on the network. In these scenarios you can configure the application to request permissions from the server through a REST API:

usbsecurity-monitor --url-api _url_api_rest_

_Local policies are a priority_

# Help

$ usbsecurity-monitor -h | --help
