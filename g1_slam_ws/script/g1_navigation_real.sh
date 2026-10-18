#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/g1_env.sh"
WS="${G1_WS}"

CFG="$WS/src/g1_loco_bridge/config/g1_loco_bridge_nav2_real.yaml"

RUNTIME="$WS/runtime/navigation"
LOG_DIR="$RUNTIME/logs"
PID_FILE="$RUNTIME/real_bridge.pid"
LOG_FILE="$LOG_DIR/real_bridge.log"
AUDIO_PID_FILE="$RUNTIME/audio_bridge.pid"
AUDIO_LOG_FILE="$LOG_DIR/audio_bridge.log"
LOCALIZATION_HELPER="${SCRIPT_DIR}/g1_wait_localization.py"

mkdir -p "$LOG_DIR"

load_env() { g1_source_environment; }

# A PID can be reused after an interrupted session. Match its kernel start time
# before sending any signal to a process recorded as ours.
process_token()
{
    python3 - "$1" <<'PY'
import pathlib
import sys
try:
    fields = pathlib.Path('/proc/' + sys.argv[1] + '/stat').read_text().rsplit(')', 1)[1].split()
    if fields[0] == 'Z':
        raise SystemExit(1)
    print(fields[19])
except (OSError, IndexError):
    raise SystemExit(1)
PY
}

stop_audio_bridge()
{
    [[ -f "$AUDIO_PID_FILE" ]] || return 0
    local audio_pid token current attempt
    read -r audio_pid token < "$AUDIO_PID_FILE" || true
    [[ "${audio_pid:-}" =~ ^[1-9][0-9]*$ && "${token:-}" =~ ^[0-9]+$ ]] || {
        echo "[ERROR] 语音 PID 记录无效，未发送停止信号：$AUDIO_PID_FILE"
        return 1
    }
    current="$(process_token "$audio_pid" || true)"
    if [[ "$current" != "$token" ]]; then
        rm -f "$AUDIO_PID_FILE"
        echo "[INFO] 已清除退出的语音进程记录"
        return 0
    fi
    kill -INT -- "-$audio_pid" 2>/dev/null || kill -INT "$audio_pid" 2>/dev/null || true
    for attempt in {1..30}; do
        current="$(process_token "$audio_pid" || true)"
        if [[ "$current" != "$token" ]]; then
            rm -f "$AUDIO_PID_FILE"
            echo "[OK] 导航启动的语音桥已停止"
            return 0
        fi
        sleep 0.2
    done
    # Keep the record so a later stop can retry; never report a live process as stopped.
    echo "[ERROR] 语音桥停止尚未确认，请检查 $AUDIO_LOG_FILE；PID 记录已保留"
    return 1
}

start_audio_bridge()
{
    local result prefix executable volume audio_pid token
    volume="${G1_AUDIO_VOLUME:-100}"
    [[ "$volume" =~ ^(-1|0|[1-9][0-9]?|100)$ ]] || {
        echo "[ERROR] G1_AUDIO_VOLUME 必须为 -1（保留当前音量）或 0..100"
        return 1
    }
    # Do not spawn another server when an existing one is still starting or
    # misconfigured. Exit 3 means no bridge/action was discovered at all.
    if python3 -m g1_task_manager.audio_readiness --timeout 2 --probe; then
        echo "[OK] 复用已运行的真实语音桥"
        return 0
    else
        result=$?
        [[ "$result" == 3 ]] || return "$result"
    fi
    if [[ -f "$AUDIO_PID_FILE" ]]; then
        read -r audio_pid token < "$AUDIO_PID_FILE" || true
        if [[ "${audio_pid:-}" =~ ^[1-9][0-9]*$ && -n "${token:-}"
              && "$(process_token "$audio_pid" || true)" == "$token" ]]; then
            echo "[ERROR] 已有导航语音进程，但 ROS 服务不可见；请检查网络/Domain 或先执行 stop"
            return 1
        fi
        rm -f "$AUDIO_PID_FILE"
    fi
    prefix="$(ros2 pkg prefix g1_audio_bridge)" || return 1
    executable="$prefix/lib/g1_audio_bridge/g1_audio_bridge"
    [[ -x "$executable" ]] || {
        echo "[ERROR] 找不到语音桥可执行文件，请重新构建：$executable"
        return 1
    }
    # Run the binary directly so its PID is the managed process, with no ros2
    # launcher intermediary. Close the lifecycle lock in the child.
    setsid "$executable" --ros-args -p dry_run:=false -p "volume:=$volume" \
        >"$AUDIO_LOG_FILE" 2>&1 </dev/null 9>&- &
    audio_pid=$!
    token="$(process_token "$audio_pid" || true)"
    if [[ -z "$token" ]]; then
        echo "[ERROR] 语音桥启动后立即退出"
        tail -n 80 "$AUDIO_LOG_FILE"
        return 1
    fi
    printf '%s %s\n' "$audio_pid" "$token" > "$AUDIO_PID_FILE"
    if python3 -m g1_task_manager.audio_readiness --timeout 10; then
        echo "[OK] 真实语音桥已启动，日志：$AUDIO_LOG_FILE"
        return 0
    fi
    echo "[ERROR] 语音桥未就绪，停止本次创建的语音进程"
    tail -n 80 "$AUDIO_LOG_FILE"
    stop_audio_bridge || true
    return 1
}

