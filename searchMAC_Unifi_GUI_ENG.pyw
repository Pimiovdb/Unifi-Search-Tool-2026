import os
import queue
import re
import threading
import traceback
from urllib.parse import quote, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import tkinter as tk
from tkinter import messagebox, ttk


BASE_URL = "https://api.ui.com"


def norm_mac(mac):
    return re.sub(r"[^0-9a-fA-F]", "", str(mac or "")).lower()


def colon_mac(mac):
    raw = norm_mac(mac)
    if len(raw) != 12:
        return str(mac)
    return ":".join(raw[i:i + 2] for i in range(0, 12, 2))


def connector_console_id_candidates(host_id, host_raw=None):
    raw_values = [host_id]

    if isinstance(host_raw, dict):
        for key in (
            "consoleId",
            "console_id",
            "hostId",
            "host_id",
            "id",
            "uuid",
        ):
            raw_values.append(host_raw.get(key))

        for obj_key in ("host", "console"):
            obj = host_raw.get(obj_key)
            if isinstance(obj, dict):
                for key in ("consoleId", "console_id", "hostId", "host_id", "id", "uuid"):
                    raw_values.append(obj.get(key))

    unique = []
    seen = set()

    def add_candidate(value):
        if value in (None, ""):
            return

        raw = unquote(str(value).strip())
        if not raw:
            return


        if ":" in raw:
            raw = raw.split(":", 1)[0].strip()

        if not raw or ":" in raw:
            return

        if raw not in seen:
            seen.add(raw)
            unique.append(raw)

    for value in raw_values:
        add_candidate(value)

    return unique


def get_any(d, *keys, default=None):
    if not isinstance(d, dict):
        return default

    for key in keys:
        value = d.get(key)
        if value not in (None, ""):
            return value

    return default


def data_from_body(body):
    if isinstance(body, list):
        return body

    if isinstance(body, dict):
        for key in ("data", "items", "results"):
            value = body.get(key)
            if isinstance(value, list):
                return value

    return []


