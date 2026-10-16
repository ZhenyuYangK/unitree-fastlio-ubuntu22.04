# G1 SLAM 本机运行

本项目已适配当前电脑：Ubuntu 22.04、x86_64、ROS 2 Humble。包含 MID360 驱动、FAST-LIO 建图、自动全局定位和 NDT 跟踪、Nav2、G1 速度桥、导航点管理及双语讲解巡航工具。

在项目根目录执行下面的命令。

本轮真机测试反馈及待处理问题见 [KNOWN_ISSUES.md](KNOWN_ISSUES.md)，其中首个导航点语音播放异常和满音量需求仍待讨论处理。

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

该入口不需要初始位置、朝向或 `auto_start_pose.env`。机器人保持静止后，系统采集点云，在三维地图中搜索候选位置和朝向，用 NDT 精配准及后续新扫描确认结果。只有 `/g1_relocalization/status` 报告有效且新鲜的 `LOCALIZED` 或 `TRACKING` 状态，脚本才启动 Nav2。默认等待 180 秒，可通过环境变量调整：

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

导航速度配置：最大前进速度 1.0 m/s，最大转速 0.40 rad/s，禁止横移和倒退。
Nav2 的横向速度范围为 0，导航真机/Dry Run 桥均关闭横移开关。
Nav2 和导航真机/Dry Run 桥的线速度加速上限均为 0.20 m/s²、减速幅值为 0.30 m/s²，
角速度加减速幅值均为 4.0 rad/s²。
参数修改后需重启 Nav2 和导航桥加载；`g1_navigation.sh` 会重新生成运行时参数文件。

连接真机速度桥：

```bash
./g1_slam_ws/script/g1_navigation_real.sh start
./g1_slam_ws/script/g1_navigation_real.sh enable
```

真机桥的 `start`、`enable` 都要求 Nav2 已激活且当前定位有效、新鲜；同名 Dry Run 桥会被拒绝。`start` 自动在后台启动真实语音桥，并确认 `/g1_audio/speak` 就绪和 `dry_run=false`；已经运行的真实语音桥会被复用。即使运动桥已运行，再次 `start` 也会补齐语音桥。语音节点重复、模式不匹配或启动失败时命令报错，不能据此视为导航准备完成。`start` 新建运动桥时安全门保持关闭；`enable` 才允许 `/cmd_vel_nav` 控制 G1。机器人运动模式由操作者用原有方式切换。关闭控制或结束导航：

定位失效或状态断流时，导航速度桥会停止输出并关闭控制门。重新确认定位后，需要显式 `enable` 和新的速度指令才能恢复控制。

```bash
./g1_slam_ws/script/g1_navigation_real.sh disable
./g1_slam_ws/script/g1_navigation_real.sh stop
./g1_slam_ws/script/g1_navigation.sh stop
```

`g1_navigation_real.sh status` 同时检查运动桥和真实语音桥，`logs` 同时查看两者日志。自动启动的语音日志位于 `g1_slam_ws/runtime/navigation/logs/audio_bridge.log`。真机桥 `stop` 同时停止由该脚本启动的语音进程；复用的外部语音实例由原启动者停止。任务完成或取消时保留语音桥，供下一次任务使用。启动语音桥默认保留机器人当前音量，可在首次启动前设置 `export G1_AUDIO_VOLUME=70`（范围 `0..100`，`-1` 保留当前音量）；该设置不修改已运行实例。

只验证规划与速度桥时，用 `./g1_slam_ws/script/g1_navigation.sh start-auto-dry`；该入口仍需要真实雷达定位。无显示器时设置 `G1_ENABLE_RVIZ=0`，自动全局定位可以直接运行。`start-auto` 启动定位和 Nav2 规划，真机控制仍通过上述速度桥入口启用。

```bash
# 当前定位状态（String 消息中的 JSON）：state、valid、reason、fitness 及时间戳
ros2 topic echo /g1_relocalization/status --qos-durability transient_local
# 使用同一实时就绪检查；非零表示当前不能启动导航
python3 g1_slam_ws/script/g1_wait_localization.py --once --timeout 5
# 无雷达、无机器人的任务配置及流程回归检查
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/g1_slam_ws/src/g1_task_manager" \
  /usr/bin/python3 -m unittest discover -s g1_slam_ws/src/g1_task_manager/test -v
```

自动定位参数位于 `g1_slam_ws/src/g1_relocalization/config/relocalization.yaml`。更换地图或雷达安装后，需要用不同位置、朝向及相似场景的实测点云验证定位成功率；离线检查不能代替真实场景验收。

