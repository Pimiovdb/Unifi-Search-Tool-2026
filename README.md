# UniFi MAC to Site Lookup GUI

A small Python/Tkinter desktop tool that searches the UniFi Site Manager API for a UniFi device by MAC address and shows the host/controller and site where the device belongs.

The tool is useful when you manage multiple UniFi hosts, CloudKeys, or sites and want to quickly map a device MAC address to the correct UniFi site.

## Features

- Search UniFi devices by MAC address.
- Accepts common MAC address formats, for example:
  - `24:5a:4c:9d:76:ec`
  - `24-5A-4C-9D-76-EC`
  - `245A4C9D76EC`
- Uses the UniFi Site Manager API endpoint `/v1/devices` first.
- Tries to resolve the underlying UniFi Network site through the connector Network Integration API.
- Includes a fallback scan across available hosts/controllers and sites.
- Shows useful device information such as:
  - host/controller name and ID
  - site name and ID
  - device name
  - model
  - MAC address
  - IP address
  - status
  - last seen timestamp, when available
  - device ID
- Optional debug output for troubleshooting API or permission issues.
- API key can be entered manually or loaded from the `UNIFI_API_KEY` environment variable.
- The API key is not saved by the application.

## Project files

```text
.
├── searchMAC_Unifi_GUI_ENG.pyw       # Main GUI application
├── start_searchMAC_unifi_gui.bat     # Windows launcher
├── requirements_unifi_gui.txt        # Python dependency list
└── README.md                         # Project documentation
```

## Requirements

- Python 3.9 or newer recommended.
- A UniFi Site Manager API key.
- Network/API access to `https://api.ui.com`.
- Python package:
  - `requests>=2.31.0`

Tkinter is used for the graphical interface and is included with most standard Python installations.

## Installation

Clone the repository:

```bash
git clone https://github.com/Pimiovdb/Unifi-Search-Tool-2026.git
cd Unifi-Search-Tool-2026
```

Install the required Python package:

```bash
py -m pip install -r requirements_unifi_gui.txt
```

On Linux or macOS, use `python3` instead of `py` when needed:

```bash
python3 -m pip install -r requirements_unifi_gui.txt
```

## Usage on Windows

The easiest way to start the application on Windows is to run:

```bat
start_searchMAC_unifi_gui.bat
```

The batch file checks whether `requests` is installed. If it is missing, it installs the package from `requirements_unifi_gui.txt` and then starts the GUI.

You can also start the application manually:

```bat
py searchMAC_Unifi_GUI_ENG.pyw
```

## Usage on Linux or macOS

Run the Python file directly:

```bash
python3 searchMAC_Unifi_GUI_ENG.pyw
```

Depending on your Python installation, you may need to install Tkinter separately. For example, on Debian/Ubuntu-based systems:

```bash
sudo apt install python3-tk
```

## Using an environment variable for the API key

The application reads the `UNIFI_API_KEY` environment variable when it starts. This is optional, but useful if you do not want to paste the key every time.

### Windows PowerShell

```powershell
$env:UNIFI_API_KEY="your-api-key-here"
py searchMAC_Unifi_GUI_ENG.pyw
```

### Windows Command Prompt

```cmd
set UNIFI_API_KEY=your-api-key-here
py searchMAC_Unifi_GUI_ENG.pyw
```

### Linux/macOS

```bash
export UNIFI_API_KEY="your-api-key-here"
python3 searchMAC_Unifi_GUI_ENG.pyw
```

## How it works

The application follows this lookup flow:

1. Normalize the entered MAC address by removing separators and converting it to lowercase.
2. Search the UniFi Site Manager `/v1/devices` endpoint.
3. If the device is found on a host/controller, try to open the Network Integration API through the UniFi cloud connector.
4. Retrieve sites from the host/controller.
5. Search the device list for each site.
6. If the filtered lookup does not return a result, perform a deeper scan using full device lists.
7. If the device is still not found, fall back to scanning all available hosts/controllers and their sites.

## Example output

```text
Searching for MAC: 24:5a:4c:9d:76:ec
Device found via /v1/devices on host/controller: Example CloudKey
Searching within underlying sites...

Found UniFi device:
--------------------------------------------------------------------------------
Host/controller: Example CloudKey
Host ID: abc123
Site name: Main Office
Site ID: def456

Name: UAP-Office-01
Model: U7-Pro
MAC: 24:5a:4c:9d:76:ec
IP: 192.168.1.20
Status: online
Last seen: 2026-05-13T10:00:00Z
Device ID: xyz789
```

## Troubleshooting

### Access denied: HTTP 401 or 403

Check that the API key is correct and has sufficient permissions for the UniFi Site Manager and the relevant hosts/controllers.

### Device not found

Check the following:

- The entered MAC address is correct.
- The device still exists in the UniFi Network device list.
- The host/controller is online.
- The host/controller is linked to UniFi Site Manager.
- The API key has access to the required host/controller and site.

### Site name is not found

The device may be visible through Site Manager, but the underlying Network Integration API may not be reachable or the API key may not have enough permissions to read the site/device list.

Enable the `debug` checkbox and run the lookup again to see more details.

### Tkinter is missing

On some Linux installations, Tkinter is not installed by default. Install it with your package manager, for example:

```bash
sudo apt install python3-tk
```

## Disclaimer

This project is not affiliated with, endorsed by, or supported by Ubiquiti Inc. or UniFi. Use it at your own risk and test it in your own environment.