check_localization()
{
    python3 "$LOCALIZATION_HELPER" --once --timeout 5 || {
        echo "[ERROR] 当前定位无效或不新鲜，已拒绝启动/启用真机桥"
        return 1
    }
}

check_real_bridge()
{
    local value topic service
    value="$(timeout 8 ros2 param get /g1_cmd_vel_dry_run dry_run 2>/dev/null || true)"
    grep -Eq '^Boolean value is: False$' <<<"$value" || {
        echo "[ERROR] 同名节点不是 dry_run=False；请先停止 Dry Run 桥"
        return 1
    }
    topic="$(timeout 8 ros2 param get /g1_cmd_vel_dry_run cmd_vel_topic 2>/dev/null || true)"
    grep -Eq '^String value is: /cmd_vel_nav$' <<<"$topic" || {
        echo "[ERROR] 安全桥输入不是 /cmd_vel_nav"
        return 1
    }
    service="$(timeout 8 ros2 param get /g1_cmd_vel_dry_run enable_service_name 2>/dev/null || true)"
    grep -Eq '^String value is: /g1_loco_bridge/enable_real_nav$' <<<"$service" || {
        echo "[ERROR] 安全桥不是导航真机配置，启用服务不匹配"
        return 1
    }
}

check_nav()
{
    for n in \
        controller_server \
        planner_server \
        behavior_server \
        bt_navigator
    do
        state="$(timeout 8 ros2 lifecycle get "/$n" 2>/dev/null || true)"

        if ! grep -Eq '^active \[3\]'  <<<"$state"; then
            echo "[ERROR] $n 不是 active"
            exit 1
        fi
    done

    # grep 必须读完整个列表，避免提前退出触发 BrokenPipeError/pipefail 误判。
    ros2 topic list --no-daemon --spin-time 1 | grep -Fx /cmd_vel_nav >/dev/null || {
        echo "[ERROR] /cmd_vel_nav 不存在"
        exit 1
    }

    echo "[OK] Nav2 已准备好"
}

start_bridge()
{
    load_env
    check_nav
    check_localization

    if ros2 node list --no-daemon --spin-time 1 2>/dev/null |
        grep -Fx /g1_cmd_vel_dry_run >/dev/null
    then
        check_real_bridge || exit 1
        echo "[WARN] 真机安全桥已经运行"
        start_audio_bridge
        return
    fi

    echo
    echo "=========================================="
    echo "G1 REAL NAVIGATION"
    echo "=========================================="
    echo
    echo "请确认："
    echo "  1. 机器人运动模式已经由你手动切换"
    echo "  2. 周围没有人员和障碍物"
    echo "  3. 遥控器/急停在手边"
    echo
    echo "安全门启动后仍然保持关闭。"
    echo "=========================================="
    echo

    start_audio_bridge || return $?

    setsid ros2 run \
        g1_loco_bridge \
        g1_cmd_vel_dry_run \
        --ros-args \
        --params-file "$CFG" \
        >"$LOG_FILE" 2>&1 </dev/null 9>&- &

    pid=$!
    if ! token="$(process_token "$pid")"; then
        stop_audio_bridge
        return 1
    fi
    printf '%s %s\n' "$pid" "$token" > "$PID_FILE"

    sleep 3

    ros2 node list --no-daemon --spin-time 1 |
        grep -Fx /g1_cmd_vel_dry_run >/dev/null || {
            echo "[ERROR] real bridge 启动失败"
            tail -n 80 "$LOG_FILE"
            stop_bridge
            exit 1
        }

    check_real_bridge || {
        stop_bridge
        exit 1
    }

    echo "[OK] 真机安全桥已启动"
    echo "[OK] 安全门当前仍关闭"
}