第一版适用于相同楼层、既有雷达安装和已标定的地面模型。搜索采用全图粗搜索及多个候选的局部细化，是启发式算法；重复结构、遮挡和地图变化仍可能需要人工后备。运行中被搬移后自动重新全局搜索尚未实现。

离线检查当前地图索引，或对独立录制的局部扫描测试匹配：

```bash
source unitree_ros2/setup.sh
ros2 run g1_relocalization global_matcher_check --map "$PWD/g1_slam_ws/maps/map.pcd"
ros2 run g1_relocalization global_matcher_check --help
```

只传地图时不会验证定位效果。扫描坐标和地面参数要求见工具帮助；完整模块验证和新增功能现场验收步骤位于本机 `doc/`，该目录已被 Git 忽略。

## 导航点管理

统一入口为 `g1_slam_ws/script/g1_waypoints.sh`。默认导航点文件为 `g1_slam_ws/task_data/maps/laboratory_map_v1/waypoints.yaml`，默认任务文件为 `g1_slam_ws/task_data/missions/missions.yaml`；这两个现场配置均被 Git 忽略。可通过 `G1_WAYPOINTS_FILE`、`G1_MISSIONS_FILE` 覆盖路径，也可在命令中传入 `--file`、`--missions-file`。导航点与任务的 `map_id` 必须一致。

```bash
./g1_slam_ws/script/g1_waypoints.sh path
./g1_slam_ws/script/g1_waypoints.sh list
./g1_slam_ws/script/g1_waypoints.sh show point_01
./g1_slam_ws/script/g1_waypoints.sh validate
```

`list`、`show` 和配置校验均可离线运行。`validate` 同时校验指定任务文件中的全部导航点引用。新环境需要先准备导航点 YAML；空文件的结构如下，`map_id` 应填写当前使用的地图标识：

```yaml
schema_version: 1
map_id: laboratory_map_v1
frame_id: map
base_frame: nav_base
waypoints: {}
```

录点时先完成定位，将机器人移动到目标位置和朝向并保持静止。工具连续采样 `map -> nav_base`，检查定位、TF 新鲜度及位置和朝向波动后保存：

```bash
# 新建导航点；依次记录 point_01 到 point_05
./g1_slam_ws/script/g1_waypoints.sh record point_01 --name "第一讲解点"
# 重新采集已经存在的导航点
./g1_slam_ws/script/g1_waypoints.sh update point_01
# 备份和删除预览；被当前指定任务文件引用的点不能删除
./g1_slam_ws/script/g1_waypoints.sh backup
./g1_slam_ws/script/g1_waypoints.sh delete unused_point
# 确认预览后执行删除
./g1_slam_ws/script/g1_waypoints.sh delete unused_point --yes
```

录点和更新不会覆盖其他导航点，写入前自动备份到 `g1_slam_ws/backup/waypoints/`。坐标单位为米，`yaw` 单位为弧度。使用其他点文件时将路径放在子命令前，例如 `./g1_slam_ws/script/g1_waypoints.sh --file /path/to/waypoints.yaml list`。

## 多点导航与双语讲解

可直接使用仓库中的[五站双语讲解示例](g1_slam_ws/src/g1_task_manager/config/tour_missions.example.yaml)，其任务 ID 为 `five_point_tour`，引用 `point_01` 至 `point_05`。示例文字需要替换为现场介绍，每种语言的等待时间需要真机标定；使用它不会修改现有 `missions.yaml`。下面的变量在执行任务的终端设置一次：

```bash
G1_TOUR_MISSIONS="$PWD/g1_slam_ws/src/g1_task_manager/config/tour_missions.example.yaml"
# 列出任务及路线
./g1_slam_ws/script/g1_waypoints.sh missions --missions-file "$G1_TOUR_MISSIONS"
# 检查整条任务，不创建 ROS 节点，不发送目标
./g1_slam_ws/script/g1_waypoints.sh mission five_point_tour \
  --missions-file "$G1_TOUR_MISSIONS" --check-only
```

任务文件的顶层包含 `schema_version: 1`、`map_id` 和 `missions` 字典。每个任务包含 `name` 与非空 `steps` 列表，每个步骤至少指定 `waypoint`；完整结构见示例文件。所有步骤及引用在执行前统一校验，未知字段、重复键和无效配置均会拒绝。

