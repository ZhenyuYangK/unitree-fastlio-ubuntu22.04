#!/usr/bin/env bash
set -Eeuo pipefail

# G1 + MID360 + FAST-LIO 建图管理器
#
# 用法：
#   ./g1_mapping.sh start       启动雷达、FAST-LIO 和建图 RViz
#   ./g1_mapping.sh save        调用 /map_save 保存当前 PCD
#   ./g1_mapping.sh finish      保存地图后停止系统
#   ./g1_mapping.sh stop        停止系统（不主动调用 /map_save）
#   ./g1_mapping.sh restart
#   ./g1_mapping.sh status
#   ./g1_mapping.sh logs
#   ./g1_mapping.sh map-path    显示本次建图输出路径

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/g1_env.sh"
WS="${G1_WS}"

SOURCE_CFG="${WS}/src/FAST_LIO_ROS2/config/mid360.yaml"
RVIZ_CFG="${WS}/src/FAST_LIO_ROS2/rviz/fastlio.rviz"

RUNTIME_DIR="${WS}/runtime/mapping"
LOG_DIR="${RUNTIME_DIR}/logs"
PID_FILE="${RUNTIME_DIR}/mapping.pids"
SESSION_FILE="${RUNTIME_DIR}/session.env"
RUNTIME_CFG="${RUNTIME_DIR}/mid360_mapping.yaml"
STATE_HELPER="${SCRIPT_DIR}/g1_mapping_state.py"

mkdir -p "${LOG_DIR}"

