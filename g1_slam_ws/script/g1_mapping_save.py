#!/usr/bin/env python3
"""Check Trigger.success and a newly written, nonempty PCD, not ros2 CLI exit status."""
import argparse
from pathlib import Path
import time

from g1_mapping_state import pcd_info


def save(path, timeout=120):
    import rclpy
    from std_srvs.srv import Trigger
    path = Path(path)
    before = (path.stat().st_mtime_ns, path.stat().st_size, path.stat().st_ino) if path.exists() else None
    rclpy.init(args=[])
    node = rclpy.create_node('g1_mapping_save_client')
    try:
        client = node.create_client(Trigger, '/map_save')
        if not client.wait_for_service(timeout_sec=8):
            raise RuntimeError('/map_save 服务不可用')
        future = client.call_async(Trigger.Request())
        deadline = time.monotonic() + timeout
        while not future.done() and rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not future.done():
            raise RuntimeError('保存响应超时，结果未知；请核对文件后重试，建图进程保留')
        response = future.result()
        if not response.success:
            raise RuntimeError('建图节点拒绝保存：' + response.message)
        deadline = time.monotonic() + 3
        while True:
            try:
                current = path.stat()
                if (current.st_mtime_ns, current.st_size, current.st_ino) == before:
                    raise ValueError('PCD 文件尚未更新')
                result = pcd_info(path)
                print('[OK] 已保存 {} 个点，{} 字节：{}'.format(result['points'], result['bytes'], path))
                return
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('保存未生成新的有效 PCD；已有旧文件不能作为保存成功依据')
                time.sleep(0.1)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        save(args.output)
    except (RuntimeError, OSError, ValueError) as exc:
        parser.exit(1, '[ERROR] ' + str(exc) + '\n')
