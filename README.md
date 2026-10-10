# G1 SLAM 本机运行

本项目已适配当前电脑：Ubuntu 22.04、x86_64、ROS 2 Humble。包含 MID360 驱动、FAST-LIO 建图、NDT 重定位、Nav2、G1 速度桥及导航点/巡航工具。

在项目根目录执行下面的命令。

## 配置与编译

本机配置位于 `g1_slam_ws/script/local.env`：

| 配置 | 当前值 |
| --- | --- |
| G1_NETWORK_INTERFACE | enp4s0 |
| G1_HOST_IP | 192.168.123.99 |
| G1_LIDAR_IP | 192.168.123.120 |
| ROS_DOMAIN_ID | 0 |
| RMW_IMPLEMENTATION | rmw_cyclonedds_cpp |

雷达和 G1 接入同一有线网络。脚本会检查主机 IP 是否属于选定网卡，并生成 `runtime/livox/MID360_config.json`；不会修改电脑网卡。换电脑、换网卡或换雷达时修改 `local.env`，也可以在运行前 `export` 同名变量覆盖。

```bash
./g1_slam_ws/script/g1_build.sh
./g1_slam_ws/script/g1_check.sh
```

已保留本机编译的 `install`，可直接运行；旧构建、备份和历史日志已清理。需要重新编译时运行 `g1_build.sh`。Livox SDK、Unitree 消息和业务包全部从项目源码编译。默认顺序构建、两个编译线程，可用 `G1_BUILD_JOBS=1` 减少内存占用。

当前电脑已安装依赖。若在新的 Ubuntu 22.04 电脑部署，先安装 ROS 2 Humble，再安装依赖：

```bash
sudo apt install python3-colcon-common-extensions python3-rosdep \
  python3-yaml python3-numpy python3-scipy python3-matplotlib python3-dev \
  libpcl-dev libeigen3-dev ros-humble-pcl-ros ros-humble-pcl-conversions \
  ros-humble-navigation2 ros-humble-nav2-bringup \
  ros-humble-rmw-cyclonedds-cpp ros-humble-rviz2
```

`unitree_ros2` 仅保留本机环境加载脚本；原来的 Foxy 中间件和示例工作空间已移除。

## 建图

```bash
./g1_slam_ws/script/g1_mapping.sh start
./g1_slam_ws/script/g1_mapping.sh save
./g1_slam_ws/script/g1_mapping.sh finish
```

启动后用遥控器采集环境。默认 PCD 输出为 `g1_slam_ws/maps/map_时间戳.pcd`，`map-path` 可查询路径；`finish` 保存后停止。可指定输出：

```bash
G1_MAPPING_OUTPUT="$(pwd)/g1_slam_ws/maps/new_map.pcd" \
  ./g1_slam_ws/script/g1_mapping.sh start
```

二维地图转换工具及参数说明：

```bash
python3 g1_slam_ws/maps/pcd2pgm_multilayer.py --help
```

导航需要同一区域对应的 PCD、PGM 和地图 YAML。当前项目保留原有 `map.pcd` / `map_multilayer.pgm` / `map_multilayer.yaml`。使用新地图时以 `G1_MAP_PCD`、`G1_MAP_PGM`、`G1_MAP_YAML` 指定对应文件。

## 定位与导航

先结束建图，然后启动定位和 Nav2：

```bash
./g1_slam_ws/script/g1_navigation.sh start
```

在 RViz 点击 **2D Pose Estimate**，指定实际位置和朝向。NDT 定位成功后脚本继续启动 Nav2。若初始化等待超时，完成定位后运行 `g1_navigation.sh continue`。

连接真机速度桥：

```bash
./g1_slam_ws/script/g1_navigation_real.sh start
./g1_slam_ws/script/g1_navigation_real.sh enable
```

`start` 启动桥时安全门保持关闭；`enable` 才允许 `/cmd_vel_nav` 控制 G1。机器人运动模式由操作者用原有方式切换。关闭控制或结束导航：

```bash
./g1_slam_ws/script/g1_navigation_real.sh disable
./g1_slam_ws/script/g1_navigation_real.sh stop
./g1_slam_ws/script/g1_navigation.sh stop
```

只验证规划与速度桥时，用 `g1_navigation.sh start-dry`；该入口仍需要真实雷达定位。无显示器时设置 `G1_ENABLE_RVIZ=0`，并从其他终端发布初始位姿，或配置 `script/auto_start_pose.env` 后使用 `start-auto`。

## 诊断和其他工具

```bash
# 本地依赖检查；离线模式跳过网卡检查
./g1_slam_ws/script/g1_check.sh --offline
# 加载本项目 Humble + CycloneDDS 环境，供手动 ROS 命令使用
source unitree_ros2/setup.sh
# 只读查询机器人状态
ros2 run g1_unitree_ros2_probe g1_unitree_ros2_status_probe
# 运行状态与日志
./g1_slam_ws/script/g1_mapping.sh status
./g1_slam_ws/script/g1_navigation.sh status
./g1_slam_ws/script/g1_navigation.sh logs
# 离线导航点与巡航预览
./g1_slam_ws/script/g1_waypoints.sh --help
./g1_slam_ws/script/g1_cruise.sh --help
```

运行时会自动创建 `runtime` 目录，建图与导航日志分别写入 `runtime/mapping/logs` 和 `runtime/navigation/logs`，ROS 日志写入 `runtime/ros_logs`。历史日志和临时验收产物不保留。

本机适配保留原项目倒装 MID360 的 `body_roll_deg=180` 及 `body -> nav_base` 变换。若雷达安装方向变化，需要同步调整 FAST-LIO 外参和重定位/导航坐标变换。
