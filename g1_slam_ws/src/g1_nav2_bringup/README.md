# g1_nav2_bringup

Planning-only Nav2 bringup for the G1 FAST-LIO project on ROS 2 Humble.

- global frame: `map`
- odom frame: `camera_init`
- FAST-LIO frame: `body`
- navigation base: `nav_base` (static 180-degree X correction from `body`)
- raw FAST-LIO odometry: `/Odometry` (twist in `body`)
- navigation odometry: `/Odometry_nav` (twist in `nav_base`)
- local obstacle source: `/cloud_registered_body`
- isolated velocity output: `/cmd_vel_nav`

This package intentionally does not connect velocity output to Unitree SDK2.

The launch file also starts `navigation_odometry`. FAST-LIO publishes its estimated
world velocity rotated into `body`, plus bias-corrected IMU angular velocity. The
adapter rotates pose, twist and twist covariance into the co-located `nav_base`
frame using the same quaternion as the static TF. It preserves the sensor timestamp
and parent frame, and publishes only when new odometry arrives. Both the controller
and BT navigator consume `/Odometry_nav`; the raw topic and existing TF stay available
to localization. The adapter assumes zero translation between `body` and `nav_base`.
If the mounting transform changes, update both the TF and conversion together.

The 1.0 m/s setting is a maximum. With missing velocity feedback, DWB would repeatedly
sample from rest and only reach `0.2 m/s² * 1.5 s = 0.3 m/s`. Correct measured feedback
lets it sample higher speeds as the robot accelerates; obstacles, curvature and
stopping distance still determine the selected command.

After building and sourcing the workspace, start it with:

```bash
ros2 launch g1_nav2_bringup planning_only.launch.py
```

The launch file starts Humble's `nav2_behaviors/behavior_server` and resolves
`navigate_g1_timeout.xml` from this package's installed `behavior_trees` directory.
Use `params_file:=/path/to/nav2_params.yaml` or `bt_xml:=/path/to/tree.xml` to override
the defaults. The map server, FAST-LIO and relocalization are started by
`g1_slam_ws/script/g1_navigation.sh`; this launch file requires their map and TF data.
