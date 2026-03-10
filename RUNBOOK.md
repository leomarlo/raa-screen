# Raa Screen Server — Runbook

## Start server locally + expose via tunnel

**Terminal 1 — start the API:**
```bash
cd raa-screen-server/server-app
docker compose up --build
```

**Terminal 2 — create Cloudflare tunnel:**
```bash
cloudflared tunnel --url http://localhost:8000
```
Copy the printed URL (e.g. `https://something-random.trycloudflare.com`).
Update `screen-app/.env` on the Pi: `API_URL=https://something-random.trycloudflare.com/resource`

---

## Deploy screen-app to the Pi

Set your Pi host once (add to `~/.zshrc` to make it permanent):
```bash
export PI_HOST=raspberrypi.local   # or use IP: export PI_HOST=192.168.8.20
export PI_USER=leo
```

`raspberrypi.local` works when on the same network. If it fails, use the IP (`hostname -I` on the Pi).

**First time only — copy files then run setup:**
```bash
rsync -avz screen-app/ $PI_USER@$PI_HOST:~/screen-app/
ssh $PI_USER@$PI_HOST "bash ~/screen-app/scripts/setup_pi.sh"
```

**All future deploys (syncs + restarts service):**
```bash
bash screen-app/scripts/deploy_scp.sh
```

---

## Pi service management

```bash
# Start / stop / restart
sudo systemctl start video-agent.service
sudo systemctl stop video-agent.service
sudo systemctl restart video-agent.service

# Live logs
journalctl -u video-agent.service -f

# Check status
sudo systemctl status video-agent.service
```

---

## Update tunnel URL on the Pi

The Cloudflare quick tunnel URL changes every time you restart it. Update the Pi in one line:
```bash
ssh $PI_USER@$PI_HOST "sed -i 's|API_URL=.*|API_URL=https://NEW-TUNNEL.trycloudflare.com/resource|' ~/screen-app/.env && sudo systemctl restart video-agent.service"
```

---

## Change the resource playing on screen

POST a new resource to the API (tunnel must be running):
```bash
curl -X POST https://<tunnel-url>/resource \
  -H "Content-Type: application/json" \
  -H "x-admin-password: <your-password>" \
  -d '{"resource": {"kind": "direct", "url": "https://example.com/video.mp4", "mime_type": "video/mp4"}}'
```

The Pi polls every 15 seconds and switches automatically.

---

## Test VLC directly on the Pi

```bash
URL="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
DISPLAY=:0 XAUTHORITY=/home/leo/.Xauthority cvlc --fullscreen --loop --no-osd "$URL"
```

---

## Set up Caddy + Cloudflare on Hetzner (recommended)

Gives you `https://your-domain.com` → Caddy on Hetzner (ports 80/443) → Docker app.
Cloudflare acts as DNS proxy; the Cloudflare → server leg uses a Cloudflare Origin Certificate.

**Prerequisites:**
- Domain added to Cloudflare (orange cloud / proxied A record pointing to the Hetzner IP)
- Hetzner firewall allows inbound TCP 80 and 443
- Cloudflare SSL/TLS → Overview set to **Full** (not Flexible, not Strict)

**1. Copy `.env` to the server:**
```bash
scp server-app/.env root@135.181.94.243:/opt/raa-screen-server/.env
```

**2. Start the stack:**
```bash
ssh root@135.181.94.243
cd /opt/raa-screen-server/server-app
docker compose up -d --build
```

Caddy automatically obtains and renews a Let's Encrypt certificate via HTTP-01 challenge (Cloudflare proxies port 80 through to the server). Certs are stored in the `caddy_data` Docker volume and persist across restarts.

**Check Caddy logs:**
```bash
docker compose logs caddy -f
```

---

## Set up Cloudflare Tunnel + custom domain on Hetzner (legacy/alternative)

Gives you `https://your-domain.com` → Hetzner server, no open ports needed.

**Prerequisites:**
- A domain added to Cloudflare (cloudflare.com → Add a site → point your registrar's nameservers to Cloudflare)

**1. Install cloudflared on the Hetzner server:**
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

**2. Authenticate (run on server, opens a browser link):**
```bash
cloudflared tunnel login
```

**3. Create a named tunnel:**
```bash
cloudflared tunnel create raa-screen
```

**4. Route your domain to the tunnel:**
```bash
cloudflared tunnel route dns raa-screen your-domain.com
```

**5. Run the tunnel:**
```bash
cloudflared tunnel run --url http://localhost:8000 raa-screen
```

**6. Install as a systemd service (starts on boot):**
```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

After this, `https://your-domain.com` proxies to the FastAPI app with automatic HTTPS.

**Check tunnel status:**
```bash
sudo systemctl status cloudflared
cloudflared tunnel info raa-screen
```
