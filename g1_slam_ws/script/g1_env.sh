#!/usr/bin/env bash
# 公共环境。仅定义函数和配置，source 本文件不会启动 ROS 节点。
G1_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export G1_WS="${G1_WS:-$(cd -- "${G1_SCRIPT_DIR}/.." && pwd)}"
if [[ -f "${G1_LOCAL_ENV:-${G1_SCRIPT_DIR}/local.env}" ]]; then
  # shellcheck disable=SC1090
  source "${G1_LOCAL_ENV:-${G1_SCRIPT_DIR}/local.env}"
fi
G1_ROS_SETUP="${G1_ROS_SETUP:-/opt/ros/${G1_ROS_DISTRO:-humble}/setup.bash}"

g1_error() { printf '[ERROR] %s\n' "$*" >&2; }

g1_load_ros() {
  [[ -f "${G1_ROS_SETUP}" ]] || {
    g1_error "找不到 ${G1_ROS_SETUP}，请安装 ROS 2 ${G1_ROS_DISTRO:-humble}"
    return 1
  }
  if [[ -n "${ROS_DISTRO:-}" && "${ROS_DISTRO}" != "${G1_ROS_DISTRO:-humble}" ]]; then
    g1_error "当前终端加载了 ${ROS_DISTRO}，请在新终端运行，避免混用 ROS 版本"
    return 1
  fi
  local had_nounset=0
  [[ "$-" != *u* ]] || had_nounset=1
  set +u
  # shellcheck disable=SC1090
  source "${G1_ROS_SETUP}"
  if (( had_nounset )); then set -u; fi
  export ROS_LOG_DIR="${G1_WS}/runtime/ros_logs"
  mkdir -p "${ROS_LOG_DIR}"
  # 系统 Humble 的 CycloneDDS，无需加载原电脑的 ARM/Foxy underlay。
  if [[ "${RMW_IMPLEMENTATION:-}" == rmw_cyclonedds_cpp && -z "${CYCLONEDDS_URI:-}" ]]; then
    [[ "${G1_NETWORK_INTERFACE:-}" =~ ^[a-zA-Z0-9_.:-]+$ ]] || {
      g1_error 'G1_NETWORK_INTERFACE 无效'; return 1;
    }
    export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"${G1_NETWORK_INTERFACE}\" priority=\"default\" multicast=\"default\" /></Interfaces></General><Discovery><MaxAutoParticipantIndex>100</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"
  fi
}

g1_source_environment() {
  g1_load_ros || return 1
  [[ -f "${G1_WS}/install/local_setup.bash" ]] || {
    g1_error "缺少本机构建，请执行 ${G1_SCRIPT_DIR}/g1_build.sh"; return 1;
  }
  local had_nounset=0
  [[ "$-" != *u* ]] || had_nounset=1
  set +u
  # shellcheck disable=SC1090
  source "${G1_WS}/install/local_setup.bash"
  if (( had_nounset )); then set -u; fi
  if [[ -d "${G1_WS}/install/livox_sdk2/lib" ]]; then
    export LD_LIBRARY_PATH="${G1_WS}/install/livox_sdk2/lib:${LD_LIBRARY_PATH:-}"
  fi
  ros2 pkg prefix g1_loco_bridge >/dev/null 2>&1 || {
    g1_error "工作空间尚未完整编译，请执行 ${G1_SCRIPT_DIR}/g1_build.sh"; return 1;
  }
}

g1_prepare_livox_config() {
  export G1_LIVOX_CONFIG="${G1_WS}/runtime/livox/MID360_config.json"
  python3 "${G1_SCRIPT_DIR}/g1_livox_config.py" || return 1
}

g1_start_rviz() {
  [[ "${G1_ENABLE_RVIZ:-1}" == 1 ]] || return 0
  [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] || {
    g1_error '没有图形显示，设置 G1_ENABLE_RVIZ=0 可禁用 RViz'; return 1;
  }
  start_process rviz rviz2 -d "$1"
}
