#!/usr/bin/env python3
"""Wait for fresh, successful localization reported by the running ROS node."""

import argparse
import json
import math
import sys
import time


STATUS_TOPIC = "/g1_relocalization/status"
READY_STATES = {"LOCALIZED", "TRACKING"}


def stamp_problem(status, field, now_ns, age_sec):
    stamp = status.get(field)
    if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp <= 0:
        return f"{field} 无效"
    age = now_ns - stamp
    if age < 0:
        return f"{field} 来自未来"
    if age > int(age_sec * 1_000_000_000):
        return f"{field} 已过期 ({age / 1e9:.2f} 秒)"
    return None


def assess_status(status, now_ns, status_age_sec=1.0, scan_age_sec=3.0):
    """Return (ready, reason), rejecting stale, malformed and future samples."""
    if not isinstance(status, dict):
        return False, "定位状态必须是 JSON 对象"
    if isinstance(now_ns, bool) or not isinstance(now_ns, int) or now_ns <= 0:
        return False, "当前 ROS 时钟无效"
    state = status.get("state", "UNKNOWN")
    if not isinstance(state, str):
        return False, "定位 state 必须是字符串"
    reason = str(status.get("reason", ""))
    problem = stamp_problem(status, "stamp_ns", now_ns, status_age_sec)
    if problem:
        return False, f"{state}: {problem}"
    if status.get("valid") is not True or state not in READY_STATES:
        return False, f"{state}: {reason or '尚未确认定位'}"
    problem = stamp_problem(status, "last_success_stamp_ns", now_ns, scan_age_sec)
    if problem:
        return False, f"{state}: {problem}"
    if status["last_success_stamp_ns"] > status["stamp_ns"]:
        return False, f"{state}: 成功扫描时间晚于状态发布时间"
    return True, f"{state}: 定位有效，最近成功扫描仍新鲜"


def positive_seconds(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("必须是有限的正数")
    return result


def terminal_failure(status, now_ns):
    """Only final failure states end the wait; candidate verification/retry keep waiting."""
    return (isinstance(status, dict)
            and isinstance(status.get("state"), str)
            and status["state"] in {"FAILED", "AMBIGUOUS"}
            and stamp_problem(status, "stamp_ns", now_ns, 1.0) is None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=positive_seconds)
    parser.add_argument(
        "--once", action="store_true", help="检查当前实时就绪状态（建议同时设置 --timeout 5）"
    )
    args = parser.parse_args(argv)
    args.timeout = args.timeout if args.timeout is not None else (5.0 if args.once else 180.0)

    # Keep the validation function importable for offline checks without ROS.
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String
    except ImportError as error:
        print(f"[ERROR] 无法加载 ROS Python 环境：{error}", file=sys.stderr)
        return 2

    rclpy.init(args=[])
    node = Node("g1_navigation_wait_localization")
    result = None
    last_reason = f"未收到 {STATUS_TOPIC}"
    last_report = None

    def report(reason):
        nonlocal last_report
        if reason != last_report:
            print(f"[G1-LOCALIZATION] {reason}", flush=True)
            last_report = reason

    def on_status(message):
        nonlocal result, last_reason
        try:
            status = json.loads(message.data)
        except (TypeError, ValueError):
            last_reason = "收到无效的定位状态 JSON"
            report(last_reason)
            return
        now_ns = node.get_clock().now().nanoseconds
        ready, last_reason = assess_status(status, now_ns)
        report(last_reason)
        if ready:
            result = 0
        elif terminal_failure(status, now_ns):
            result = 1

    qos = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    subscription = node.create_subscription(String, STATUS_TOPIC, on_status, qos)
    deadline = time.monotonic() + args.timeout
    try:
        while rclpy.ok() and result is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            rclpy.spin_once(node, timeout_sec=min(0.2, remaining))
        if result is None:
            print(f"[ERROR] 等待定位状态超时：{last_reason}", file=sys.stderr)
            return 1
        return result
    except KeyboardInterrupt:
        return 130
    finally:
        node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
