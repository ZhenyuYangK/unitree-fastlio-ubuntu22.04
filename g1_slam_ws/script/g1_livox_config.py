#!/usr/bin/env python3
"""Verify the selected host interface and write a local MID360 configuration."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    ws = Path(os.environ["G1_WS"]).resolve()
    interface = os.environ["G1_NETWORK_INTERFACE"]
    host = ipaddress.IPv4Address(os.environ["G1_HOST_IP"])
    lidar = ipaddress.IPv4Address(os.environ["G1_LIDAR_IP"])
    if host == lidar or host.is_unspecified or host.is_multicast or host.is_loopback:
        raise ValueError("主机和雷达必须使用不同的有效局域网 IPv4 地址")
    if lidar.is_unspecified or lidar.is_multicast or lidar.is_loopback:
        raise ValueError("雷达 IPv4 地址无效")
    result = subprocess.run(
        ["ip", "-j", "-4", "addr", "show", "dev", interface],
        check=True, capture_output=True, text=True,
    )
    interfaces = json.loads(result.stdout)
    addresses = [
        address for adapter in interfaces for address in adapter.get("addr_info", [])
        if address.get("family") == "inet" and address.get("local") == str(host)
    ]
    if not addresses:
        raise ValueError(f"网卡 {interface} 尚未配置 {host}；请检查网卡或 script/local.env")
    network = ipaddress.IPv4Network(f"{host}/{addresses[0]['prefixlen']}", strict=False)
    if lidar not in network or lidar in (network.network_address, network.broadcast_address):
        raise ValueError(f"雷达 {lidar} 不在网卡 {interface} 的可用子网 {network} 内")
    source = ws / "src/livox_ros_driver2/config/MID360_config.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    host_config = config["MID360"]["host_net_info"]
    for key in ("cmd_data_ip", "push_msg_ip", "point_data_ip", "imu_data_ip"):
        host_config[key] = str(host)
    if host_config.get("log_data_ip"):
        host_config["log_data_ip"] = str(host)
    config["lidar_configs"][0]["ip"] = str(lidar)
    output = Path(os.environ["G1_LIVOX_CONFIG"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] MID360: {interface} / {host} -> {lidar}")
    print(f"[OK] 雷达运行配置: {output}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"[ERROR] MID360 配置检查失败: {exc}", file=sys.stderr)
        sys.exit(1)