say()  { printf '\033[1;36m[G1-MAP]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

source_environment() { g1_source_environment; }

check_package() {
  ros2 pkg prefix "$1" >/dev/null 2>&1 || die "ROS2 包不存在：$1"
}

check_prerequisites() {
  [[ -d "${WS}" ]] || die "工作空间不存在：${WS}"
  [[ -f "${SOURCE_CFG}" ]] || die "缺少 FAST-LIO 配置：${SOURCE_CFG}"
  [[ -f "${RVIZ_CFG}" ]] || die "缺少 RViz 配置：${RVIZ_CFG}"

  source_environment
  g1_prepare_livox_config || die "雷达网卡配置检查失败"
  check_package livox_ros_driver2
  check_package fast_lio

  local nodes
  nodes="$(timeout 8 ros2 node list --no-daemon --spin-time 1)" || die "无法核对导航节点，未启动建图"
  if grep -Eq '/(controller_server|planner_server|g1_relocalization|map_server|g1_cmd_vel_dry_run)$' <<<"$nodes"; then
    die "检测到定位、导航或运动桥仍在运行，请先按原管理方式结束这些进程"
  fi
}

pid_alive() { kill -0 "$1" 2>/dev/null; }

start_process() {
  local name="$1"
  shift
  local log_file="${LOG_DIR}/${name}.log"

  setsid "$@" >"${log_file}" 2>&1 < /dev/null 9>&- 8>&- &
  local pid=$!
  local token
  token="$(python3 "$STATE_HELPER" token "$pid")" || die "$name 启动后立即退出，请查看日志"
  printf '%s %s %s\n' "${name}" "${pid}" "$token" >>"${PID_FILE}"
  say "已启动 ${name}，PID=${pid}，日志=${log_file}"
}

group_running() {
  python3 "$STATE_HELPER" check "$1" "${2:-}" >/dev/null 2>&1
}

stop_from_pid_file() {
  [[ -f "${PID_FILE}" ]] || return 0
  local records name pid token state attempt remaining
  records="$(python3 "$STATE_HELPER" processes "$PID_FILE")" || die "PID 记录不可用，未发送停止信号"
  python3 -c 'import json,sys; sys.exit(any(p["state"] == "unverified" for p in json.loads(sys.argv[1])))' "$records" \
    || die "存在无法确认归属的旧 PID 记录，未发送停止信号；请核对实际进程后按原会话处理"
  while read -r name pid token; do
    if group_running "$pid" "$token"; then
      say "停止 ${name}，PID=${pid}"
      kill -INT -- "-${pid}" 2>/dev/null || true
    fi
  done < <(tac "$PID_FILE")
  for attempt in {1..12}; do
    remaining=0
    while read -r name pid token; do
      if group_running "$pid" "$token"; then remaining=1; fi
    done < "$PID_FILE"
    (( remaining )) || break
    sleep 0.5
  done
  while read -r name pid token; do
    if group_running "$pid" "$token"; then
      warn "$name 尚未退出，发送 TERM"
      kill -TERM -- "-${pid}" 2>/dev/null || true
    fi
  done < <(tac "$PID_FILE")
  for attempt in {1..10}; do
    remaining=0
    while read -r name pid token; do
      if group_running "$pid" "$token"; then remaining=1; fi
    done < "$PID_FILE"
    (( remaining )) || break
    sleep 0.5
  done
  records="$(python3 "$STATE_HELPER" processes "$PID_FILE")" || die "无法确认进程退出，PID 记录保留"
  python3 -c 'import json,sys; sys.exit(any(p["state"] != "stopped" for p in json.loads(sys.argv[1])))' "$records" \
    || die "建图进程退出尚未确认，PID 记录保留"
  rm -f "$PID_FILE"
}


wait_for_topic() {
  local topic="$1"
  local timeout_sec="${2:-30}"
  local elapsed=0

  while (( elapsed < timeout_sec )); do
    if timeout 4 ros2 topic list --no-daemon --spin-time 1 2>/dev/null | grep -Fx "${topic}" >/dev/null; then
      ok "话题已出现：${topic}"
      return 0
    fi
    sleep 1
    ((elapsed += 1))
  done

  return 1
}

wait_for_service() {
  local service="$1"
  local timeout_sec="${2:-30}"
  local elapsed=0

  while (( elapsed < timeout_sec )); do
    if timeout 4 ros2 service list --no-daemon --spin-time 1 2>/dev/null | grep -Fx "${service}" >/dev/null; then
      ok "服务已出现：${service}"
      return 0
    fi
    sleep 1
    ((elapsed += 1))
  done

  return 1
}

generate_runtime_config() {
  local output_path
  local stamp
  stamp="$(date +%Y%m%d_%H%M%S)"
  output_path="${G1_MAPPING_OUTPUT:-${WS}/maps/map_${stamp}.pcd}"
  output_path="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "${output_path}")"
  MAP_OUTPUT="${output_path}"

  mkdir -p "$(dirname "${output_path}")" "${RUNTIME_DIR}"

  python3 - "${SOURCE_CFG}" "${RUNTIME_CFG}" "${output_path}" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
output = Path(sys.argv[3]).resolve()

lines = src.read_text(encoding="utf-8").splitlines()
patched = []
found_path = False
found_save = False

for line in lines:
    stripped = line.strip()
    indent = line[:len(line) - len(line.lstrip())]

    if stripped.startswith("map_file_path:"):
        patched.append(f'{indent}map_file_path: "{output}"')
        found_path = True
    elif stripped.startswith("pcd_save_en:"):
        patched.append(f"{indent}pcd_save_en: true")
        found_save = True
    else:
        patched.append(line)

if not found_path:
    raise SystemExit("配置中找不到 map_file_path")
if not found_save:
    raise SystemExit("配置中找不到 pcd_save_en")

dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text("\n".join(patched) + "\n", encoding="utf-8")
PY

  printf 'MAP_OUTPUT=%q\nRUNTIME_CONFIG=%q\nSTART_TIME=%q\n' \
    "${output_path}" "${RUNTIME_CFG}" "${stamp}" >"${SESSION_FILE}"

  python3 - "$RUNTIME_DIR/session.json" "$output_path" "$stamp" <<'JSON_SESSION'
import json, os, pathlib, sys, uuid
path = pathlib.Path(sys.argv[1])
value = {"id": os.environ.get("G1_MAPPING_SESSION_ID") or str(uuid.uuid4()), "output": sys.argv[2], "started_at": sys.argv[3]}
path.with_suffix('.tmp').write_text(json.dumps(value, ensure_ascii=False))
path.with_suffix('.tmp').replace(path)
JSON_SESSION

  ok "本次地图输出：${output_path}"
  ok "运行配置：${RUNTIME_CFG}"
}

load_session() {
  [[ -f "${SESSION_FILE}" ]] || die "没有建图会话记录，请先执行 start"
  # shellcheck disable=SC1090
  source "${SESSION_FILE}"
}

start_all() {
  local records
  records="$(python3 "$STATE_HELPER" processes "$PID_FILE")" || die "无法核对已有建图进程"
  python3 -c 'import json,sys; sys.exit(any(p["state"] != "stopped" for p in json.loads(sys.argv[1])))' "$records" \
    || die "已有建图进程或未确认的 PID，请先结束原会话"
  check_prerequisites
  stop_from_pid_file

  : >"${PID_FILE}"
  rm -f "${LOG_DIR}"/*.log
  generate_runtime_config

  start_process \
    livox \
    ros2 launch livox_ros_driver2 msg_MID360_launch.py \
      user_config_path:="${G1_LIVOX_CONFIG}"

  wait_for_topic /livox/lidar 35 || die "未收到 /livox/lidar，请查看 livox.log"
  wait_for_topic /livox/imu 20 || die "未收到 /livox/imu，请查看 livox.log"

  start_process \
    fast_lio \
    ros2 launch fast_lio mapping.launch.py \
      config_path:="${RUNTIME_DIR}" \
      config_file:="$(basename "${RUNTIME_CFG}")" \
      map_file_path:="${MAP_OUTPUT}" \
      rviz:=false

  wait_for_topic /Odometry 40 || die "FAST-LIO 未发布 /Odometry"
  wait_for_topic /cloud_registered 30 || warn "未检测到 /cloud_registered"
  wait_for_service /map_save 30 || die "未检测到 /map_save"

  g1_start_rviz "${RVIZ_CFG}" || die "启动 RViz 失败"

  echo
  ok "建图系统已启动"
  say "使用遥控器缓慢走遍环境，尽量闭环并减少快速转动"
  say "保存地图：${SCRIPT_DIR}/g1_mapping.sh save"
  say "保存并停止：${SCRIPT_DIR}/g1_mapping.sh finish"
  show_map_path
}

save_map() {
  source_environment
  load_session

  wait_for_service /map_save 8 || die "/map_save 不存在，建图节点可能未运行"

  say "正在保存地图到 ${MAP_OUTPUT}"
  python3 "$SCRIPT_DIR/g1_mapping_save.py" --output "$MAP_OUTPUT" \
    || die "地图保存未确认，建图进程保留"

  ok "地图保存成功"
  ls -lh "${MAP_OUTPUT}"
}

show_map_path() {
  if [[ -f "${SESSION_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${SESSION_FILE}"
    printf '当前地图输出：%s\n' "${MAP_OUTPUT}"
  else
    warn "尚未创建本次建图会话"
  fi
}

stop_all() {
  source_environment || true
  stop_from_pid_file
  ok "建图系统已停止"
}

finish_all() {
  save_map
  stop_all
}

show_status() {
  source_environment
  echo "工作空间：${WS}"
  show_map_path
  echo

  if [[ -f "${PID_FILE}" ]]; then
    printf '%-14s %-10s %s\n' "进程" "PID" "状态"
    local records
    records="$(python3 "$STATE_HELPER" processes "$PID_FILE")" || die "无法核对 PID 记录"
    python3 - "$records" <<'STATUS_JSON'
import json, sys
labels = {'running': '运行中', 'stopped': '已退出', 'unverified': '归属未确认'}
for item in json.loads(sys.argv[1]):
    print('{:<14} {:<10} {}'.format(item['name'], item['pid'], labels[item['state']]))
STATUS_JSON
  else
    warn "没有 PID 文件"
  fi

  echo
  for topic in /livox/lidar /livox/imu /Odometry /cloud_registered /cloud_registered_body; do
    if timeout 4 ros2 topic list --no-daemon --spin-time 1 2>/dev/null | grep -Fx "${topic}" >/dev/null; then
      printf '[OK]   %s\n' "${topic}"
    else
      printf '[MISS] %s\n' "${topic}"
    fi
  done

  if timeout 4 ros2 service list --no-daemon --spin-time 1 2>/dev/null | grep -Fx /map_save >/dev/null; then
    printf '[OK]   /map_save\n'
  else
    printf '[MISS] /map_save\n'
  fi
}

show_logs() {
  for file in "${LOG_DIR}"/*.log; do
    echo
    printf '========== %s ==========\n' "$(basename "${file}")"
    [[ -f "${file}" ]] && tail -n 60 "${file}" || true
  done
}

usage() {
  cat <<EOF_USAGE
用法：
  $0 start
  $0 save
  $0 finish
  $0 stop
  $0 restart
  $0 status
  $0 logs
  $0 map-path

可选输出路径：
  G1_MAPPING_OUTPUT=/绝对路径/new_map.pcd $0 start
EOF_USAGE
}

main() {
  case "${1:-start}" in
    start|save|finish|stop|restart)
      exec 9>"$WS/runtime/stack_lifecycle.lock"
      flock -n 9 || die "另一个建图/导航操作正在执行"
      mkdir -p "$WS/runtime/missions"
      exec 8>"$WS/runtime/missions/mission.lock"
      flock -n 8 || die "任务运行中，不能操作建图"
      ;;
  esac
  case "${1:-start}" in
    start|restart) [[ ! -f "$WS/runtime/missions/recovery_required.json" ]] || die "存在停止未确认的任务，不能启动建图" ;;
  esac
  case "${1:-start}" in
    start) start_all ;;
    save) save_map ;;
    finish) finish_all ;;
    stop) stop_all ;;
    restart) stop_all; sleep 2; start_all ;;
    status) show_status ;;
    logs) show_logs ;;
    map-path) show_map_path ;;
    -h|--help|help) usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