def make_session():
    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )

    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class UniFiLookup:
    def __init__(self, api_key, debug=False, log_func=None):
        self.api_key = api_key
        self.debug = debug
        self.log_func = log_func
        self.session = make_session()
        self._connector_base_cache = {}
        self._sites_cache = {}
        self.headers = {
            "Accept": "application/json",
            "X-API-Key": api_key,
        }

    def log(self, message):
        if self.log_func:
            self.log_func(message)

    def get_json(self, url, params=None, allow_404=False, allow_statuses=None):
        allow_statuses = set(allow_statuses or ())

        try:
            r = self.session.get(
                url,
                headers=self.headers,
                params=params or {},
                timeout=(5, 25),
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Network error while connecting to the UniFi API: {e}") from e

        if self.debug:
            self.log(f"[DEBUG] GET {r.url} -> HTTP {r.status_code}")

        if allow_404 and r.status_code == 404:
            return None

        if r.status_code in allow_statuses:
            return None

        if r.status_code in (401, 403):
            raise RuntimeError(
                f"Access denied: HTTP {r.status_code}. Check your API key and permissions."
            )

        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"UniFi API returned HTTP {r.status_code}: {e}") from e

        try:
            return r.json()
        except ValueError as e:
            raise RuntimeError("UniFi API did not return valid JSON.") from e

    def paginate_site_manager(self, endpoint, params=None):
        results = []
        next_token = None

        while True:
            query = dict(params or {})
            query["pageSize"] = 200

            if next_token:
                query["nextToken"] = next_token

            body = self.get_json(BASE_URL + endpoint, query)
            results.extend(data_from_body(body))

            if not isinstance(body, dict):
                break

            next_token = body.get("nextToken") or body.get("next_token")

            if not next_token:
                break

        return results

    def paginate_network(self, base, path, params=None):
        results = []
        offset = 0
        limit = 200

        while True:
            query = dict(params or {})
            query.setdefault("offset", offset)
            query.setdefault("limit", limit)

            body = self.get_json(base + path, query)
            batch = data_from_body(body)
            results.extend(batch)

            total = None
            if isinstance(body, dict):
                total = body.get("totalCount") or body.get("total")

            if total is not None:
                try:
                    if len(results) >= int(total):
                        break
                except (TypeError, ValueError):
                    break

            if len(batch) < limit:
                break

            offset += limit

        return results

    def host_info_from_item(self, item, source="devices"):
        if not isinstance(item, dict):
            return None, "Unknown host"

        if source == "hosts" or isinstance(item.get("devices"), list):
            host_id = get_any(
                item,
                "hostId",
                "host_id",
                "consoleId",
                "console_id",
                "id",
            )
        else:
            host_id = get_any(
                item,
                "hostId",
                "host_id",
                "consoleId",
                "console_id",
            )

        host_obj = item.get("host") if isinstance(item.get("host"), dict) else {}
        console_obj = item.get("console") if isinstance(item.get("console"), dict) else {}

        if not host_id:
            host_id = get_any(host_obj, "id", "hostId", "consoleId")
        if not host_id:
            host_id = get_any(console_obj, "id", "hostId", "consoleId")

        host_name = get_any(
            item,
            "hostName",
            "host_name",
            "consoleName",
            "console_name",
            "hostname",
            "name",
        )
        if not host_name:
            host_name = get_any(host_obj, "name", "hostname", "displayName")
        if not host_name:
            host_name = get_any(console_obj, "name", "hostname", "displayName")
        if not host_name:
            host_name = "Unknown host"

        return host_id, host_name

    def find_host_from_site_manager_devices(self, wanted_mac):
        items = self.paginate_site_manager("/v1/devices")

        if self.debug:
            self.log(f"[DEBUG] /v1/devices items: {len(items)}")

        for item in items:
            if not isinstance(item, dict):
                continue


            devices = item.get("devices")
            if isinstance(devices, list):
                host_id, host_name = self.host_info_from_item(item, source="devices")

                if self.debug:
                    self.log(
                        f"[DEBUG] Check host/container: {host_name} ({host_id}), devices: {len(devices)}"
                    )

                for dev in devices:
                    dev_mac = get_any(
                        dev,
                        "mac",
                        "macAddress",
                        "ethernetMac",
                    )

                    if norm_mac(dev_mac) == wanted_mac:
                        return {
                            "host_id": host_id,
                            "host_name": host_name,
                            "host_raw": item,
                            "device": dev,
                        }

                continue


            dev_mac = get_any(
                item,
                "mac",
                "macAddress",
                "ethernetMac",
            )

            if norm_mac(dev_mac) == wanted_mac:
                host_id, host_name = self.host_info_from_item(item, source="flat-device")
                return {
                    "host_id": host_id,
                    "host_name": host_name,
                    "host_raw": item,
                    "device": item,
                }

        return None

    def list_hosts(self):
        hosts = []

        try:
            hosts.extend(self.paginate_site_manager("/v1/hosts"))
            if self.debug:
                self.log(f"[DEBUG] /v1/hosts items: {len(hosts)}")
        except RuntimeError as e:
            if self.debug:
                self.log(f"[DEBUG] /v1/hosts not usable: {e}")


        if not hosts:
            try:
                items = self.paginate_site_manager("/v1/devices")
                for item in items:
                    if not isinstance(item, dict):
                        continue

                    if isinstance(item.get("devices"), list):
                        hosts.append(item)
                        continue

                    host_id, _host_name = self.host_info_from_item(item, source="flat-device")
                    if host_id:
                        hosts.append(item)

                if self.debug:
                    self.log(f"[DEBUG] Hosts derived from /v1/devices: {len(hosts)}")
            except RuntimeError as e:
                if self.debug:
                    self.log(f"[DEBUG] Deriving hosts from /v1/devices failed: {e}")

        unique = []
        seen = set()

        for host in hosts:
            source = "hosts" if not isinstance(host.get("devices"), list) else "devices"
            host_id, host_name = self.host_info_from_item(host, source=source)
            if not host_id:
                continue

            candidates = connector_console_id_candidates(host_id, host)
            key = candidates[0] if candidates else str(host_id)
            if key in seen:
                continue

            seen.add(key)
            unique.append({
                "host_id": host_id,
                "host_name": host_name,
                "raw": host,
            })

        return unique

    def discover_connector_base(self, host_id, host_raw=None):
        connector_ids = connector_console_id_candidates(host_id, host_raw)

        if self.debug:
            self.log(f"[DEBUG] Connector ID candidates: {connector_ids}")

        for connector_id in connector_ids:
            if connector_id in self._connector_base_cache:
                return self._connector_base_cache[connector_id]

            encoded_host_id = quote(str(connector_id), safe="")

            candidates = [
                f"{BASE_URL}/v1/connector/consoles/{encoded_host_id}/proxy/network/integration/v1",
                f"{BASE_URL}/v1/connector/consoles/{encoded_host_id}/network/integration/v1",
            ]

            for base in candidates:
                try:
                    body = self.get_json(
                        base + "/sites",
                        params={"offset": 0, "limit": 1},
                        allow_404=True,
                        allow_statuses=(400,),
                    )
                except RuntimeError as e:
                    if self.debug:
                        self.log(f"[DEBUG] Connector test failed for {connector_id}: {e}")
                    continue

                if body is not None:
                    if self.debug:
                        self.log(f"[DEBUG] Connector found: {base}")
                    self._connector_base_cache[connector_id] = base
                    return base

            self._connector_base_cache[connector_id] = None

        return None

    def list_sites_cached(self, base):
        if base not in self._sites_cache:
            self._sites_cache[base] = self.paginate_network(base, "/sites")
        return self._sites_cache[base]

    def find_device_in_site_device_list(self, base, site, wanted_mac, include_filter=True, include_unfiltered=False):
        site_id = get_any(site, "id", "siteId", "_id")
        site_name = get_any(
            site,
            "name",
            "desc",
            "internalReference",
            default="Unknown site",
        )

        if not site_id:
            return None

        if self.debug:
            self.log(f"[DEBUG] Checking site: {site_name} ({site_id})")

        wanted_colon = colon_mac(wanted_mac)

        searches = []
        if include_filter:
            searches.append(({"filter": f"macAddress.eq('{wanted_colon}')"}, "filter"))
        if include_unfiltered:
            searches.append((None, "full list"))

        for params, label in searches:
            try:
                devices = self.paginate_network(
                    base,
                    f"/sites/{site_id}/devices",
                    params=params,
                )
            except RuntimeError as e:
                if self.debug:
                    self.log(
                        f"[DEBUG] Could not retrieve devices for site {site_name} ({label}): {e}"
                    )
                continue

            if self.debug:
                self.log(
                    f"[DEBUG] Devices in site {site_name} via {label}: {len(devices)}"
                )

            for dev in devices:
                dev_mac = get_any(
                    dev,
                    "macAddress",
                    "mac",
                    "ethernetMac",
                )

                if norm_mac(dev_mac) == wanted_mac:
                    return {
                        "site": site,
                        "site_id": site_id,
                        "site_name": site_name,
                        "device": dev,
                        "connector_base": base,
                    }

        return None

    def find_device_in_sites(self, host_id, wanted_mac, host_raw=None):
        base = self.discover_connector_base(host_id, host_raw)

        if not base:
            raise RuntimeError(
                "Could not open the Network Integration API through the cloud connector. "
                "Check that the host is online and that your API key has sufficient permissions."
            )

        sites = self.list_sites_cached(base)

        if self.debug:
            self.log(f"[DEBUG] Number of sites found on host: {len(sites)}")


        for site in sites:
            found = self.find_device_in_site_device_list(base, site, wanted_mac, include_filter=True)
            if found:
                return found


        if self.debug:
            self.log("[DEBUG] No filter match; starting deep scan with full device lists")

        for site in sites:
            found = self.find_device_in_site_device_list(base, site, wanted_mac, include_filter=False, include_unfiltered=True)
            if found:
                return found

        return None

    def find_device_by_scanning_all_hosts_and_sites(self, wanted_mac):
        hosts = self.list_hosts()

        if self.debug:
            self.log(f"[DEBUG] Fallback scanning hosts/controllers: {len(hosts)}")

        for host in hosts:
            host_id = host["host_id"]
            host_name = host["host_name"]

            if self.debug:
                self.log(f"[DEBUG] Fallback checking host/controller: {host_name} ({host_id})")

            try:
                base = self.discover_connector_base(host_id, host.get("raw"))
            except RuntimeError as e:
                if self.debug:
                    self.log(f"[DEBUG] Retrieving connector failed for host {host_name}: {e}")
                continue

            if not base:
                if self.debug:
                    self.log(f"[DEBUG] No connector available for host {host_name}")
                continue

            try:
                sites = self.list_sites_cached(base)
            except RuntimeError as e:
                if self.debug:
                    self.log(f"[DEBUG] Could not retrieve sites for host {host_name}: {e}")
                continue

            if self.debug:
                self.log(f"[DEBUG] Fallback sites on {host_name}: {len(sites)}")


            for include_unfiltered in (False, True):
                if include_unfiltered and self.debug:
                    self.log(f"[DEBUG] Deep scan full device lists on {host_name}")

                for site in sites:
                    found = self.find_device_in_site_device_list(
                        base, site, wanted_mac, include_filter=not include_unfiltered, include_unfiltered=include_unfiltered
                    )
                    if found:
                        return {
                            "host_id": host_id,
                            "host_name": host_name,
                            "found_site": found,
                        }

        return None


