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
LOCALIZATION_HELPER="${SCRIPT_DIR}/g1_wait_localization.py"

mkdir -p "$LOG_DIR"

load_env() { g1_source_environment; }

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

    setsid ros2 run \
        g1_loco_bridge \
        g1_cmd_vel_dry_run \
        --ros-args \
        --params-file "$CFG" \
        >"$LOG_FILE" 2>&1 </dev/null &

    pid=$!
    echo "$pid" > "$PID_FILE"

    sleep 3

    ros2 node list --no-daemon --spin-time 1 |
        grep -Fx /g1_cmd_vel_dry_run >/dev/null || {
            echo "[ERROR] real bridge 启动失败"
            tail -n 80 "$LOG_FILE"
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
        pid="$(cat "$PID_FILE")"

        if kill -0 "$pid" 2>/dev/null; then
            kill -INT -- "-$pid" 2>/dev/null ||
                kill -INT "$pid" 2>/dev/null ||
                true
        fi

        rm -f "$PID_FILE"
    fi

    echo "[OK] 真机安全桥已停止"
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
}

logs()
{
    tail -n 150 "$LOG_FILE"
}

case "${1:-}" in

    start)
        start_bridge
        ;;

    enable)
        enable_bridge
        ;;

    disable)
        disable_bridge
        ;;

    stop)
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
