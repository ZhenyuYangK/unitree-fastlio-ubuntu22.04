# G1 网页控制框架

面向当前 Ubuntu 22.04 / x86_64 / Humble 开发电脑的需求草案、HTTP/WebSocket 网关和浏览器页面。PC2 的 Ubuntu 20.04 / aarch64 / Foxy 原生版本后续单独适配。

先阅读 [需求与待确认项](docs/requirements.md)，接口见 [API 契约](docs/api.md)。默认直接使用本地工作空间的地图、导航点和任务，支持在页面编辑并保存后端配置。显式 `ros_control` 模式接入导航准备、初始位姿、单点导航及巡航开始/取消/放行；使用流程见 [网页定位与导航](docs/navigation.md)。PC2 原生版本后续单独适配。

机器人已连接时，按 [现场完整验证方案](docs/real_robot_validation.md) 分阶段验证：定位/状态、网页配置同步、ROS 模拟联调、限速单点、语音、取消和五点巡航。该文档区分已有只读通信基线、合成导航测试与尚待现场验收的真实运动。

网页建图入口、成果路径与异常处理见 [建图使用说明](docs/mapping.md)。已接入启动、保存、保存并结束、停止、点云俯视预览和 PCD 下载。

## 本地地图与配置

- 实际读取 `g1_slam_ws/maps/map_multilayer.yaml` 与对应 PGM，不再默认显示示意地图。
- 导航点来自 `g1_slam_ws/task_data/maps/laboratory_map_v1/waypoints.yaml`，任务来自 `g1_slam_ws/task_data/missions/missions.yaml`。
- 在地图上选择坐标新增站点，或点击站点/列表编辑名称、X、Y、yaw；支持删除未被任务引用的导航点。
- 创建、编辑、删除任务，调整站点顺序、超时、停留、人工/自动推进、中英讲解文本、发音人与等待时间。
- 保存直接写入以上 YAML，保留已有导航点采样元数据；原配置备份到 `g1_slam_ws/backup/web_console/`。
- 其他浏览器及命令行修改通过 2 Hz 状态流自动同步。编辑窗口保留打开时的版本，旧版本保存会报冲突；点击“重新载入后端”后重新编辑。
- 保存复用现有 YAML 校验器，校验导航点引用、map_id 和讲解配置；与 CLI 共用文件锁，任务运行或有恢复标记时拒绝修改。
- 保留公共导视牌风格、浅/深色主题、手机布局、键盘焦点和减少动态效果支持。

地图虚线表示任务的站点顺序，绿色实线表示新鲜的 Nav2 规划路径。ROS 模式接入 map→nav_base 位姿和朝向，local 模式明确显示机器人实时状态未连接。地图像素本身不在网页编辑范围内。

## 本机启动

在项目根目录执行，Python 3.10：

```bash
python3 -m venv --system-site-packages web_console/.venv
web_console/.venv/bin/python -m pip install -r web_console/requirements.txt
bash web_console/run.sh
```

浏览器打开 **http://127.0.0.1:8080**。默认 `G1_WEB_MODE=local`，无需启动 ROS。点击“取得操作权”，然后在导航点、巡航任务页或地图标记中编辑，点击“保存到后端”写入文件。启动网关本身不会自动启动机器人业务节点；建图页的显式操作可以启动雷达和 FAST-LIO。

若创建虚拟环境提示 ensurepip 不可用，需要先安装系统 python3-venv 包。使用 system-site-packages 是为了在之后的 Humble 模式访问系统 rclpy。

可通过环境变量覆盖数据源，路径均由服务端配置：

| 环境变量 | 用途 |
| --- | --- |
| G1_WS | 工作空间根目录，默认本仓库的 g1_slam_ws |
| G1_MAP_YAML | 地图 YAML，默认 $G1_WS/maps/map_multilayer.yaml |
| G1_MAP_PGM | 可选，覆盖地图 YAML 中的 image 路径 |
| G1_WAYPOINTS_FILE | 导航点 YAML |
| G1_MISSIONS_FILE | 任务 YAML |

地图分辨率、原点和旋转从地图 YAML 获取，用于 ROS 米制坐标与图片像素之间的转换。数据源缺失或校验失败时显示错误，不回退到模拟数据。

局域网访问时设置口令和监听地址：

```bash
read -rs -p "访问口令: " G1_WEB_TOKEN
export G1_WEB_TOKEN
export G1_WEB_HOST=0.0.0.0
bash web_console/run.sh
```

其他设备访问 `http://控制电脑的可达局域网IP:8080` 并输入口令；同一时间一个设备持有操作权，其他设备可查看。页面按当前域名构造 API/WS 地址。

需要独立体验五站模拟任务时显式启动：

```bash
G1_WEB_MODE=mock bash web_console/run.sh
```

模拟模式沿用示例地图和任务，不写入现场文件。点击“取得控制权”后开始模拟巡航，到站后放行，末站也需放行。

## 当前电脑的 ROS 只读接入

先按照项目根 README 编译并启动已有 ROS 系统，然后在没有混用 Foxy 的终端执行：

```bash
read -rs -p "访问口令: " G1_WEB_TOKEN
export G1_WEB_TOKEN
G1_WEB_MODE=ros_readonly bash web_console/run.sh
```