| 步骤字段 | 行为 |
| --- | --- |
| `timeout_sec` | 本段导航超时；不包含播报、额外停留和人工等待 |
| `speech.mode: tts` | 使用 Unitree 文字转语音 |
| `speech.language: zh / en / both` | 中文、英文，或先中文后英文 |
| `speech.content.zh / en` | 对应语言的 `speaker_id`、非空 `text` 和有限正数 `wait_sec` |
| `speech.failure_policy: abort` | 选定语言任一播报失败即结束任务并保持安全门关闭；省略时也采用 `abort` |
| `dwell_sec` | 全部选定语言等待结束后的额外停留，讲解任务建议为 `0` |
| `advance_mode: manual` | 播报及额外停留后持续等待终端放行 |
| `advance_mode: auto` | 播报及额外停留后自动进入下一段；缺省为 `auto` |

单语模式只要求对应语言内容完整，`both` 必须同时配置中英文。`speaker_id` 为非负 int32，官方示例中文使用 `0`、英文使用 `1`。旧任务没有 `speech` 和 `advance_mode` 时，继续采用原有到点定时停留、自动巡航行为。

`wait_sec` 从对应 TTS 请求返回成功后计时。接口确认的是请求成功；等待届满不代表收到机器人播放完成回调。`both` 按“中文请求、中文等待、英文请求、英文等待”顺序执行，再执行 `dwell_sec`。需要现场调整等待时间，覆盖语音时长及播放延迟。

### 无真机流程演练

先编译新增的 `g1_task_interfaces`、`g1_task_manager` 和 `g1_audio_bridge`，或运行前文的完整构建。模拟模式使用真实 ROS 状态查询与放行服务，模拟导航、定位、安全门和语音，不需要雷达、Nav2、运动桥或语音桥：

```bash
./g1_slam_ws/script/g1_waypoints.sh mission five_point_tour \
  --missions-file "$G1_TOUR_MISSIONS" --simulate --time-scale 0.01
```

`--time-scale` 仅用于模拟，缩放语音、停留及模拟导航耗时。到人工等待后始终持续等待，不设置自动出发倒计时。另开一个终端查询并放行当前站：

```bash
./g1_slam_ws/script/g1_waypoints.sh status
./g1_slam_ws/script/g1_waypoints.sh continue
```

每站重复上述操作，最后一站也必须执行 `continue` 才完成任务。状态显示当前任务、站点、阶段和下一点，模拟模式带有标识。导航、播报、额外停留期间会拒绝放行，不会预存请求；每次放行绑定本次运行和等待标识，重复或过期请求不会放行下一站。`continue` 成功表示请求已接受，后续进展通过任务输出或 `status` 查看。控制终端断开后任务仍继续等待，重新打开终端即可操作。

需要重跑 ROS 集成回归时，在项目根目录加载环境后执行。测试会自动使用独立 Domain 和本地回环接口，并清理临时配置、任务记录及日志：

```bash
source unitree_ros2/setup.sh
G1_RUN_ROS_TESTS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD/g1_slam_ws/src/g1_task_manager:$PYTHONPATH" \
  /usr/bin/python3 -m unittest discover -s g1_slam_ws/src/g1_task_manager/test \
  -p 'test_mission_integration.py' -v
# 真实 AudioClient 对接本地模拟响应，不连接机器人
/usr/bin/python3 g1_slam_ws/src/g1_audio_bridge/test/test_audio_bridge.py \
  --bridge "$PWD/g1_slam_ws/install/g1_audio_bridge/lib/g1_audio_bridge/g1_audio_bridge"
```

### 真机执行

按照前文启动定位和 Nav2 后，启动真机速度桥即可同时准备真实语音桥，无需额外打开语音终端：

```bash
./g1_slam_ws/script/g1_navigation_real.sh start
./g1_slam_ws/script/g1_navigation_real.sh status
```

带 `speech` 的真实任务在发送第一个导航目标前检查语音 Action 和 `dry_run=false`，缺失或配置不符时直接结束并执行运动收尾，不会先走到讲解点。该检查不发送试播请求，也不代替机器人声音实测。任务执行器负责每段导航前的就绪检查及安全门开关，讲解和人工等待期间安全门保持关闭，不要手动 `enable`。

