import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def default_map_path(package_path):
    workspace = os.environ.get("G1_WS") or os.environ.get("WS")
    if workspace:
        return str(Path(workspace).expanduser() / "maps/map.pcd")
    for candidate in Path(package_path).resolve().parents:
        if (candidate / "src").is_dir() and (candidate / "maps").is_dir():
            return str(candidate / "maps/map.pcd")
    raise RuntimeError("无法找到地图目录，请设置 G1_WS 指向 g1_slam_ws")


def generate_launch_description():
    package_path = get_package_share_directory("g1_relocalization")
    config_file = os.path.join(
        package_path,
        "config",
        "relocalization.yaml",
    )

    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=config_file),
        DeclareLaunchArgument(
            "initialization_mode", default_value="manual",
            description="manual waits for initialpose; global searches without a position prior",
        ),
        DeclareLaunchArgument(
            "map_path", default_value=default_map_path(package_path),
            description="PCD map path",
        ),
        Node(
            package="g1_relocalization",
            executable="g1_relocalization_node",
            name="g1_relocalization",
            output="screen",
            parameters=[LaunchConfiguration("params_file"), {
                "map_path": LaunchConfiguration("map_path"),
                "initialization_mode": LaunchConfiguration("initialization_mode"),
            }],
        )
    ])
