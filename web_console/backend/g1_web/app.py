import asyncio
import json
import secrets
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, UUID4

from .adapters.mock import MockAdapter
from .adapters.ros_readonly import RosReadOnlyAdapter
from .adapters.local import LocalAdapter
from .config import Settings
from .control import CommandCache, ControlLease, GatewayError
from .workspace import WorkspaceData


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Payload):
    token: str = Field(max_length=1024)


class LeaseRequest(Payload):
    owner: str = Field(min_length=1, max_length=40, pattern=r".*\S.*")


class Command(Payload):
    request_id: UUID4


class MissionStart(Command):
    mission_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")


class MissionContinue(Command):
    run_id: str = Field(min_length=1, max_length=128)
    wait_id: str = Field(min_length=1, max_length=128)


class MissionCancel(Command):
    run_id: str = Field(min_length=1, max_length=128)


class Operation(Command):
    operation: Literal["mapping.start", "mapping.save", "mapping.finish", "navigation.start", "navigation.stop"]


class WaypointEdit(Payload):
    name: str = Field(min_length=1, max_length=160, pattern=r".*\S.*")
    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)
    yaw: float = Field(strict=True, allow_inf_nan=False)


class WaypointCreate(WaypointEdit):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")


class MissionEdit(Payload):
    name: str = Field(min_length=1, max_length=160, pattern=r".*\S.*")
    steps: list[dict] = Field(min_length=1, max_length=1000)


class MissionCreate(MissionEdit):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")


