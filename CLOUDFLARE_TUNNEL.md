# Cloudflare Quick Tunnel — Visitor Diagnostic

This guide documents how to run the authorized browser diagnostic server behind a temporary Cloudflare Quick Tunnel.

## 1. Prerequisites

Check that the diagnostic script exists:

```bash
ls -l ~/hacking/visitor_diagnostic_fixed.py
python3 --version
```

## 2. Install cloudflared

On Kali/Debian-based Linux:

```bash
cd /tmp

curl -L --output cloudflared.deb \
  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"

sudo dpkg -i cloudflared.deb
```

Verify:

```bash
cloudflared --version
```

## 3. Start the diagnostic server

Open Terminal 1:

```bash
python3 ~/hacking/visitor_diagnostic_fixed.py
```

The server should listen on:

```text
http://0.0.0.0:8080
```

Keep this terminal running.

Optional local test:

```bash
curl http://127.0.0.1:8080
```

Check the port:

```bash
ss -lntp | grep ':8080'
```

## 4. Start the Cloudflare Quick Tunnel

Open Terminal 2:

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

Cloudflare will print a temporary URL similar to:

```text
https://random-name.trycloudflare.com
```

Copy that URL.

## 5. Test the URL

Open the generated HTTPS URL in a browser.

The diagnostic page requires the visitor to explicitly consent before browser diagnostic data is sent.

After consent, click:

```text
Send Diagnostics
```

The diagnostic information is printed in Terminal 1.

## 6. Keep both terminals running

Terminal 1:

```bash
python3 ~/hacking/visitor_diagnostic_fixed.py
```

Terminal 2:

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

If either process stops, the service/tunnel stops.

Stop either process with:

```text
Ctrl+C
```

## 7. Restarting later

After rebooting, you do not need to reinstall cloudflared.

Run:

```bash
python3 ~/hacking/visitor_diagnostic_fixed.py
```

Then:

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

A Quick Tunnel normally provides a new temporary `trycloudflare.com` URL when a new tunnel is started.

## 8. Troubleshooting

### cloudflared command not found

```bash
cd /tmp

curl -L --output cloudflared.deb \
  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"

sudo dpkg -i cloudflared.deb
```

### 502 Bad Gateway

Check that the Python server is running:

```bash
curl http://127.0.0.1:8080
```

Then restart the Python server if necessary.

### Port 8080 is already in use

```bash
sudo ss -lntp | grep ':8080'
```

Stop the process using the port, or change the port in the diagnostic script and use the matching port in the tunnel command.

### Visitor source IP is incorrect

The diagnostic script is designed to use Cloudflare's `CF-Connecting-IP` header when available. Make sure you are using the current `visitor_diagnostic_fixed.py` and that requests are going through the Cloudflare Tunnel.

## 9. Security notes

- Use this only for systems and visitors where you have authorization/consent.
- The diagnostic page collects information exposed by the HTTP request and browser APIs used by the page.
- A normal website cannot directly obtain a visitor's MAC address, process list, files, or other private system data.
- IP geolocation is approximate and is not equivalent to GPS.
- Do not commit Cloudflare credentials, API tokens, SSH private keys, passwords, or visitor logs to Git.
- Quick Tunnels are intended for testing/development. For persistent production use, use a properly configured named Cloudflare Tunnel.

## 10. Git commands

After adding or changing this guide:

```bash
cd ~/hacking
git add CLOUDFLARE_TUNNEL.md
git commit -m "Add Cloudflare Tunnel setup guide"
git push
```