如需独立验证声音，仍可手动运行 `ros2 run g1_audio_bridge g1_audio_bridge --ros-args -p dry_run:=false -p volume:=70`。语音桥单独启动默认 `dry_run=true`；仅运行不带参数的命令会输出播报计划并等待，不向机器人发送音频请求，真实导航启动和带讲解的真实任务会拒绝这种实例。音量范围为 `0..100`，默认 `-1` 保留机器人当前音量，首次真实播报前读取并按配置设置。节点参数在启动时固定，修改后重启。语音桥沿用项目的网卡、CycloneDDS 和 ROS Domain 配置，使用 `/api/voice/request`、`/api/voice/response`。

在任务终端执行：

```bash
./g1_slam_ws/script/g1_waypoints.sh mission five_point_tour \
  --missions-file "$G1_TOUR_MISSIONS" --execute
```

负责人仍在另一终端使用 `status`、`continue`。每次放行后重新检查定位和导航状态，满足条件才前往下一站。最后一站提示“继续以完成任务”，确认后结束整条路线。人工等待时长不计入导航超时。

在任务终端按 `Ctrl+C` 可取消导航、播报等待和人工等待。收尾先处理运动安全门及本任务的 Nav2 目标，语音取消异步请求停止，不阻塞运动收尾。Unitree `PlayStop(app_name)` 对自带 TTS 的实际中断效果仍需真机验证。

### Action 入口

现有 `/g1_task/execute_mission` Action 通过同一 CLI 执行子进程运行任务，`/g1_task/get_state`、`/g1_task/continue` 由实际执行任务的节点提供。直接终端执行与 Action 执行共用同一套状态和放行命令，Action 同时转发播报及人工等待阶段的反馈。

需要通过 Action 真机执行时，在已启动定位、Nav2、真机速度桥和真实语音桥的基础上，另开终端运行服务端：

```bash
source unitree_ros2/setup.sh
ros2 run g1_task_manager g1_task_manager_node --ros-args \
  -p execute_real:=true \
  -p "missions_file:=$PWD/g1_slam_ws/src/g1_task_manager/config/tour_missions.example.yaml"
```

然后在客户端终端运行：

```bash
source unitree_ros2/setup.sh
ros2 run g1_task_manager g1_mission five_point_tour
```

服务端默认 `execute_real=false`，只检查配置，不执行导航或提供人工等待流程；启动参数变更后须重启服务端。客户端 `Ctrl+C` 请求取消并等待收尾结果，客户端退出或状态服务不可用均不能视为机器人停止确认。同一工作空间同时只允许一个多点任务。

### 停止未确认后的恢复

真实任务启动时创建 `g1_slam_ws/runtime/missions/recovery_required.json`，只有确认关门且本任务导航目标终止后才自动移除。异常退出、断电或 `STOP_UNCONFIRMED` 会保留标记并阻止后续真实任务。不要通过反复重试或直接删除标记绕过恢复：

1. 使用遥控器确认机器人已经停止，并结束原任务进程；检查标记中记录的任务报告及终端错误。报告位于 `g1_slam_ws/runtime/missions/`。
2. 确认真机运动安全门关闭。可执行 `./g1_slam_ws/script/g1_navigation_real.sh disable`，但必须检查服务返回 `success: true`；脚本退出码不能代替关门确认。服务无响应时先恢复通信并确认关门。
3. 确认本任务自己的 Nav2 目标已进入 `SUCCEEDED`、`CANCELED` 或 `ABORTED` 终态。优先使用原任务客户端取消并等待结果；也可检查 `/navigate_to_pose/_action/status` 中对应目标的状态（`4`、`5`、`6`）。不要用“取消全部目标”影响其他客户端；无法确认目标归属和终止状态时保持标记，并在机器人静止、安全门关闭的条件下处理 Nav2。
4. 只有确认遥控停止、安全门关闭、原任务退出且自己的目标终止后，才手动移除该标记。若 Action 管理器因停止未确认而进入拒绝状态，完成上述检查后重启管理器，再重新检查定位并启动任务。

```bash
# 仅在完成上述人工确认后执行
rm g1_slam_ws/runtime/missions/recovery_required.json
```

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
./g1_slam_ws/script/g1_waypoints.sh mission --help
```

运行时会自动创建 `runtime` 目录，建图与导航日志分别写入 `runtime/mapping/logs` 和 `runtime/navigation/logs`，ROS 日志写入 `runtime/ros_logs`。历史日志和临时验收产物不保留。

本机适配保留原项目倒装 MID360 的 `body_roll_deg=180` 及 `body -> nav_base` 变换。若雷达安装方向变化，需要同步调整 FAST-LIO 外参和重定位/导航坐标变换。
