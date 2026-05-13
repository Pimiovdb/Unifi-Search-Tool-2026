# UniFi MAC Search Tool

A small Windows desktop tool for finding the UniFi host/controller and site that belong to a specific device MAC address.

The tool searches the UniFi Site Manager API and tries to map the entered MAC address to the correct UniFi site. It is useful when you manage multiple UniFi hosts, CloudKeys, controllers, or sites.

## Download latest release

The recommended way to use this tool is to download the latest Windows release:

[Download the latest release](https://github.com/Pimiovdb/Unifi-Search-Tool-2026/releases/latest)

Download the Windows release asset, extract it if needed, and run the `.exe` file.

No Python installation is required when using the release version.

## Requirements

To use the application, you need:

- A UniFi Site Manager API key.
- Access to `https://api.ui.com`.
- Permission to read the UniFi hosts/controllers and sites you want to search.

The API key can be entered in the application.

The application does not save the API key.

## Features

- Search UniFi devices by MAC address.
- Accepts common MAC address formats, including:
  - `24:5a:4c:9d:76:ec`
  - `24-5A-4C-9D-76-EC`
  - `245A4C9D76EC`
- Uses the UniFi Site Manager API.
- Tries to resolve the matching UniFi host/controller.
- Tries to resolve the underlying UniFi Network site.
- Includes fallback searching across available hosts/controllers and sites.
- Shows useful device information, including:
  - host/controller name
  - host/controller ID
  - site name
  - site ID
  - device name
  - model
  - MAC address
  - IP address
  - status
  - last seen timestamp, when available
  - device ID
- Includes optional debug output for troubleshooting API or permission issues.

## How it works

The application follows this lookup flow:

1. Normalize the entered MAC address.
2. Search the UniFi Site Manager device list.
3. Identify the host/controller where the device is known.
4. Try to connect to the underlying UniFi Network API for that host/controller.
5. Retrieve available sites.
6. Search the device lists inside the available sites.
7. Show the matching host/controller and site information.
8. If the first lookup does not return enough information, perform a fallback scan across available hosts/controllers and sites.

## Troubleshooting

### API key does not work

Check that the API key is valid and has access to the required UniFi Site Manager resources.

Also check that the UniFi host/controller is visible in UniFi Site Manager.

### HTTP 401 or 403

This usually means the API key is missing, invalid, expired, or does not have enough permissions.

Create or update the API key in UniFi Site Manager and try again.

### Device not found

Check the following:

- The MAC address is correct.
- The device still exists in UniFi Network.
- The device belongs to a host/controller linked to UniFi Site Manager.
- The host/controller is online.
- The API key has access to the required host/controller and site.

### Site name is missing

The device may be visible in UniFi Site Manager, but the underlying UniFi Network site information may not be available through the API.

Enable debug output and run the lookup again to see more details.

## Build from source

This section is only for developers or users who want to build the Windows executable themselves.

Clone the repository:

```bash
git clone https://github.com/Pimiovdb/Unifi-Search-Tool-2026.git
cd Unifi-Search-Tool-2026
```

Create a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
```

Install the required packages:

```powershell
python -m pip install --upgrade pip
pip install -r requirements_unifi_gui.txt
pip install pyinstaller
```

Build the Windows executable:

```powershell
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "UniFi-Search-Tool" searchMAC_Unifi_GUI_ENG.pyw
```

The built executable will be created in:

```text
dist\UniFi-Search-Tool.exe
```

## Disclaimer

This project is not affiliated with, endorsed by, or supported by Ubiquiti Inc. or UniFi.

Use it at your own risk and test it in your own environment.
