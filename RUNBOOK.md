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
