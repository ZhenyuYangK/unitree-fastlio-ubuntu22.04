# G1 SLAM 本机运行

本项目已适配当前电脑：Ubuntu 22.04、x86_64、ROS 2 Humble。包含 MID360 驱动、FAST-LIO 建图、自动全局定位和 NDT 跟踪、Nav2、G1 速度桥及导航点/巡航工具。

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

先结束建图，然后在项目根目录启动自动定位和 Nav2：

```bash
./g1_slam_ws/script/g1_navigation.sh start-auto
```

该入口不需要初始位置、朝向或 `auto_start_pose.env`。机器人保持静止后，系统采集点云，在三维地图中搜索候选位置和朝向，用 NDT 精配准、有界 ICP 修正及后续新扫描确认结果。只有 `/g1_relocalization/status` 报告有效且新鲜的 `LOCALIZED` 或 `TRACKING` 状态，脚本才启动 Nav2。默认等待 180 秒，可通过环境变量调整：

```bash
G1_LOCALIZATION_TIMEOUT_SEC=240 ./g1_slam_ws/script/g1_navigation.sh start-auto
```

搜索失败、匹配存在歧义或等待超时，脚本返回非零，保留雷达、FAST-LIO、重定位和地图节点，方便检查及人工后备。可在 RViz 点击 **2D Pose Estimate** 指定实际位置和朝向；定位状态有效后运行 `./g1_slam_ws/script/g1_navigation.sh continue`。重复走廊或相似房间可能需要人工后备。

保留以下入口：

| 命令 | 定位方式与用途 |
| --- | --- |
| `./g1_slam_ws/script/g1_navigation.sh start-auto` | 自动全局定位后启动 Nav2 规划 |
| `./g1_slam_ws/script/g1_navigation.sh start-auto-dry` | 自动全局定位后启动 Nav2 和 Dry Run 安全桥 |
| `./g1_slam_ws/script/g1_navigation.sh start` / `start-dry` | 人工 **2D Pose Estimate** 初始化 |
| `./g1_slam_ws/script/g1_navigation.sh start-fixed` / `start-fixed-dry` | 使用 `g1_slam_ws/script/auto_start_pose.env` 中的固定坐标 |
| `./g1_slam_ws/script/g1_navigation.sh continue` / `continue-dry` | 检查当前实时定位后继续启动 Nav2 |

`start-fixed` 是原 `start-auto` 固定坐标模式的新名称。使用它时需自行创建 `auto_start_pose.env`，填写 `AUTO_X`、`AUTO_Y`、`AUTO_YAW`（弧度），可选 `AUTO_Z`（默认 0）。

连接真机速度桥：

```bash
./g1_slam_ws/script/g1_navigation_real.sh start
./g1_slam_ws/script/g1_navigation_real.sh enable
```

真机桥的 `start`、`enable` 都要求 Nav2 已激活且当前定位有效、新鲜；同名 Dry Run 桥会被拒绝。`start` 启动桥时安全门保持关闭；`enable` 才允许 `/cmd_vel_nav` 控制 G1。机器人运动模式由操作者用原有方式切换。关闭控制或结束导航：

定位失效或状态断流时，导航速度桥会停止输出并关闭控制门。重新确认定位后，需要显式 `enable` 和新的速度指令才能恢复控制。

```bash
./g1_slam_ws/script/g1_navigation_real.sh disable
./g1_slam_ws/script/g1_navigation_real.sh stop
./g1_slam_ws/script/g1_navigation.sh stop
```

只验证规划与速度桥时，用 `./g1_slam_ws/script/g1_navigation.sh start-auto-dry`；该入口仍需要真实雷达定位。无显示器时设置 `G1_ENABLE_RVIZ=0`，自动全局定位可以直接运行。`start-auto` 启动定位和 Nav2 规划，真机控制仍通过上述速度桥入口启用。

```bash
# 当前定位状态（String 消息中的 JSON）：state、valid、reason、fitness 及时间戳
ros2 topic echo /g1_relocalization/status --qos-durability transient_local
# 使用同一实时就绪检查；非零表示当前不能启动导航
python3 g1_slam_ws/script/g1_wait_localization.py --once --timeout 5
# 无雷达、无机器人运行入口回归检查
python3 -m unittest discover -s g1_slam_ws/script/tests -v
```

自动定位参数位于 `g1_slam_ws/src/g1_relocalization/config/relocalization.yaml`。更换地图或雷达安装后，需要用不同位置、朝向及相似场景的实测点云验证定位成功率；离线检查不能代替真实场景验收。

第一版适用于相同楼层、既有雷达安装和已标定的地面模型。搜索采用全图粗搜索及多个候选的局部细化，是启发式算法；重复结构、遮挡和地图变化仍可能需要人工后备。运行中被搬移后自动重新全局搜索尚未实现。

现场验证标志：**常用启动点自动全局初始化成功**（2026-10-12，用户现场反馈及运行日志确认）。对应基线为 `3e3bf1e`，Git 标记 `auto-localization-usual-start-ok-20261012`。

| 验证位置 | 记录结果 |
| --- | --- |
| 常用启动点 | `initialization_mode=global`，全局搜索约 0.71 秒，后续新扫描确认成功；fitness=0.028075，coverage=0.949 |
| 其他位置 | 原版搜索约 0.85 秒后返回 `AMBIGUOUS`；之后人工初始化确认成功，fitness=0.079234，coverage=0.693；自动定位优化后需现场复测 |

以上标志仅确认常用启动点成功，不代表所有位置或完整真实导航已经验收。

2026-10-12 的异地定位优化将固定 12 个精配准候选改为初始 12 个、按歧义需要扩展到最多 48 个；合并同一位置模式，并用完整三维质量排除投影相似的伪候选。NDT 后增加最多 20 次的 ICP 修正，限制移动 0.50 m、转动 10°，原质量和歧义阈值保持不变；新扫描确认使用同一修正方法。仍有可信不同地点或预算不足时继续拒绝初始化。

本轮 55 项自动化测试/场景通过，包括四个不同位置/朝向的独立射线扫描、遮挡、环境变化、重复房间和单墙拒绝。其他实际启动位置的优化效果仍需复测。

现有启动脚本会将每次全局搜索的精确输入 PCD 与候选 JSON 保存到 `g1_slam_ws/runtime/relocalization/`。报告包含候选位姿、覆盖率、误差、参数和具体歧义原因；该目录不进入 Git。若仍失败，请保留这两个文件及 `runtime/navigation/logs/relocalization.log`。保存的 PCD 已在重力参考坐标，无需再次应用 body 姿态旋转：

```bash
source unitree_ros2/setup.sh
# 将文件名替换为本轮生成的 PCD；已修改地图/地面参数时同步 CLI 参数。
ros2 run g1_relocalization global_matcher_check \
  --map "${G1_MAP_PCD:-$G1_WS/maps/map.pcd}" \
  --scan "$G1_WS/runtime/relocalization/global_<扫描时间戳>_g0.pcd" \
  --ndt-candidates 12 --ndt-max-candidates 48 --timeout 180
```

离线检查当前地图索引，或对独立录制的局部扫描测试匹配：

```bash
source unitree_ros2/setup.sh
ros2 run g1_relocalization global_matcher_check --map "$PWD/g1_slam_ws/maps/map.pcd"
ros2 run g1_relocalization global_matcher_check --help
```

只传地图时不会验证定位效果。扫描坐标和地面参数要求见工具帮助；完整模块验证和新增功能现场验收步骤位于本机 `doc/`，该目录已被 Git 忽略。

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
