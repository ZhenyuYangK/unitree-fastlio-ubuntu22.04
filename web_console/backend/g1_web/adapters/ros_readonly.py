"""Humble telemetry adapter. No publishers, motion clients or process launches."""
import json
import threading
import time

from .base import RobotAdapter, empty_mission
from ..control import GatewayError


def localization_view(raw, now_ns, receive_age):
    def fresh(key, limit):
        stamp = raw.get(key)
        return type(stamp) is int and stamp > 0 and -0.05 <= (now_ns - stamp) / 1e9 <= limit

    stale = receive_age > 1.0 or not fresh("stamp_ns", 1.0) or not fresh("last_success_stamp_ns", 3.0)
    state = raw.get("state")
    return dict(raw, stale=stale,
                valid=not stale and raw.get("valid") is True and isinstance(state, str)
                and state in {"LOCALIZED", "TRACKING"})


class RosReadOnlyAdapter(RobotAdapter):
    def __init__(self):
        self.lock = threading.Lock()
        self.localization = {"state": "UNKNOWN", "valid": False, "reason": "等待定位数据"}
        self.localization_at = self.mission_at = 0.0
        self.mission = empty_mission(False)
        self.pending = None
        self.started_at = time.time()

    async def start(self):
        try:
            import rclpy
            from rclpy.context import Context
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.node import Node
            from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
            from std_msgs.msg import String
            from g1_task_interfaces.srv import GetMissionState
        except ImportError as exc:
            raise RuntimeError("ROS 只读模式需要已编译并加载的 Humble 工作空间及 rclpy") from exc
        self.rclpy, self.service_type = rclpy, GetMissionState
        self.context = Context()
        rclpy.init(context=self.context)
        self.node = Node("g1_web_readonly", context=self.context)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.subscription = self.node.create_subscription(
            String, "/g1_relocalization/status", self._localization, qos)
        self.client = self.node.create_client(GetMissionState, "/g1_task/get_state")
        self.timer = self.node.create_timer(0.5, self._poll)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, name="g1-web-ros", daemon=True)
        self.thread.start()

    def _localization(self, message):
        try:
            data = json.loads(message.data)
            if not isinstance(data, dict):
                return
            # Reject NaN / Infinity rather than breaking the JSON snapshot stream.
            json.dumps(data, allow_nan=False)
        except (ValueError, TypeError):
            return
        with self.lock:
            self.localization, self.localization_at = data, time.monotonic()

    def _poll(self):
        if self.pending is not None and not self.pending.done():
            if time.monotonic() - self.pending_at < 2.0:
                return
            self.client.remove_pending_request(self.pending)
            self.pending.cancel()
        if self.client.service_is_ready():
            self.pending_at = time.monotonic()
            self.pending = self.client.call_async(self.service_type.Request())
            self.pending.add_done_callback(self._mission)

    def _mission(self, future):
        if future.cancelled() or future.exception() is not None:
            return
        response = future.result()
        fields = ("active", "simulated", "run_id", "mission_id", "mission_name", "state",
                  "current_step", "total_steps", "current_waypoint", "next_waypoint", "wait_id", "message")
        with self.lock:
            self.mission.update({key: getattr(response, key) for key in fields})
            self.mission_at = time.monotonic()

    async def snapshot(self):
        now = time.monotonic()
        with self.lock:
            localization = localization_view(self.localization, self.node.get_clock().now().nanoseconds,
                                             now - self.localization_at)
            mission = dict(self.mission, stale=now - self.mission_at > 2.0)
        return {"simulated": False, "localization": localization, "mission": mission, "pose": None,
                "logs": [{"time": self.started_at, "message": "ROS 只读：未发送运动、语音、任务或进程控制命令"}],
                "capabilities": {"mission_control": False, "process_control": False,
                                 "waypoint_write": False, "teleop": False, "video": False},
                "map": {"available": False, "simulated": False, "id": None}}

    async def catalog(self):
        try:
            from g1_task_manager.paths import get_default_waypoints_file, default_missions_file
            from g1_task_manager.waypoint_store import WaypointStore
            from g1_task_manager.mission_store import load_missions
            store = WaypointStore(get_default_waypoints_file()).load()
            missions = load_missions(default_missions_file(), store)
            return {"simulated": False, "map_id": store.map_id, "frame_id": store.frame_id,
                    "waypoints": [dict(value, id=key) for key, value in store.list_waypoints()],
                    "missions": [{"id": key, "name": value["name"],
                                  "waypoints": [step["waypoint"] for step in value["steps"]]}
                                 for key, value in missions.items()]}
        except Exception as exc:
            raise GatewayError(503, "CATALOG_UNAVAILABLE", "现场导航点或任务配置不可用，请检查后端配置") from exc

    async def close(self):
        if hasattr(self, "executor"):
            self.executor.shutdown(timeout_sec=2.0)
            self.thread.join(timeout=2.0)
        if hasattr(self, "node"):
            self.node.destroy_node()
        if hasattr(self, "context"):
            self.context.try_shutdown()