def create_app(settings=None, adapter=None):
    settings = settings or Settings.from_env()
    robot = adapter or (MockAdapter(settings) if settings.mode == "mock" else LocalAdapter() if settings.mode == "local" else RosReadOnlyAdapter())
    workspace = None if settings.mode == "mock" else WorkspaceData(settings)
    lease, cache, command_lock = ControlLease(settings.lease_seconds), CommandCache(), asyncio.Lock()
    sessions = OrderedDict()
    instance_id = uuid.uuid4().hex
    sequence = 0

    @asynccontextmanager
    async def lifespan(app):
        try:
            await robot.start()
            yield
        finally:
            await robot.close()

    app = FastAPI(title="G1 Web Gateway · 框架", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.robot, app.state.lease = robot, lease
    app.state.workspace = workspace

    @app.exception_handler(GatewayError)
    async def gateway_error(request, exc):
        return JSONResponse(status_code=exc.status,
                            content={"error": {"code": exc.code, "message": exc.message}})

    def same_origin(connection):
        origin = connection.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != connection.headers.get("host"):
                raise GatewayError(403, "ORIGIN_DENIED", "只接受同源网页请求")

    def authenticated(connection):
        if not settings.token:
            return True
        cookie = connection.cookies.get("g1_session", "")
        return sessions.get(cookie, 0.0) > time.monotonic()

    async def auth(request: Request):
        if request.method not in {"GET", "HEAD"}:
            same_origin(request)
        if not authenticated(request):
            raise GatewayError(401, "AUTH_REQUIRED", "请输入访问口令")

    async def state():
        nonlocal sequence
        data = await robot.snapshot()
        if workspace:
            configuration, map_data = await asyncio.to_thread(workspace.status)
            data["configuration"], data["map"] = configuration, map_data
            data["capabilities"].update(waypoint_write=configuration["available"], mission_write=configuration["available"])
        sequence += 1
        return {"type": "state", "schema_version": 1, "instance_id": instance_id,
                "sequence": sequence, "server_time": time.time(),
                "data": dict(data, mode=settings.mode, control=lease.snapshot())}

    @app.get("/api/v1/health")
    async def health():
        return {"ok": True, "mode": settings.mode, "schema_version": 1}

    @app.get("/api/v1/session")
    async def session(request: Request):
        return {"authenticated": authenticated(request), "auth_required": bool(settings.token)}

    @app.post("/api/v1/session")
    async def login(payload: Login, request: Request):
        same_origin(request)
        if not secrets.compare_digest(payload.token.encode("utf-8"), settings.token.encode("utf-8")):
            raise GatewayError(401, "INVALID_TOKEN", "访问口令不正确")
        now = time.monotonic()
        for key in list(sessions):
            if sessions[key] <= now:
                sessions.pop(key)
        key = secrets.token_urlsafe(32)
        sessions[key] = now + 12 * 3600
        while len(sessions) > 128:
            sessions.popitem(last=False)
        response = JSONResponse({"authenticated": True})
        response.set_cookie("g1_session", key, httponly=True, samesite="strict",
                            secure=settings.cookie_secure, max_age=12 * 3600)
        return response

    @app.delete("/api/v1/session", dependencies=[Depends(auth)])
    async def logout(request: Request):
        sessions.pop(request.cookies.get("g1_session", ""), None)
        response = JSONResponse({"authenticated": False})
        response.delete_cookie("g1_session")
        return response

    @app.get("/api/v1/state", dependencies=[Depends(auth)])
    async def get_state():
        return await state()

    @app.get("/api/v1/catalog", dependencies=[Depends(auth)])
    async def catalog():
        if workspace:
            result = await asyncio.to_thread(workspace.catalog)
            return JSONResponse(jsonable_encoder(result), headers={"ETag": '"' + result["revision"] + '"', "Cache-Control": "no-cache"})
        return await robot.catalog()

    @app.get("/api/v1/map", dependencies=[Depends(auth)])
    async def map_metadata():
        if not workspace:
            raise GatewayError(501, "DEMO_MAP", "模拟模式没有现场地图资源")
        return await asyncio.to_thread(workspace.map)

    @app.get("/api/v1/map/image", dependencies=[Depends(auth)])
    async def map_image(version: str = "", if_none_match: str = Header(default="")):
        if not workspace:
            raise GatewayError(501, "DEMO_MAP", "模拟模式没有现场地图资源")
        content, revision = await asyncio.to_thread(workspace.map_image, version)
        etag = '"' + revision + '"'
        headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
        return Response(status_code=304, headers=headers) if if_none_match == etag else Response(content, media_type="image/png", headers=headers)

    @app.get("/api/v1/openapi.json", dependencies=[Depends(auth)])
    async def schema():
        return app.openapi()

    @app.post("/api/v1/control/acquire", dependencies=[Depends(auth)])
    async def acquire(payload: LeaseRequest):
        return lease.acquire(payload.owner)

    @app.post("/api/v1/control/renew", dependencies=[Depends(auth)])
    async def renew(x_control_lease: str = Header(default="")):
        return lease.renew(x_control_lease)

    @app.post("/api/v1/control/release", dependencies=[Depends(auth)])
    async def release(x_control_lease: str = Header(default="")):
        lease.release(x_control_lease)
        return {"released": True}

    async def command(name, payload, secret, action):
        async with command_lock:
            if settings.mode != "mock":
                robot.unsupported()
            lease.require(secret)
            fingerprint = name + json.dumps(payload.model_dump(mode="json"), sort_keys=True)
            previous = cache.get(secret, str(payload.request_id), fingerprint)
            if previous is not None:
                return previous
            detail = await action()
            result = dict(detail, accepted=True, simulated=True, request_id=str(payload.request_id),
                          operation_id=uuid.uuid4().hex)
            cache.put(secret, str(payload.request_id), fingerprint, result)
            return result

    @app.post("/api/v1/missions/start", status_code=202, dependencies=[Depends(auth)])
    async def start(payload: MissionStart, x_control_lease: str = Header(default="")):
        return await command("start", payload, x_control_lease, lambda: robot.start_mission(payload.mission_id))

    @app.post("/api/v1/missions/continue", status_code=202, dependencies=[Depends(auth)])
    async def next_station(payload: MissionContinue, x_control_lease: str = Header(default="")):
        return await command("continue", payload, x_control_lease,
                             lambda: robot.continue_mission(payload.run_id, payload.wait_id))

    @app.post("/api/v1/missions/cancel", status_code=202, dependencies=[Depends(auth)])
    async def cancel(payload: MissionCancel, x_control_lease: str = Header(default="")):
        return await command("cancel", payload, x_control_lease, lambda: robot.cancel_mission(payload.run_id))

    async def save_configuration(kind, operation, identifier, payload, secret, revision):
        if not workspace:
            raise GatewayError(501, "DEMO_DATA", "模拟目录不可写，请使用默认 local 模式编辑本地数据")
        async with command_lock:
            lease.require(secret)
            mission = (await robot.snapshot())["mission"]
            if mission["active"]:
                raise GatewayError(409, "MISSION_BUSY", "任务运行中，请结束后再修改配置")
            return await asyncio.to_thread(workspace.save, kind, operation, identifier, payload, revision)

    @app.post("/api/v1/waypoints", dependencies=[Depends(auth)])
    async def create_waypoint(payload: WaypointCreate, x_control_lease: str = Header(default=""), if_match: str = Header(default="")):
        return await save_configuration("waypoints", "create", payload.id, payload.model_dump(exclude={"id"}), x_control_lease, if_match)

    @app.put("/api/v1/waypoints/{waypoint_id}", dependencies=[Depends(auth)])
    async def update_waypoint(waypoint_id: str, payload: WaypointEdit, x_control_lease: str = Header(default=""), if_match: str = Header(default="")):
        return await save_configuration("waypoints", "update", waypoint_id, payload.model_dump(), x_control_lease, if_match)

    @app.delete("/api/v1/waypoints/{waypoint_id}", dependencies=[Depends(auth)])
    async def delete_waypoint(waypoint_id: str, x_control_lease: str = Header(default=""), if_match: str = Header(default="")):
        return await save_configuration("waypoints", "delete", waypoint_id, None, x_control_lease, if_match)

    @app.post("/api/v1/missions", dependencies=[Depends(auth)])
    async def create_mission(payload: MissionCreate, x_control_lease: str = Header(default=""), if_match: str = Header(default="")):
        return await save_configuration("missions", "create", payload.id, payload.model_dump(exclude={"id"}), x_control_lease, if_match)

    @app.put("/api/v1/missions/{mission_id}", dependencies=[Depends(auth)])
    async def update_mission(mission_id: str, payload: MissionEdit, x_control_lease: str = Header(default=""), if_match: str = Header(default="")):
        return await save_configuration("missions", "update", mission_id, payload.model_dump(), x_control_lease, if_match)

    @app.delete("/api/v1/missions/{mission_id}", dependencies=[Depends(auth)])
    async def delete_mission(mission_id: str, x_control_lease: str = Header(default=""), if_match: str = Header(default="")):
        return await save_configuration("missions", "delete", mission_id, None, x_control_lease, if_match)

    @app.post("/api/v1/operations", dependencies=[Depends(auth)])
    async def operations(payload: Operation):
        raise GatewayError(501, "NOT_IMPLEMENTED", "进程控制尚未接入；未执行任何脚本")

    @app.websocket("/ws/state")
    async def stream(websocket: WebSocket):
        try:
            same_origin(websocket)
        except GatewayError:
            await websocket.close(code=4403)
            return
        if not authenticated(websocket):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            while authenticated(websocket):
                await asyncio.wait_for(websocket.send_json(await state()), timeout=2.0)
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
            await websocket.close(code=4401)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")
    return app
