import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_path = get_package_share_directory("g1_nav2_bringup")
    default_params_file = os.path.join(
        package_path,
        "config",
        "nav2_params.yaml",
    )

    params_file = LaunchConfiguration("params_file")
    use_sim_time = LaunchConfiguration("use_sim_time")
    bt_xml = LaunchConfiguration("bt_xml")
    # Share the same quaternion between TF and velocity conversion.
    body_to_nav_rotation_xyzw = [1.0, 0.0, 0.0, 0.0]

    nav2_nodes = [
        "controller_server",
        "planner_server",
        "behavior_server",
        "bt_navigator",
    ]

    return LaunchDescription([
        DeclareLaunchArgument(
            "params_file",
            default_value=default_params_file,
            description="Full path to the Nav2 parameters file",
        ),

        DeclareLaunchArgument(
            "bt_xml",
            default_value=os.path.join(
                package_path, "behavior_trees", "navigate_g1_timeout.xml"),
            description="NavigateToPose behavior tree XML file",
        ),

        DeclareLaunchArgument(
            "use_sim_time",
            default_value="false",
            description="Use simulation clock",
        ),

        # FAST-LIO body frame follows the upside-down MID360 mounting.
        # This fixed transform creates a planar navigation frame whose Z axis points up.
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="body_to_nav_base",
            output="screen",
            arguments=[
                "0", "0", "0",
                *[str(value) for value in body_to_nav_rotation_xyzw],
                "body", "nav_base",
            ],
        ),

        Node(
            package="g1_nav2_bringup",
            executable="navigation_odometry",
            name="navigation_odometry",
            output="screen",
            parameters=[{
                "use_sim_time": use_sim_time,
                "body_to_nav_rotation_xyzw": body_to_nav_rotation_xyzw,
            }],
        ),

        Node(
            package="nav2_controller",
            executable="controller_server",
            name="controller_server",
            output="screen",
            parameters=[params_file, {"use_sim_time": use_sim_time}],
            remappings=[("cmd_vel", "/cmd_vel_nav")],
        ),

        Node(
            package="nav2_planner",
            executable="planner_server",
            name="planner_server",
            output="screen",
            parameters=[params_file, {"use_sim_time": use_sim_time}],
        ),

        Node(
            package="nav2_behaviors",
            executable="behavior_server",
            name="behavior_server",
            output="screen",
            parameters=[params_file, {"use_sim_time": use_sim_time}],
            remappings=[("cmd_vel", "/cmd_vel_nav")],
        ),

        Node(
            package="nav2_bt_navigator",
            executable="bt_navigator",
            name="bt_navigator",
            output="screen",
            parameters=[params_file, {
                "use_sim_time": use_sim_time,
                "default_nav_to_pose_bt_xml": bt_xml,
            }],
        ),

        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_navigation",
            output="screen",
            parameters=[{
                "use_sim_time": use_sim_time,
                "autostart": True,
                "node_names": nav2_nodes,
            }],
        ),
    ])
