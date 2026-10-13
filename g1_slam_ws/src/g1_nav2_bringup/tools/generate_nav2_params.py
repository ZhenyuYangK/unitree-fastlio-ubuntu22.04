#!/usr/bin/env python3
import copy
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "缺少 Python yaml 模块。请安装 python3-yaml 并加载 ROS 2 Humble 环境。"
    ) from exc


def node_params(data, node_name):
    return data.setdefault(node_name, {}).setdefault("ros__parameters", {})


def costmap_params(data, name):
    return (
        data.setdefault(name, {})
        .setdefault(name, {})
        .setdefault("ros__parameters", {})
    )


def plugin_name(config, key, fallback):
    value = config.get(key, {})
    if isinstance(value, dict) and value.get("plugin"):
        return value["plugin"]
    return fallback


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "用法: generate_nav2_params.py DEFAULT_YAML OUTPUT_YAML"
        )

    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()

    if not source.is_file():
        raise SystemExit(f"找不到 Nav2 默认参数文件: {source}")

    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Nav2 默认参数文件格式不正确")

    controller = node_params(data, "controller_server")
    controller["use_sim_time"] = False
    controller["odom_topic"] = "/Odometry"
    controller["controller_frequency"] = 10.0
    controller["min_x_velocity_threshold"] = 0.001
    controller["min_y_velocity_threshold"] = 0.001
    controller["min_theta_velocity_threshold"] = 0.001
    controller["goal_checker_plugins"] = ["goal_checker"]
    controller.pop("goal_checker_plugin", None)
    controller["goal_checker"] = {
        "plugin": "nav2_controller::SimpleGoalChecker",
        "xy_goal_tolerance": 0.25,
        "yaw_goal_tolerance": 0.25,
        "stateful": True,
    }

    follow_path = controller.setdefault("FollowPath", {})
    follow_path.setdefault("plugin", "dwb_core::DWBLocalPlanner")
    follow_path.update({
        "debug_trajectory_details": True,
        "min_vel_x": 0.0,
        "min_vel_y": 0.0,
        "max_vel_x": 1.0,
        "max_vel_y": 0.0,
        "max_vel_theta": 0.40,
        "min_speed_xy": 0.0,
        "max_speed_xy": 1.0,
        "min_speed_theta": 0.0,
        "acc_lim_x": 0.20,
        "acc_lim_y": 0.0,
        "acc_lim_theta": 4.0,
        "decel_lim_x": -0.30,
        "decel_lim_y": 0.0,
        "decel_lim_theta": -4.0,
        "vx_samples": 5,
        "vy_samples": 1,
        "vtheta_samples": 9,
        "sim_time": 1.5,
        "linear_granularity": 0.05,
        "angular_granularity": 0.025,
        "transform_tolerance": 0.5,
        "xy_goal_tolerance": 0.25,
        "trans_stopped_velocity": 0.05,
        "short_circuit_trajectory_evaluation": True,
        "stateful": True,
        "critics": [
            "RotateToGoal",
            "Oscillation",
            "BaseObstacle",
            "GoalAlign",
            "PathAlign",
            "PathDist",
            "GoalDist",
        ],
        "BaseObstacle.scale": 0.02,
        "PathAlign.scale": 24.0,
        "PathAlign.forward_point_distance": 0.1,
        "GoalAlign.scale": 20.0,
        "GoalAlign.forward_point_distance": 0.1,
        "PathDist.scale": 24.0,
        "GoalDist.scale": 20.0,
        "RotateToGoal.scale": 20.0,
        "RotateToGoal.slowing_factor": 5.0,
        "RotateToGoal.lookahead_time": -1.0,
    })

    planner = node_params(data, "planner_server")
    planner["use_sim_time"] = False
    planner.setdefault("expected_planner_frequency", 2.0)

    bt = node_params(data, "bt_navigator")
    bt["use_sim_time"] = False
    bt["global_frame"] = "map"
    bt["robot_base_frame"] = "nav_base"
    bt["odom_topic"] = "/Odometry"
    # The launch file resolves the G1 tree from the installed package share.
    bt.pop("default_bt_xml_filename", None)
    bt["default_nav_to_pose_bt_xml"] = ""

    data.pop("recoveries_server", None)
    behavior = node_params(data, "behavior_server")
    behavior.update({
        "use_sim_time": False,
        "global_frame": "camera_init",
        "robot_base_frame": "nav_base",
        "transform_tolerance": 0.5,
        "max_rotational_vel": 0.35,
        "min_rotational_vel": 0.10,
        "rotational_acc_lim": 0.50,
        "behavior_plugins": ["spin", "backup", "wait"],
        "spin": {"plugin": "nav2_behaviors/Spin"},
        "backup": {"plugin": "nav2_behaviors/BackUp"},
        "wait": {"plugin": "nav2_behaviors/Wait"},
    })

    local = costmap_params(data, "local_costmap")
    local_plugin_source = copy.deepcopy(local)

    global_costmap = costmap_params(data, "global_costmap")
    global_plugin_source = copy.deepcopy(global_costmap)

    obstacle_plugin = plugin_name(
        global_plugin_source,
        "obstacle_layer",
        "nav2_costmap_2d::ObstacleLayer",
    )
    inflation_plugin = plugin_name(
        local_plugin_source,
        "inflation_layer",
        plugin_name(
            global_plugin_source,
            "inflation_layer",
            "nav2_costmap_2d::InflationLayer",
        ),
    )
    static_plugin = plugin_name(
        global_plugin_source,
        "static_layer",
        "nav2_costmap_2d::StaticLayer",
    )

    # Local rolling costmap: live PointCloud2 obstacle marking.
    local.update({
        "use_sim_time": False,
        "update_frequency": 5.0,
        "publish_frequency": 2.0,
        "global_frame": "camera_init",
        "robot_base_frame": "nav_base",
        "rolling_window": True,
        "width": 6,
        "height": 6,
        "resolution": 0.10,
        "robot_radius": 0.35,
        "transform_tolerance": 0.5,
        "plugins": ["obstacle_layer", "inflation_layer"],
        "obstacle_layer": {
            "plugin": obstacle_plugin,
            "enabled": True,
            "observation_sources": "cloud",
            "cloud": {
                "topic": "/cloud_registered_body",
                "data_type": "PointCloud2",
                "clearing": True,
                "marking": True,
                "min_obstacle_height": -0.8,
                "max_obstacle_height": 0.8,
            },
        },
        "inflation_layer": {
            "plugin": inflation_plugin,
            "cost_scaling_factor": 3.0,
            "inflation_radius": 0.65,
        },
    })
    local.pop("footprint", None)

    # Global costmap: static PGM map only for the first safety test.
    global_costmap.update({
        "use_sim_time": False,
        "update_frequency": 1.0,
        "publish_frequency": 1.0,
        "global_frame": "map",
        "robot_base_frame": "nav_base",
        "resolution": 0.05,
        "track_unknown_space": True,
        "robot_radius": 0.35,
        "transform_tolerance": 0.5,
        "plugins": ["static_layer", "inflation_layer"],
        "static_layer": {
            "plugin": static_plugin,
            "map_subscribe_transient_local": True,
        },
        "inflation_layer": {
            "plugin": inflation_plugin,
            "cost_scaling_factor": 3.0,
            "inflation_radius": 0.65,
        },
    })
    global_costmap.pop("footprint", None)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )

    print(f"默认参数: {source}")
    print(f"已生成:   {output}")
    print("Nav2 frames: map -> camera_init -> body -> nav_base")
    print("Nav2 output: /cmd_vel_nav（未连接机器人）")


if __name__ == "__main__":
    main()