def format_result(host_name, host_id, found_site, sm_device, args_mac):
    lines = []
    lines.append("Found UniFi device:")
    lines.append("-" * 80)

    if found_site:
        dev = found_site["device"]

        lines.append(f"Host/controller: {host_name}")
        lines.append(f"Host ID: {host_id}")
        lines.append(f"Site name: {found_site['site_name']}")
        lines.append(f"Site ID: {found_site['site_id']}")
        lines.append("")
        lines.append(f"Name: {get_any(dev, 'name', 'displayName', 'shortname', default='Unknown')}")
        lines.append(f"Model: {get_any(dev, 'model', 'modelName', default='Unknown')}")
        lines.append(f"MAC: {get_any(dev, 'macAddress', 'mac', default=colon_mac(args_mac))}")
        lines.append(f"IP: {get_any(dev, 'ipAddress', 'ip', default='Unknown')}")
        lines.append(f"Status: {get_any(dev, 'state', 'status', default='Unknown')}")
        last_seen = get_any(dev, 'lastSeen', 'lastSeenAt', 'last_seen', 'last_seen_at')
        if last_seen:
            lines.append(f"Last seen: {last_seen}")
        lines.append(f"Device ID: {get_any(dev, 'id', '_id', default='Unknown')}")

    else:
        lines.append(f"Host/controller: {host_name}")
        lines.append(f"Host ID: {host_id}")
        lines.append("Site name: Not found")
        lines.append("Site ID: Not found")
        lines.append("")
        lines.append(f"Name: {get_any(sm_device, 'name', 'shortname', default='Unknown')}")
        lines.append(f"Model: {get_any(sm_device, 'model', default='Unknown')}")
        lines.append(f"MAC: {get_any(sm_device, 'mac', 'macAddress', default=colon_mac(args_mac))}")
        lines.append(f"IP: {get_any(sm_device, 'ip', 'ipAddress', default='Unknown')}")
        lines.append(f"Status: {get_any(sm_device, 'status', 'state', default='Unknown')}")
        last_seen = get_any(sm_device, 'lastSeen', 'lastSeenAt', 'last_seen', 'last_seen_at')
        if last_seen:
            lines.append(f"Last seen: {last_seen}")
        lines.append("")
        lines.append(
            "Note: the device was found on the host/controller, but not within an underlying site."
        )
        lines.append("Optionally enable debug and try again.")

    return "\n".join(lines)