enable_bridge()
{
    load_env
    check_nav
    check_real_bridge || exit 1
    check_localization

    echo
    echo "[WARN] 即将允许 Nav2 控制真实 G1"
    echo "[WARN] 机器人模式必须已经由你手动切换"
    echo

    timeout 15 ros2 service call \
        /g1_loco_bridge/enable_real_nav \
        std_srvs/srv/SetBool \
        "{data: true}"
}

disable_bridge()
{
    load_env

    timeout 8 ros2 service call \
        /g1_loco_bridge/enable_real_nav \
        std_srvs/srv/SetBool \
        "{data: false}" \
        2>/dev/null || true
}

stop_bridge()
{
    if load_env; then disable_bridge || true; fi

    if [[ -f "$PID_FILE" ]]; then
        local token current attempt
        read -r pid token < "$PID_FILE" || true
        current="$(process_token "$pid" || true)"
        if [[ -n "$current" && ( -z "${token:-}" || "$current" != "$token" ) ]]; then
            echo "[ERROR] 真机桥进程身份未确认，PID 记录保留"
            return 1
        fi
        if [[ -n "$current" ]]; then
            kill -INT -- "-$pid" 2>/dev/null ||
                kill -INT "$pid" 2>/dev/null ||
                true
            for attempt in {1..40}; do
                current="$(process_token "$pid" || true)"
                [[ "$current" == "$token" ]] || break
                sleep 0.1
            done
            if [[ "$current" == "$token" ]]; then
                echo "[ERROR] 真机桥退出未确认，PID 记录保留"
                return 1
            fi
        fi

        rm -f "$PID_FILE"
    fi

    echo "[OK] 真机安全桥已停止"
    stop_audio_bridge
}

status()
{
    load_env

    echo "===== Nav2 ====="

    for n in \
        controller_server \
        planner_server \
        behavior_server \
        bt_navigator
    do
        printf "%-22s " "$n"
        ros2 lifecycle get "/$n" 2>/dev/null ||
            echo "未运行"
    done

    echo
    echo "===== Real bridge ====="

    if ros2 node list --no-daemon --spin-time 1 2>/dev/null |
        grep -Fx /g1_cmd_vel_dry_run >/dev/null
    then
        ros2 param get \
            /g1_cmd_vel_dry_run \
            dry_run

        ros2 param get \
            /g1_cmd_vel_dry_run \
            cmd_vel_topic

        echo
        ros2 service list --no-daemon --spin-time 1 |
            grep g1_loco_bridge || true
    else
        echo "未运行"
    fi

    echo
    echo "===== Audio bridge ====="
    python3 -m g1_task_manager.audio_readiness --timeout 3 || true
    if [[ -f "$AUDIO_PID_FILE" ]]; then
        echo "管理方式：由导航启动，stop 将清理该进程"
    else
        echo "管理方式：外部实例由原启动者停止"
    fi
    echo "语音日志：$AUDIO_LOG_FILE"
}

logs()
{
    local file
    for file in "$LOG_FILE" "$AUDIO_LOG_FILE"; do
        echo "===== $file ====="
        if [[ -f "$file" ]]; then tail -n 100 "$file"; else echo "暂无日志"; fi
    done
}

case "${1:-}" in

    start)
        exec 9>"$RUNTIME/real_lifecycle.lock"
        flock -n 9 || { echo "[ERROR] 另一个真机 start/stop 正在执行"; exit 1; }
        start_bridge
        ;;

    enable)
        enable_bridge
        ;;

    disable)
        disable_bridge
        ;;

    stop)
        exec 9>"$RUNTIME/real_lifecycle.lock"
        flock -n 9 || { echo "[ERROR] 另一个真机 start/stop 正在执行"; exit 1; }
        stop_bridge
        ;;

    status)
        status
        ;;

    logs)
        logs
        ;;

    *)
        echo "用法："
        echo "  $0 start"
        echo "  $0 enable"
        echo "  $0 disable"
        echo "  $0 status"
        echo "  $0 logs"
        echo "  $0 stop"
        exit 1
        ;;
esac