启动器加载本项目的 Humble 工作空间。已有定位节点和任务执行器独立运行；网关不启动 Nav2、不调用任务执行、不启用运动桥；建图页可显式管理雷达和 FAST-LIO。地图、导航点与任务文件同样使用以上本地数据源。此模式的“只读”指机器人运动/任务通道；配置文件可编辑，建图生命周期可操作。

此模式展示现场地图，不展示演示位置；定位/任务断流显示过期。任务空闲时 GetMissionState 服务可能不存在，因此显示状态未知，不推断已停止。

## PC2 后续原生版本

按当前需求不使用 Docker。先完成开发机版本，后续在 PC2 的 Ubuntu 20.04 / aarch64 / Foxy 上单独适配：

- 复用浏览器页面及 HTTP/WS 协议，分别维护 Humble 与 Foxy 的 ROS 适配器和依赖配置。
- 核对 Python 3.8 依赖版本、rclpy / Nav2 API、启动文件和参数，按 PC2 环境重新编译 C++ 包。
- 为 PC2 配置实际网卡、IP、地图和任务文件；现场数据被 Git 忽略，需要单独迁移。
- 在 PC2 验证雷达 UDP、DDS、Unitree 运动/语音接口、定位/Nav2 负载及断线处理。
- 当前 requirements.txt 面向 Python 3.10，不作为 PC2 的安装清单。Foxy 版本和真机兼容性尚未验证。
- 网关不自动启动机器人业务节点，后续原生服务启动、HTTPS、日志和进程管理按现场需求接入。

视觉规范见 [公共导视牌设计](docs/design.md)。Barlow 字体和授权文件随源码提供，页面不依赖外部字体服务；中文使用系统无衬线字体回退。

## 测试

```bash
web_console/.venv/bin/python -m pip install -r web_console/requirements-dev.txt
PYTHONPATH=web_console/backend web_console/.venv/bin/python -m unittest discover -s web_console/tests -v
node --check web_console/frontend/app.js
node web_console/tests/geometry_test.js
```

测试覆盖文件读写与备份、引用校验、外部变更、版本冲突、任务/CLI 锁、地图资源、多设备租约、模拟任务、认证/来源检查和定位新鲜度。写入测试只使用临时目录，不连接机器人。

可选浏览器检查使用 Playwright 和已有 Chrome，覆盖浅色/深色、站点状态、键盘焦点、手机布局及减少动态效果：

```bash
web_console/.venv/bin/python -m pip install playwright
# 另一个终端先用 G1_WEB_MODE=mock 启动网关
web_console/.venv/bin/python web_console/tests/browser_smoke.py
```

手机端操作权恢复检查会自行启动隔离的 mock 网关，覆盖临时续约失败、断网恢复、前后台切换、到期与多设备接管，不连接机器人：

```bash
PYTHONPATH=web_console/backend web_console/.venv/bin/python web_console/tests/browser_control_smoke.py
```

配置编辑浏览器测试使用现场数据的临时副本，测试脚本拒绝对真实工作空间写入：

```bash
# 将 maps/ 与 task_data/ 复制到 /tmp/g1-web-fixture，先启动该副本：
G1_WS=/tmp/g1-web-fixture G1_WEB_PORT=18083 bash web_console/run.sh
# 另一个终端运行：
G1_WEB_TEST_URL=http://127.0.0.1:18083 G1_WEB_TEST_WORKSPACE=/tmp/g1-web-fixture \
  web_console/.venv/bin/python web_console/tests/browser_sync_smoke.py
```

可选隔离 ROS 检查读取测试节点产生的数据，不启动机器人业务：

```bash
export G1_NETWORK_INTERFACE=lo
export ROS_DOMAIN_ID=173
source unitree_ros2/setup.sh
PYTHONPATH="web_console/backend:$PYTHONPATH" web_console/.venv/bin/python web_console/tests/ros_readonly_smoke.py
```

该测试自行固定 CycloneDDS 到回环接口，并检查定位/任务/建图点云接收、地图保存服务成功与拒绝、状态断流和适配器没有业务发布者。

## 代码结构

```text
web_console/
├── docs/                    需求、验收项与 HTTP/WS 契约
├── backend/g1_web/
│   ├── app.py               同源接口、认证、命令去重、状态快照
│   ├── control.py           单设备租约与错误模型
│   ├── config.py            模式与环境配置
│   ├── mapping.py           建图操作、持久结果、日志与下载
│   ├── cloud.py             有界点云俯视采样
│   ├── workspace.py         地图与配置读写、锁、版本、备份
│   └── adapters/
│       ├── base.py          后端能力边界
│       ├── local.py         本地文件模式，无 ROS 依赖
│       ├── mock.py          无 ROS 的五站模拟任务
│       └── ros_readonly.py  Humble 定位/任务只读接入
├── frontend/                无需构建、离线可加载的 HTML/CSS/JS
├── tests/                   不依赖机器人的协议与流程测试
└── run.sh                   单进程启动入口
```

真实控制适配器使用现有 ExecuteMission、GetMissionState、ContinueMission 接口，并保留已有就绪检查和停止恢复流程。当前 mode 接受 local / mock / ros_readonly / ros_control；仅 ros_control 接入真实导航操作，必须设置访问口令。启动网关本身不自动启动机器人业务节点；导航控制详见 [使用说明](docs/navigation.md)。
