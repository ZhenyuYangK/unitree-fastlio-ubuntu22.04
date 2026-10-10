# g1_nav2_bringup

Planning-only Nav2 bringup for the G1 FAST-LIO project on ROS 2 Humble.

- global frame: `map`
- odom frame: `camera_init`
- FAST-LIO frame: `body`
- navigation base: `nav_base` (static 180-degree X correction from `body`)
- odometry topic: `/Odometry`
- local obstacle source: `/cloud_registered_body`
- isolated velocity output: `/cmd_vel_nav`

This package intentionally does not connect velocity output to Unitree SDK2.

After building and sourcing the workspace, start it with:

```bash
ros2 launch g1_nav2_bringup planning_only.launch.py
```

The launch file starts Humble's `nav2_behaviors/behavior_server` and resolves
`navigate_g1_timeout.xml` from this package's installed `behavior_trees` directory.
Use `params_file:=/path/to/nav2_params.yaml` or `bt_xml:=/path/to/tree.xml` to override
the defaults. The map server, FAST-LIO and relocalization are started by
`g1_slam_ws/script/g1_navigation.sh`; this launch file requires their map and TF data.
