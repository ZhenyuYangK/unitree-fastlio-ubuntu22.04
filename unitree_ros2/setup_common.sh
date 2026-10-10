#!/usr/bin/env bash
# 本项目使用系统 Humble CycloneDDS + 当前工作空间生成的 Unitree 消息。
UNITREE_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UNITREE_G1_ENV="${G1_WS:-${UNITREE_SCRIPT_DIR}/../g1_slam_ws}/script/g1_env.sh"
if [[ ! -f "${UNITREE_G1_ENV}" ]]; then
  printf '[ERROR] 找不到 %s；请设置 G1_WS\n' "${UNITREE_G1_ENV}" >&2
  return 1 2>/dev/null || exit 1
fi
# shellcheck disable=SC1090
source "${UNITREE_G1_ENV}"
g1_source_environment || { return 1 2>/dev/null || exit 1; }
printf '[OK] Unitree ROS 2 %s，网卡 %s，domain %s\n' "${ROS_DISTRO}" "${G1_NETWORK_INTERFACE}" "${ROS_DOMAIN_ID}"
