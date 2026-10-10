#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/g1_env.sh"

if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
  echo '用法: g1_build.sh；顺序构建全部包。可用 G1_BUILD_JOBS 设置编译线程数。'
  exit 0
fi
[[ $# == 0 ]] || { g1_error "此入口构建全部包，不接受额外 colcon 参数"; exit 2; }
[[ "${G1_BUILD_JOBS:-2}" =~ ^[1-9][0-9]*$ ]] || { g1_error "G1_BUILD_JOBS 必须为正整数"; exit 2; }
g1_load_ros
command -v colcon >/dev/null || { g1_error '缺少 colcon'; exit 1; }
cd "${G1_WS}"

export CMAKE_BUILD_PARALLEL_LEVEL="${G1_BUILD_JOBS:-2}"
export MAKEFLAGS="-j${G1_BUILD_JOBS:-2}"
colcon build --base-paths src --executor sequential \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DPython3_EXECUTABLE=/usr/bin/python3
printf '%s %s\n' "${ROS_DISTRO}" "$(uname -m)" > install/.g1_local_build
echo "[OK] 本机构建完成。运行 script/g1_check.sh 检查环境与网卡。"