def lookup_device(api_key, mac, debug=False, log_func=None):
    api_key = (api_key or "").strip()
    mac = (mac or "").strip()

    if not api_key:
        raise RuntimeError("Enter a UniFi API key.")

    wanted = norm_mac(mac)

    if len(wanted) != 12:
        raise RuntimeError(f"Invalid MAC address: {mac}")

    def log(message):
        if log_func:
            log_func(message)

    log(f"Searching for MAC: {colon_mac(wanted)}")

    unifi = UniFiLookup(api_key, debug=debug, log_func=log)
    found_host = unifi.find_host_from_site_manager_devices(wanted)

    if found_host:
        host_id = found_host["host_id"]
        host_name = found_host["host_name"]
        sm_device = found_host["device"]

        log(f"Device found via /v1/devices on host/controller: {host_name}")

        if not host_id:
            return format_result(
                host_name=host_name,
                host_id="Unknown",
                found_site=None,
                sm_device=sm_device,
                args_mac=mac,
            )

        log("Searching within underlying sites...")
        try:
            found_site = unifi.find_device_in_sites(host_id, wanted, found_host.get("host_raw"))
        except RuntimeError as e:
            log(f"Site lookup through the found host failed: {e}")
            log(
                "Device has already been found via /v1/devices; all-host fallback is being skipped "
                "to keep CloudKeys/single-site controllers fast."
            )
            found_site = None

        return format_result(
            host_name=host_name,
            host_id=host_id,
            found_site=found_site,
            sm_device=sm_device,
            args_mac=mac,
        )

    log("Not found via /v1/devices; fallback is now scanning all hosts and sites...")
    fallback = unifi.find_device_by_scanning_all_hosts_and_sites(wanted)

    if fallback:
        return format_result(
            host_name=fallback["host_name"],
            host_id=fallback["host_id"],
            found_site=fallback["found_site"],
            sm_device=None,
            args_mac=mac,
        )

    return (
        "Device not found.\n\n"
        "Tried:\n"
        "- search via /v1/devices;\n"
        "- fallback: scan all available hosts/controllers and underlying sites through the Network Integration API.\n\n"
        "Check:\n"
        "- whether the MAC address is correct;\n"
        "- whether the API key has sufficient permissions;\n"
        "- whether the host/controller is online and linked to Site Manager;\n"
        "- whether this device is still in the UniFi Network device list for that site."
    )


class UniFiLookupApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("UniFi MAC to site lookup")
        self.minsize(820, 560)

        self.worker = None
        self.events = queue.Queue()

        self.api_key_var = tk.StringVar(value=os.getenv("UNIFI_API_KEY", ""))
        self.mac_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)
        self.debug_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._poll_events()

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(5, weight=1)

        title = ttk.Label(root, text="UniFi MAC to site lookup", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ttk.Label(root, text="API key:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.api_entry = ttk.Entry(root, textvariable=self.api_key_var, show="*", width=70)
        self.api_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)

        ttk.Label(root, text="MAC address:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.mac_entry = ttk.Entry(root, textvariable=self.mac_var, width=30)
        self.mac_entry.grid(row=2, column=1, sticky="ew", pady=4)
        self.mac_entry.bind("<Return>", lambda _event: self.start_lookup())

        options = ttk.Frame(root)
        options.grid(row=2, column=2, columnspan=2, sticky="e", pady=4)

        ttk.Checkbutton(
            options,
            text="show key",
            variable=self.show_key_var,
            command=self.toggle_key_visibility,
        ).grid(row=0, column=0, padx=(0, 10))

        ttk.Checkbutton(
            options,
            text="debug",
            variable=self.debug_var,
        ).grid(row=0, column=1)

        buttons = ttk.Frame(root)
        buttons.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 8))
        buttons.grid_columnconfigure(3, weight=1)

        self.search_button = ttk.Button(buttons, text="Search", command=self.start_lookup)
        self.search_button.grid(row=0, column=0, padx=(0, 8))

        ttk.Button(buttons, text="Clear output", command=self.clear_output).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Copy result", command=self.copy_output).grid(row=0, column=2, padx=(0, 8))

        self.progress = ttk.Progressbar(buttons, mode="indeterminate", length=180)
        self.progress.grid(row=0, column=4, sticky="e")

        ttk.Label(root, textvariable=self.status_var).grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 4))

        output_frame = ttk.Frame(root)
        output_frame.grid(row=5, column=0, columnspan=4, sticky="nsew")
        output_frame.grid_rowconfigure(0, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)

        self.output = tk.Text(output_frame, wrap="word", height=20, font=("Consolas", 10))
        self.output.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scrollbar.set)

        hint = (
            "Enter your UniFi Site Manager API key and MAC address. "
            "The API key is not saved."
        )
        ttk.Label(root, text=hint).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

        if self.api_key_var.get():
            self.mac_entry.focus_set()
        else:
            self.api_entry.focus_set()

    def toggle_key_visibility(self):
        self.api_entry.configure(show="" if self.show_key_var.get() else "*")

    def clear_output(self):
        self.output.delete("1.0", "end")
        self.status_var.set("Ready")

    def copy_output(self):
        text = self.output.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Copy result", "There is no output to copy yet.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Result copied to clipboard")

    def append_output(self, text):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def set_busy(self, busy):
        if busy:
            self.search_button.configure(state="disabled")
            self.progress.start(10)
            self.status_var.set("Searching...")
        else:
            self.search_button.configure(state="normal")
            self.progress.stop()

    def start_lookup(self):
        if self.worker and self.worker.is_alive():
            return

        api_key = self.api_key_var.get()
        mac = self.mac_var.get()
        debug = self.debug_var.get()

        self.clear_output()
        self.set_busy(True)

        self.worker = threading.Thread(
            target=self._run_lookup,
            args=(api_key, mac, debug),
            daemon=True,
        )
        self.worker.start()

    def _run_lookup(self, api_key, mac, debug):
        def log(message):
            self.events.put(("log", message))

        try:
            result = lookup_device(api_key, mac, debug=debug, log_func=log)
            self.events.put(("result", result))
        except Exception as e:
            if debug:
                details = traceback.format_exc()
                self.events.put(("error", f"Error: {e}\n\n{details}"))
            else:
                self.events.put(("error", f"Error: {e}"))
        finally:
            self.events.put(("done", None))

    def _poll_events(self):
        try:
            while True:
                event_type, payload = self.events.get_nowait()

                if event_type == "log":
                    self.append_output(str(payload))
                elif event_type == "result":
                    if self.output.get("1.0", "end").strip():
                        self.append_output("")
                    self.append_output(str(payload))
                    self.status_var.set("Lookup complete")
                elif event_type == "error":
                    self.append_output(str(payload))
                    self.status_var.set("Error")
                    messagebox.showerror("UniFi lookup error", str(payload).split("\n", 1)[0])
                elif event_type == "done":
                    self.set_busy(False)
        except queue.Empty:
            pass

        self.after(100, self._poll_events)


if __name__ == "__main__":
    app = UniFiLookupApp()
    app.mainloop()
