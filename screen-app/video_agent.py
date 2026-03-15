#!/usr/bin/env python3
"""
Raa Screen Agent
Connects to the resource server via WebSocket for instant updates, with
polling as a fallback. Displays the active resource fullscreen:
  - youtube          → mpv (via yt-dlp)
  - direct / hls     → VLC
  - image            → feh
  - web              → Chromium kiosk
"""
import asyncio
import json
import os
import queue
import signal
import subprocess
import threading
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests
import websockets
from dotenv import load_dotenv

load_dotenv()

API_URL        = os.environ.get("API_URL", "").strip()
POLL_SECONDS   = int(os.environ.get("POLL_SECONDS", "15"))
DISPLAY        = os.environ.get("DISPLAY", ":0")
XAUTHORITY     = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
NETWORK_CACHING_MS = int(os.environ.get("NETWORK_CACHING_MS", "2000"))

# Derive WebSocket URL from API_URL (e.g. https://monitor.raa.space/resource → wss://monitor.raa.space/ws)
def _ws_url(api_url: str) -> str:
    parsed = urlparse(api_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/ws"

WS_URL = _ws_url(API_URL) if API_URL else ""

_stop = False
_ws_queue: queue.Queue = queue.Queue()


def handle_signal(signum, frame):
    global _stop
    _stop = True


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def base_env() -> dict:
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    env["XAUTHORITY"] = XAUTHORITY
    return env


def fetch_resource() -> Tuple[Optional[str], Optional[str]]:
    """Returns (url, kind) or (None, None) on failure."""
    if not API_URL:
        print("ERROR: API_URL is not set in .env", flush=True)
        return None, None
    r = requests.get(API_URL, timeout=10)
    r.raise_for_status()
    data = r.json()
    url = data.get("url", "").strip()
    kind = data.get("kind", "direct").strip()
    return (url, kind) if url else (None, None)


def start_player(url: str, kind: str) -> subprocess.Popen:
    env = base_env()

    if kind == "youtube":
        cmd = [
            "mpv",
            "--fullscreen",
            "--osd-level=0",
            url,
        ]
    elif kind in ("direct", "hls"):
        cmd = [
            "cvlc",
            "--vout", "x11",
            "--fullscreen",
            "--loop",
            "--no-osd",
            "--no-video-title-show",
            f"--network-caching={NETWORK_CACHING_MS}",
            url,
        ]
    elif kind == "image":
        cmd = [
            "feh",
            "--fullscreen",
            "--zoom", "fill",
            "--no-fehbg",
            url,
        ]
    elif kind == "web":
        cmd = [
            "chromium-browser",
            "--kiosk",
            "--noerrdialogs",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            "--no-first-run",
            url,
        ]
    else:
        print(f"[agent] unknown kind '{kind}', falling back to VLC", flush=True)
        cmd = ["cvlc", "--vout", "x11", "--fullscreen", "--loop", url]

    print(f"[agent] starting {kind} player: {url}", flush=True)
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_player(proc: Optional[subprocess.Popen]) -> None:
    for name in ("cvlc", "vlc", "mpv", "feh", "chromium"):
        subprocess.run(["pkill", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# ── WebSocket listener (runs in a background thread) ──────────────────────────

async def _ws_listen():
    while not _stop:
        try:
            async with websockets.connect(WS_URL, ping_interval=30) as ws:
                print(f"[ws] connected to {WS_URL}", flush=True)
                async for message in ws:
                    if _stop:
                        break
                    try:
                        data = json.loads(message)
                        url = data.get("url", "").strip()
                        kind = data.get("kind", "direct").strip()
                        if url:
                            _ws_queue.put((url, kind))
                            print(f"[ws] push received → [{kind}] {url}", flush=True)
                    except Exception as e:
                        print(f"[ws] bad message: {e}", flush=True)
        except Exception as e:
            if _stop:
                break
            print(f"[ws] disconnected ({e}), retrying in 5s", flush=True)
            await asyncio.sleep(5)


def _start_ws_thread():
    if not WS_URL:
        print("[ws] no API_URL set, WebSocket disabled", flush=True)
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_ws_listen())


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    current_url:  Optional[str] = None
    current_kind: Optional[str] = None
    player_proc:  Optional[subprocess.Popen] = None

    # Start WebSocket listener in background
    ws_thread = threading.Thread(target=_start_ws_thread, daemon=True)
    ws_thread.start()

    print(f"[agent] starting — polling {API_URL} every {POLL_SECONDS}s, WS {WS_URL}", flush=True)

    while not _stop:
        # 1. Check for instant WebSocket push
        try:
            url, kind = _ws_queue.get_nowait()
            if url != current_url or kind != current_kind:
                stop_player(player_proc)
                time.sleep(1)
                player_proc = start_player(url, kind)
                current_url = url
                current_kind = kind
        except queue.Empty:
            pass

        # 2. Fallback poll
        try:
            url, kind = fetch_resource()
            if url and (url != current_url or kind != current_kind):
                print(f"[agent] poll: resource changed → [{kind}] {url}", flush=True)
                stop_player(player_proc)
                time.sleep(1)
                player_proc = start_player(url, kind)
                current_url = url
                current_kind = kind
        except Exception as e:
            print(f"[agent] fetch error: {e}", flush=True)

        # 3. Restart player if it crashed
        if current_url and player_proc and player_proc.poll() is not None:
            print("[agent] player exited unexpectedly, restarting...", flush=True)
            try:
                player_proc = start_player(current_url, current_kind)
            except Exception as e:
                print(f"[agent] restart error: {e}", flush=True)

        time.sleep(POLL_SECONDS)

    print("[agent] shutting down", flush=True)
    stop_player(player_proc)


if __name__ == "__main__":
    main()
