#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/g1_env.sh"
if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
  echo '用法: g1_check.sh [--offline]；检查本机构建、依赖、地图、网卡，不启动节点。'
  exit 0
fi
[[ $# == 0 || ( $# == 1 && "$1" == --offline ) ]] || { g1_error '未知参数'; exit 2; }
g1_source_environment
printf '[OK] 系统: %s / ROS 2 %s / %s / domain %s\n' "$(uname -m)" "${ROS_DISTRO}" "${RMW_IMPLEMENTATION}" "${ROS_DOMAIN_ID}"
for package in livox_sdk2 livox_ros_driver2 fast_lio g1_relocalization g1_nav2_bringup \
  g1_loco_bridge g1_unitree_ros2_probe g1_task_interfaces g1_task_manager unitree_api \
  nav2_behaviors nav2_map_server nav2_controller nav2_planner nav2_bt_navigator rviz2 rmw_cyclonedds_cpp; do
  if [[ "$package" == livox_sdk2 ]]; then
    [[ -f "${G1_WS}/install/livox_sdk2/lib/liblivox_lidar_sdk_shared.so" ]] || { g1_error '缺少本机 Livox SDK'; exit 1; }
  else
    ros2 pkg prefix "$package" >/dev/null || { g1_error "缺少包: ${package}"; exit 1; }
  fi
done
python3 -c 'import rclpy, yaml, numpy, scipy; from unitree_api.msg import Request; from livox_ros_driver2.msg import CustomMsg; from g1_task_interfaces.action import ExecuteMission; print("[OK] ROS/Python 消息和依赖")'
python3 - "${G1_WS}" <<'PY'
import sys
from pathlib import Path
import yaml
ws = Path(sys.argv[1])
pcd = Path(__import__('os').environ.get('G1_MAP_PCD', ws / 'maps/map.pcd'))
map_yaml = Path(__import__('os').environ.get('G1_MAP_YAML', ws / 'maps/map_multilayer.yaml'))
if not pcd.is_file() or not pcd.stat().st_size:
    raise SystemExit(f'[ERROR] 缺少 PCD 地图: {pcd}')
data = yaml.safe_load(map_yaml.read_text())
image = Path(__import__('os').environ.get('G1_MAP_PGM', data['image']))
if not image.is_absolute():
    image = map_yaml.parent / image
if not image.is_file():
    raise SystemExit(f'[ERROR] 缺少二维地图: {image}')
print('[OK] PCD 和二维地图')
PY
if [[ "${1:-}" != --offline ]]; then g1_prepare_livox_config; fi
echo '[OK] 检查通过。建图: script/g1_mapping.sh start；定位/导航: script/g1_navigation.sh start'
