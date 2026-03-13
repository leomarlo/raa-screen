#!/usr/bin/env python3
"""
Raa Screen Agent
Polls the resource API and displays the current resource fullscreen:
  - direct / hls / youtube  → VLC
  - image                   → feh
  - web                     → Chromium kiosk
Automatically restarts the player if the resource changes or the player crashes.
"""
import os
import signal
import subprocess
import time
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.environ.get("API_URL", "").strip()
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "15"))
DISPLAY = os.environ.get("DISPLAY", ":0")
XAUTHORITY = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
NETWORK_CACHING_MS = int(os.environ.get("NETWORK_CACHING_MS", "2000"))

_stop = False


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


def main():
    current_url: Optional[str] = None
    current_kind: Optional[str] = None
    player_proc: Optional[subprocess.Popen] = None

    print(f"[agent] starting — polling {API_URL} every {POLL_SECONDS}s", flush=True)

    while not _stop:
        try:
            url, kind = fetch_resource()
            if url and (url != current_url or kind != current_kind):
                print(f"[agent] resource changed → [{kind}] {url}", flush=True)
                stop_player(player_proc)
                time.sleep(1)
                player_proc = start_player(url, kind)
                current_url = url
                current_kind = kind
        except Exception as e:
            print(f"[agent] fetch error: {e}", flush=True)

        # Restart player if it crashed
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
