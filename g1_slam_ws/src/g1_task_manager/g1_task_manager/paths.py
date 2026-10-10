"""Locate workspace data from a source checkout or a colcon installation."""

import os
from pathlib import Path


def workspace():
    explicit = os.environ.get("G1_WS") or os.environ.get("WS")
    if explicit:
        return Path(explicit).expanduser().resolve()

    for start in (Path(__file__).resolve(), Path.cwd()):
        for candidate in (start, *start.parents):
            if (candidate / "src").is_dir() and (candidate / "task_data").is_dir():
                return candidate
            nested = candidate / "g1_slam_ws"
            if (nested / "src").is_dir() and (nested / "task_data").is_dir():
                return nested

    raise RuntimeError("无法找到 G1 工作空间，请设置 G1_WS 指向 g1_slam_ws")


def get_default_waypoints_file():
    explicit = os.environ.get("G1_WAYPOINTS_FILE")
    if explicit:
        return Path(explicit).expanduser()
    return workspace() / "task_data/maps/laboratory_map_v1/waypoints.yaml"


def default_missions_file():
    explicit = os.environ.get("G1_MISSIONS_FILE")
    if explicit:
        return str(Path(explicit).expanduser())
    return str(workspace() / "task_data/missions/missions.yaml")
