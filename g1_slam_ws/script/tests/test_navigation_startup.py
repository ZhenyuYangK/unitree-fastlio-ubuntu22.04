"""Exercise shell entry points against a fake ROS graph, without hardware."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

import yaml


SCRIPT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = SCRIPT_DIR.parent

FAKE_ROS = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with open(os.environ["MOCK_CALLS"], "a") as stream:
    stream.write(json.dumps(args) + "\n")
runtime = Path(os.environ["MOCK_RUNTIME"])
nav = runtime / "nav_started"
bridge = runtime / "bridge_started"
if args[:2] == ["pkg", "prefix"]:
    print("/mock/install")
elif args[:2] == ["topic", "list"]:
    print("\n".join(("/livox/lidar", "/livox/imu", "/Odometry",
                      "/cloud_registered_body", "/global_pcd_map", "/map",
                      "/g1_relocalization/status", "/plan", "/cmd_vel_nav")))
elif args[:2] == ["node", "list"]:
    print("/map_server")
    if nav.exists():
        print("/controller_server")
    if bridge.exists() or os.environ.get("MOCK_EXISTING_BRIDGE"):
        print("/g1_cmd_vel_dry_run")
elif args[:2] == ["lifecycle", "get"]:
    print("active [3]")
elif args[:2] == ["param", "get"]:
    parameter = args[-1]
    dry = os.environ.get("MOCK_EXISTING_BRIDGE")
    if not dry:
        dry = bridge.read_text() if bridge.exists() else "True"
    if parameter == "dry_run":
        print("Boolean value is: " + dry)
    elif parameter == "cmd_vel_topic":
        print("String value is: " + os.environ.get("MOCK_BRIDGE_TOPIC", "/cmd_vel_nav"))
    elif parameter == "enable_service_name":
        print("String value is: /g1_loco_bridge/" + ("enable" if dry == "True" else "enable_real_nav"))
elif args[:2] == ["launch", "g1_nav2_bringup"]:
    nav.write_text("started")
elif args[:2] == ["run", "g1_loco_bridge"]:
    bridge.write_text("False" if any("nav2_real.yaml" in arg for arg in args) else "True")
elif args[:3] == ["run", "tf2_ros", "tf2_echo"]:
    print("Translation: [1.0, 2.0, 0.0]")
'''

FAKE_RCLPY = r'''
import json
import os
import time
from types import SimpleNamespace

counter = 0
def init(args=None):
    pass
def ok():
    return True
def shutdown():
    pass
def spin_once(node, timeout_sec=0.2):
    global counter
    sequence = os.environ.get("MOCK_STATUS_SEQUENCE", "TRACKING").split(",")
    item = sequence[min(counter, len(sequence) - 1)]
    counter += 1
    now = time.time_ns()
    if item == "NONE":
        time.sleep(min(timeout_sec, 0.01))
        return
    state = "TRACKING" if item in {"STALE", "OLD_SCAN"} else item
    status = {"state": state, "valid": state in {"TRACKING", "LOCALIZED"},
              "stamp_ns": now - (2_000_000_000 if item == "STALE" else 100_000_000),
              "last_success_stamp_ns": now - (4_000_000_000 if item == "OLD_SCAN" else 500_000_000),
              "reason": "mock " + item}
    node.callback(SimpleNamespace(data=json.dumps(status)))
    time.sleep(min(timeout_sec, 0.01))
'''

FAKE_NODE = r'''
import time
from types import SimpleNamespace

class Node:
    def __init__(self, name):
        self.name = name
    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=time.time_ns()))
    def create_subscription(self, message_type, topic, callback, qos):
        assert topic == "/g1_relocalization/status"
        self.callback = callback
        return callback
    def destroy_subscription(self, subscription):
        pass
    def destroy_node(self):
        pass
'''


class NavigationStartupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="g1-nav-startup-")
        self.root = Path(self.temp.name)
        self.ws = self.root / "g1_slam_ws"
        self.script = self.ws / "script"
        self.script.mkdir(parents=True)
        for name in ("g1_navigation.sh", "g1_navigation_real.sh", "g1_wait_localization.py"):
            shutil.copy2(SCRIPT_DIR / name, self.script / name)
        self.write(self.script / "g1_env.sh", r'''
            export G1_WS="${G1_WS}"
            g1_source_environment() { return 0; }
            g1_prepare_livox_config() { export G1_LIVOX_CONFIG="${G1_WS}/mock_livox.json"; }
            g1_start_rviz() { return 0; }
        ''')
        for relative in (
            "src/FAST_LIO_ROS2/config/mid360.yaml",
            "src/g1_relocalization/config/relocalization.yaml",
            "src/g1_nav2_bringup/config/nav2_params.yaml",
            "src/g1_nav2_bringup/rviz/navigation.rviz",
            "src/g1_loco_bridge/config/g1_loco_bridge_nav2_dry_run.yaml",
            "src/g1_loco_bridge/config/g1_loco_bridge_nav2_real.yaml",
        ):
            target = self.ws / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(WORKSPACE / relative, target)
        self.write(self.ws / "maps/map.pcd", "mock")
        self.write(self.ws / "maps/map_multilayer.pgm", "P2\n1 1\n255\n255\n")
        self.write(self.ws / "maps/map_multilayer.yaml", "image: map_multilayer.pgm\nresolution: 0.1\n")
        self.runtime = self.root / "mock_runtime"
        self.runtime.mkdir()
        self.calls_file = self.root / "calls.jsonl"
        self.calls_file.touch()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.write(self.bin / "ros2", FAKE_ROS, executable=True)
        self.write(self.bin / "sleep", "#!/usr/bin/env bash\nexit 0\n", executable=True)
        modules = self.root / "modules"
        self.write(modules / "rclpy/__init__.py", FAKE_RCLPY)
        self.write(modules / "rclpy/node.py", FAKE_NODE)
        self.write(modules / "rclpy/qos.py", '''
            class QoSProfile:
                def __init__(self, **values):
                    self.values = values
            class DurabilityPolicy:
                TRANSIENT_LOCAL = 1
            class ReliabilityPolicy:
                RELIABLE = 1
        ''')
        self.write(modules / "std_msgs/__init__.py", "")
        self.write(modules / "std_msgs/msg.py", "class String: pass\n")
        self.env = os.environ.copy()
        self.env.update({
            "G1_WS": str(self.ws),
            "G1_ENABLE_RVIZ": "0",
            "G1_LOCALIZATION_TIMEOUT_SEC": "0.1",
            "MOCK_CALLS": str(self.calls_file),
            "MOCK_RUNTIME": str(self.runtime),
            "PYTHONPATH": str(modules),
            "PATH": str(self.bin) + os.pathsep + self.env["PATH"],
        })

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, content, executable=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"))
        if executable:
            path.chmod(0o755)

    def run_script(self, command, real=False, **env):
        name = "g1_navigation_real.sh" if real else "g1_navigation.sh"
        return subprocess.run(
            ["bash", str(self.script / name), command], env={**self.env, **env},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
        )

    def calls(self):
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]

    def navigation_velocity_profiles(self):
        result = self.run_script("start-auto")
        self.assertEqual(result.returncode, 0, result.stdout)
        source = self.ws / "src/g1_nav2_bringup/config/nav2_params.yaml"
        generated = self.root / "generated_nav2.yaml"
        result = subprocess.run(
            [sys.executable, str(WORKSPACE / "src/g1_nav2_bringup/tools/generate_nav2_params.py"),
             str(source), str(generated)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        planners = {
            path.name: yaml.safe_load(path.read_text())["controller_server"]["ros__parameters"]["FollowPath"]
            for path in (source, generated, self.ws / "runtime/navigation/nav2_params_safe.yaml")
        }
        bridges = {
            mode: yaml.safe_load((self.ws / "src/g1_loco_bridge/config" /
                                  f"g1_loco_bridge_nav2_{mode}.yaml").read_text())
            ["g1_cmd_vel_dry_run"]["ros__parameters"]
            for mode in ("real", "dry_run")
        }
        return planners, bridges

    def test_navigation_acceleration_limits_agree_across_generated_configs(self):
        planners, bridges = self.navigation_velocity_profiles()
        for planner_name, planner in planners.items():
            for bridge_name, bridge in bridges.items():
                with self.subTest(planner=planner_name, bridge=bridge_name):
                    for axis in ("x", "theta"):
                        kind = "linear" if axis == "x" else "angular"
                        self.assertEqual(planner[f"acc_lim_{axis}"], bridge[f"max_{kind}_accel"])
                        self.assertEqual(-planner[f"decel_lim_{axis}"], bridge[f"max_{kind}_decel"])

    def test_navigation_speed_limits_fit_bridge_output_and_rejection_limits(self):
        planners, bridges = self.navigation_velocity_profiles()
        for planner_name, planner in planners.items():
            for bridge_name, bridge in bridges.items():
                with self.subTest(planner=planner_name, bridge=bridge_name):
                    self.assertEqual(planner["max_vel_x"], bridge["max_linear_x"])
                    self.assertEqual(planner["max_speed_xy"], planner["max_vel_x"])
                    self.assertEqual(planner["max_vel_theta"], bridge["max_angular_z"])
                    for axis, kind in (("x", "linear"), ("y", "linear"), ("z", "angular")):
                        self.assertGreater(bridge[f"reject_abs_{kind}_{axis}"],
                                           bridge[f"max_{kind}_{axis}"])

    def test_navigation_samples_both_lateral_directions_with_matching_bridge_limits(self):
        planners, bridges = self.navigation_velocity_profiles()
        for planner_name, planner in planners.items():
            for bridge_name, bridge in bridges.items():
                with self.subTest(planner=planner_name, bridge=bridge_name):
                    self.assertTrue(bridge["allow_lateral"])
                    self.assertFalse(bridge["allow_reverse"])
                    self.assertGreater(planner["max_vel_y"], 0.0)
                    self.assertEqual(planner["max_vel_y"], bridge["max_linear_y"])
                    self.assertEqual(planner["min_vel_y"], -bridge["max_linear_y"])
                    self.assertGreaterEqual(planner["vy_samples"], 3)
                    self.assertEqual(planner["vy_samples"] % 2, 1)
                    self.assertEqual(planner["acc_lim_y"], bridge["max_linear_accel"])
                    self.assertEqual(-planner["decel_lim_y"], bridge["max_linear_decel"])

    def nav_launched(self):
        return any(call[:2] == ["launch", "g1_nav2_bringup"] for call in self.calls())

    def initialpose_published(self):
        return any(call[:2] == ["topic", "pub"] and "/initialpose" in call for call in self.calls())

    def relocalization_args(self):
        return next(call for call in self.calls() if call[:2] == ["run", "g1_relocalization"])

    def test_auto_uses_global_search_without_initialpose(self):
        result = self.run_script("start-auto")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.nav_launched())
        self.assertFalse(self.initialpose_published())
        self.assertIn("initialization_mode:=global", self.relocalization_args())
        self.assertIn("global_search_timeout_sec:=0.1", self.relocalization_args())
        self.assertFalse((self.script / "auto_start_pose.env").exists())

    def test_failed_auto_preserves_base_stack_and_suggests_manual_fallback(self):
        result = self.run_script("start-auto", MOCK_STATUS_SEQUENCE="FAILED")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.nav_launched())
        self.assertFalse(self.initialpose_published())
        pids = (self.ws / "runtime/navigation/navigation.pids").read_text()
        for name in ("livox", "fast_lio", "relocalization", "map_server"):
            self.assertIn(name + " ", pids)
        self.assertIn("2D Pose Estimate", result.stdout)
        self.assertIn("continue", result.stdout)

    def test_ambiguous_auto_stops_before_nav2(self):
        result = self.run_script("start-auto", MOCK_STATUS_SEQUENCE="AMBIGUOUS")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.nav_launched())
        self.assertIn("AMBIGUOUS", result.stdout)

    def test_no_status_auto_times_out_before_nav2(self):
        result = self.run_script("start-auto", MOCK_STATUS_SEQUENCE="NONE")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.nav_launched())
        self.assertIn("超时", result.stdout)

    def test_manual_mode_remains_available(self):
        result = self.run_script("start")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("initialization_mode:=manual", self.relocalization_args())
        self.assertIn("2D Pose Estimate", result.stdout)
        self.assertFalse(self.initialpose_published())

    def test_fixed_mode_explicitly_publishes_saved_initialpose(self):
        self.write(self.script / "auto_start_pose.env", "AUTO_X=1\nAUTO_Y=2\nAUTO_YAW=0.5\n")
        result = self.run_script("start-fixed")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("initialization_mode:=manual", self.relocalization_args())
        self.assertTrue(self.initialpose_published())

    def test_auto_dry_starts_dry_bridge_after_readiness(self):
        result = self.run_script("start-auto-dry")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.nav_launched())
        self.assertEqual((self.runtime / "bridge_started").read_text(), "True")
        self.assertFalse(self.initialpose_published())

    def test_continue_ignores_old_success_log(self):
        self.write(self.ws / "runtime/navigation/logs/relocalization.log", "NDT success\n")
        result = self.run_script("continue", MOCK_STATUS_SEQUENCE="FAILED")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.nav_launched())

    def test_continue_waits_past_old_retained_status_for_fresh_message(self):
        result = self.run_script("continue", MOCK_STATUS_SEQUENCE="STALE,TRACKING")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.nav_launched())

    def test_continue_rejects_live_status_with_old_success_scan(self):
        result = self.run_script("continue", MOCK_STATUS_SEQUENCE="OLD_SCAN")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.nav_launched())
        self.assertIn("last_success_stamp_ns", result.stdout)

    def test_dry_continue_rejects_existing_real_bridge_before_nav2(self):
        result = self.run_script("continue-dry", MOCK_EXISTING_BRIDGE="False")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.nav_launched())
        self.assertIn("不是 dry_run=True", result.stdout)

    def test_real_start_rejects_existing_dry_bridge(self):
        result = self.run_script("start", real=True, MOCK_EXISTING_BRIDGE="True")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.runtime / "bridge_started").exists())
        self.assertIn("不是 dry_run=False", result.stdout)

    def test_real_start_and_enable_require_current_localization(self):
        for command in ("start", "enable"):
            result = self.run_script(command, real=True,
                                     MOCK_EXISTING_BRIDGE="False", MOCK_STATUS_SEQUENCE="FAILED")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("已拒绝启动/启用真机桥", result.stdout)
        self.assertFalse(any(call[:2] == ["service", "call"] for call in self.calls()))
        self.assertFalse((self.runtime / "bridge_started").exists())


if __name__ == "__main__":
    unittest.main()
