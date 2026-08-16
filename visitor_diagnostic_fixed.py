#!/usr/bin/env python3

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

HOST = "0.0.0.0"
PORT = 8080

# This page explicitly asks the visitor to consent before browser diagnostics
# are sent to the server.
HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Browser Diagnostic</title>
<style>
body{font-family:system-ui,sans-serif;max-width:650px;margin:50px auto;padding:20px}
button{padding:12px 18px;font-size:16px;cursor:pointer}
</style>
</head>
<body>
<h2>Browser Diagnostic</h2>
<p>This diagnostic sends basic browser/device information to the diagnostic server.</p>
<label><input id="consent" type="checkbox"> I consent to sending the diagnostic information.</label>
<br><br>
<button onclick="sendDiagnostics()">Send Diagnostics</button>
<pre id="status"></pre>

<script>
async function sendDiagnostics() {
    if (!document.getElementById("consent").checked) {
        document.getElementById("status").textContent =
            "Please provide consent first.";
        return;
    }

    const data = {
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
        timezone_offset_minutes: new Date().getTimezoneOffset(),
        language: navigator.language || null,
        languages: navigator.languages || [],
        platform: navigator.platform || null,
        user_agent: navigator.userAgent || null,
        vendor: navigator.vendor || null,

        screen_width: screen.width || null,
        screen_height: screen.height || null,
        avail_width: screen.availWidth || null,
        avail_height: screen.availHeight || null,
        color_depth: screen.colorDepth || null,
        pixel_depth: screen.pixelDepth || null,
        device_pixel_ratio: window.devicePixelRatio || null,

        viewport_width: window.innerWidth || null,
        viewport_height: window.innerHeight || null,

        hardware_concurrency: navigator.hardwareConcurrency || null,
        device_memory_gb: navigator.deviceMemory || null,
        max_touch_points: navigator.maxTouchPoints || 0,
        online: navigator.onLine,

        cookies_enabled: navigator.cookieEnabled,
        do_not_track: navigator.doNotTrack || null,

        connection: (function () {
            const c = navigator.connection ||
                      navigator.mozConnection ||
                      navigator.webkitConnection;
            if (!c) return null;
            return {
                effective_type: c.effectiveType || null,
                downlink_mbps: c.downlink || null,
                rtt_ms: c.rtt || null,
                save_data: c.saveData || false
            };
        })()
    };

    document.getElementById("status").textContent =
        "Sending diagnostics...";

    try {
        const response = await fetch("/diagnostic", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });

        const result = await response.json();
        document.getElementById("status").textContent =
            result.message || "Diagnostic sent.";
    } catch (e) {
        document.getElementById("status").textContent =
            "Could not send diagnostics.";
    }
}
</script>
</body>
</html>
"""


def valid_ip(value):
    if not value:
        return False
    value = value.strip()
    # Basic IPv4/IPv6 validation without importing extra packages.
    if ":" in value:
        return bool(re.fullmatch(r"[0-9A-Fa-f:]+", value))
    return bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value))


def get_client_ip(handler):
    """
    When using Cloudflare Tunnel, the origin sees the tunnel connection.
    CF-Connecting-IP contains the original visitor IP.
    Only trust this header because this script is intended to sit behind
    the user's Cloudflare Tunnel. A directly exposed server must not trust
    arbitrary client-supplied forwarding headers.
    """
    cf_ip = handler.headers.get("CF-Connecting-IP")
    if valid_ip(cf_ip):
        return cf_ip.strip()

    # Local/LAN testing fallback.
    return handler.client_address[0]


def geolocate_ip(ip):
    if not valid_ip(ip) or ip in {
        "127.0.0.1", "::1", "0.0.0.0"
    }:
        return {}

    try:
        # ip-api accepts both IPv4 and IPv6 addresses.
        fields = (
            "status,country,countryCode,regionName,region,city,"
            "lat,lon,timezone,isp,org,as,query"
        )
        url = (
            "http://ip-api.com/json/"
            + urllib.parse.quote(ip, safe="")
            + "?fields="
            + fields
        )

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Authorized-Diagnostic/1.0"}
        )

        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))

        if data.get("status") == "success":
            return data

    except Exception as exc:
        print(f"[!] Geolocation lookup failed: {exc}")

    return {}


def classify_device(browser):
    ua = (browser.get("user_agent") or "").lower()
    platform = (browser.get("platform") or "").lower()

    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        if "mobile" in ua:
            return "Android phone"
        return "Android tablet"
    if "windows" in ua:
        return "Windows PC"
    if "macintosh" in ua or "mac os x" in ua:
        return "Mac"
    if "linux" in platform or "linux" in ua:
        return "Linux PC"
    return "Unknown"


def browser_name(browser):
    ua = browser.get("user_agent") or ""

    # Order matters: Edge/Chrome contain Chrome in their UA.
    patterns = [
        ("EdgiOS", "Edge iOS"),
        ("Edg/", "Microsoft Edge"),
        ("OPiOS", "Opera iOS"),
        ("OPR/", "Opera"),
        ("CriOS/", "Chrome iOS"),
        ("Chrome/", "Chrome"),
        ("FxiOS/", "Firefox iOS"),
        ("Firefox/", "Firefox"),
        ("Version/", "Safari"),
    ]

    for token, name in patterns:
        if token in ua:
            return name

    return "Unknown"


def print_report(handler, browser):
    client_ip = get_client_ip(handler)
    geo = geolocate_ip(client_ip)

    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")

    print()
    print("=" * 72)
    print("  VISITOR DIAGNOSTIC")
    print("=" * 72)
    print(f"Time:              {stamp}")
    print(f"Source IP:         {client_ip}")

    cf_country = handler.headers.get("CF-IPCountry")
    cf_ray = handler.headers.get("CF-Ray")

    print()
    print("PUBLIC IP GEOLOCATION")
    print("-" * 72)

    if geo:
        print(f"Country:           {geo.get('country', 'Unknown')}")
        print(f"Country code:      {geo.get('countryCode', 'Unknown')}")
        print(f"Region:            {geo.get('regionName', 'Unknown')}")
        print(f"City:              {geo.get('city', 'Unknown')}")
        print(f"Latitude:          {geo.get('lat', 'Unknown')}")
        print(f"Longitude:         {geo.get('lon', 'Unknown')}")
        print(f"Timezone:          {geo.get('timezone', 'Unknown')}")
        print(f"ISP:               {geo.get('isp', 'Unknown')}")
        print(f"Organization:      {geo.get('org', 'Unknown')}")
        print(f"ASN:               {geo.get('as', 'Unknown')}")
    else:
        print("Geolocation:       unavailable")
        print("Note: IP geolocation is approximate, not GPS.")

    if cf_country:
        print(f"Cloudflare country: {cf_country}")
    if cf_ray:
        print(f"Cloudflare Ray:     {cf_ray}")

    print()
    print("DEVICE / BROWSER")
    print("-" * 72)
    print(f"Device:            {classify_device(browser)}")
    print(f"Browser:           {browser_name(browser)}")
    print(f"Platform:          {browser.get('platform')}")
    print(f"User-Agent:        {browser.get('user_agent')}")
    print(f"Vendor:             {browser.get('vendor')}")
    print(f"Language:          {browser.get('language')}")
    print(f"Languages:         {', '.join(browser.get('languages') or [])}")
    print(f"Timezone:          {browser.get('timezone')}")
    print(f"UTC offset:        {browser.get('timezone_offset_minutes')} minutes")

    print()
    print("DISPLAY")
    print("-" * 72)
    print(
        f"Screen:            {browser.get('screen_width')} x "
        f"{browser.get('screen_height')}"
    )
    print(
        f"Available screen:  {browser.get('avail_width')} x "
        f"{browser.get('avail_height')}"
    )
    print(
        f"Viewport:          {browser.get('viewport_width')} x "
        f"{browser.get('viewport_height')}"
    )
    print(f"Pixel ratio:       {browser.get('device_pixel_ratio')}")
    print(f"Color depth:       {browser.get('color_depth')}")

    print()
    print("DEVICE CAPABILITIES")
    print("-" * 72)
    print(f"CPU threads:       {browser.get('hardware_concurrency')}")
    print(f"Memory (reported): {browser.get('device_memory_gb')}")
    print(f"Touch points:      {browser.get('max_touch_points')}")
    print(f"Online:            {browser.get('online')}")
    print(f"Cookies enabled:   {browser.get('cookies_enabled')}")
    print(f"Do Not Track:      {browser.get('do_not_track')}")

    connection = browser.get("connection")
    if connection:
        print()
        print("NETWORK HINTS")
        print("-" * 72)
        print(f"Effective type:    {connection.get('effective_type')}")
        print(f"Downlink:          {connection.get('downlink_mbps')} Mbps")
        print(f"RTT:               {connection.get('rtt_ms')} ms")
        print(f"Save-Data:         {connection.get('save_data')}")

    print()
    print("=" * 72)
    print("[+] Displayed in terminal only; no report file was saved.")
    print("=" * 72)


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path != "/diagnostic":
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 100_000:
                self.send_json({"error": "Request too large"}, 413)
                return

            raw = self.rfile.read(length)
            browser = json.loads(raw.decode("utf-8"))

        except Exception:
            self.send_json({"error": "Invalid diagnostic payload"}, 400)
            return

        print_report(self, browser)

        self.send_json({
            "message": "Diagnostic displayed in the server terminal."
        })


print("=" * 72)
print("  AUTHORIZED VISITOR DIAGNOSTIC SERVER")
print("=" * 72)
print(f"Listening: http://0.0.0.0:{PORT}")
print("Designed for use behind your Cloudflare Quick Tunnel.")
print("No visitor reports are written to disk.")
print("Press Ctrl+C to stop.")
print("=" * 72)

server = HTTPServer((HOST, PORT), Handler)

try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\n[+] Server stopped.")
    server.server_close()



