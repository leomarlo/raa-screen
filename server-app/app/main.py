import os
import json
import uuid
import pathlib
from typing import Literal, Optional, Dict, Any, List
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "raa-screen-server")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
RESOURCE_FILE = os.getenv("RESOURCE_FILE", "/data/resources.json")

app = FastAPI(title=APP_NAME, version="2.0.0")

_ADMIN_HTML = (pathlib.Path(__file__).parent / "admin.html").read_text()

MediaKind = Literal["direct", "hls", "youtube", "image", "web"]

_DEFAULT_RESOURCE = {
    "id": "__default__",
    "kind": "direct",
    "url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "mime_type": "video/mp4",
    "title": "Big Buck Bunny (default)",
    "description": "Built-in fallback resource. Add your own via the admin dashboard and activate it.",
    "meta": {"note": "Default resource. Add your own via the admin dashboard."},
}


class MediaResource(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: MediaKind = Field(..., examples=["direct"])
    url: str = Field(..., description="URL to the resource")
    mime_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    poster_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    start_seconds: Optional[float] = Field(None, ge=0)
    meta: Optional[Dict[str, Any]] = None


class AddResourceRequest(BaseModel):
    kind: MediaKind = Field(..., examples=["direct"])
    url: str
    mime_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    poster_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    start_seconds: Optional[float] = Field(None, ge=0)
    meta: Optional[Dict[str, Any]] = None


def _ensure_data_dir():
    data_dir = os.path.dirname(RESOURCE_FILE)
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)


def load_store() -> dict:
    """Load store, migrating old single-resource format if needed."""
    try:
        with open(RESOURCE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "resources" not in data:
            # Migrate old format
            rid = str(uuid.uuid4())
            resource = {**data, "id": rid}
            resource.pop("resource", None)  # old SetResourceRequest wrapper
            return {"resources": [resource], "active_id": rid}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"resources": [], "active_id": None}


def save_store(store: dict) -> None:
    _ensure_data_dir()
    tmp = RESOURCE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RESOURCE_FILE)


def require_admin(x_admin_password: Optional[str]):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD is not configured")
    if not x_admin_password or x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Public ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME}


@app.get("/resource", response_model=MediaResource)
def get_active_resource():
    """Returns the active resource. Used by the Pi client."""
    store = load_store()
    active_id = store.get("active_id")
    if active_id:
        for r in store.get("resources", []):
            if r.get("id") == active_id:
                return MediaResource(**r)
    return MediaResource(**_DEFAULT_RESOURCE)


@app.get("/resources")
def list_resources_public():
    """Returns all resources and the active_id. Public, read-only."""
    store = load_store()
    active_id = store.get("active_id")
    resources = store.get("resources", [])
    if not resources:
        resources = [_DEFAULT_RESOURCE]
        active_id = _DEFAULT_RESOURCE["id"]
    return {"resources": resources, "active_id": active_id}


# ── Admin dashboard ───────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard():
    return HTMLResponse(content=_ADMIN_HTML)


# ── Admin API ─────────────────────────────────────────────────────────────────

@app.get("/admin/resources")
def list_resources(
    x_admin_password: Optional[str] = Header(default=None, convert_underscores=True),
):
    require_admin(x_admin_password)
    store = load_store()
    active_id = store.get("active_id")
    resources = [
        {**r, "is_active": r.get("id") == active_id}
        for r in store.get("resources", [])
    ]
    # When nothing is active, surface the built-in default so the list is never empty
    if not active_id:
        resources = [{**_DEFAULT_RESOURCE, "is_active": True, "is_default": True}] + resources
    return {"resources": resources, "active_id": active_id}


@app.delete("/admin/resources", status_code=204)
def reset_resources(
    x_admin_password: Optional[str] = Header(default=None, convert_underscores=True),
):
    """Clear all resources and revert to the built-in default."""
    require_admin(x_admin_password)
    save_store({"resources": [], "active_id": None})


@app.post("/admin/resources", response_model=MediaResource, status_code=201)
def add_resource(
    req: AddResourceRequest,
    activate: bool = Query(False, description="Also set this resource as active"),
    x_admin_password: Optional[str] = Header(default=None, convert_underscores=True),
):
    require_admin(x_admin_password)
    store = load_store()
    resource = MediaResource(**req.model_dump())
    resource_dict = resource.model_dump()
    store["resources"].append(resource_dict)
    if activate:
        store["active_id"] = resource_dict["id"]
    save_store(store)
    return resource


@app.post("/admin/resources/{resource_id}/activate", response_model=MediaResource)
def activate_resource(
    resource_id: str,
    x_admin_password: Optional[str] = Header(default=None, convert_underscores=True),
):
    require_admin(x_admin_password)
    store = load_store()
    for r in store.get("resources", []):
        if r.get("id") == resource_id:
            store["active_id"] = resource_id
            save_store(store)
            return MediaResource(**r)
    raise HTTPException(status_code=404, detail="Resource not found")


@app.delete("/admin/resources/{resource_id}", status_code=204)
def remove_resource(
    resource_id: str,
    x_admin_password: Optional[str] = Header(default=None, convert_underscores=True),
):
    require_admin(x_admin_password)
    store = load_store()
    if store.get("active_id") == resource_id:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the active resource. Activate another one first.",
        )
    before = len(store.get("resources", []))
    store["resources"] = [r for r in store.get("resources", []) if r.get("id") != resource_id]
    if len(store["resources"]) == before:
        raise HTTPException(status_code=404, detail="Resource not found")
    save_store(store)
