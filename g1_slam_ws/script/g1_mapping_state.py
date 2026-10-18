#!/usr/bin/env python3
"""Pure file/process inspection shared by the mapping CLI and web gateway."""
import json
import struct
from pathlib import Path
import sys


def process(pid, proc_root=Path('/proc')):
    try:
        fields = (proc_root / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        return {'state': fields[0], 'group': int(fields[2]), 'session': int(fields[3]), 'token': int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


def group_state(pid, token=None, proc_root=Path('/proc')):
    leader = process(pid, proc_root)
    if leader and leader['state'] != 'Z' and (token is None or leader['token'] != token):
        return 'unverified'
    members = []
    for entry in proc_root.iterdir():
        if entry.name.isdigit():
            item = process(int(entry.name), proc_root)
            if item and item['state'] != 'Z' and item['group'] == pid and item['session'] == pid:
                members.append(item)
    if members:
        if leader and (token is None or leader['token'] != token):
            return 'unverified'
        return 'running' if token is not None and all(item['token'] >= token for item in members) else 'unverified'
    return 'stopped'


def processes(path):
    result = []
    if not Path(path).exists():
        return result
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) not in (2, 3) or not parts[1].isdigit() or int(parts[1]) <= 1:
            raise ValueError('建图 PID 记录格式无效')
        token = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else None
        result.append({'name': parts[0], 'pid': int(parts[1]), 'token': token,
                       'state': group_state(int(parts[1]), token)})
    return result


def pcd_info(path):
    path = Path(path)
    stat = path.stat()
    header = {}
    with path.open('rb') as stream:
        for _ in range(40):
            line = stream.readline(1024)
            if not line:
                break
            text = line.decode('ascii', errors='replace').strip()
            if text and not text.startswith('#'):
                key, _, value = text.partition(' ')
                header[key.upper()] = value.strip()
                if key.upper() == 'DATA':
                    break
        offset = stream.tell()
    points = int(header.get('POINTS', '0'))
    if points <= 0 or not {'x', 'y', 'z'}.issubset(header.get('FIELDS', '').split()) or header.get('DATA') not in {'ascii', 'binary', 'binary_compressed'} or stat.st_size <= offset:
        raise ValueError('PCD 尚未写完或没有有效点云')
    sizes = [int(value) for value in header.get('SIZE', '').split()]
    counts = [int(value) for value in header.get('COUNT', ' '.join('1' for _ in sizes)).split()]
    if len(sizes) != len(header['FIELDS'].split()) or len(counts) != len(sizes) or any(v <= 0 for v in sizes + counts):
        raise ValueError('PCD 字段格式无效')
    expected = points * sum(size * count for size, count in zip(sizes, counts))
    if header['DATA'] == 'binary' and stat.st_size - offset < expected:
        raise ValueError('PCD 二进制内容尚未写完')
    if header['DATA'] == 'binary_compressed':
        with path.open('rb') as stream:
            stream.seek(offset)
            lengths = stream.read(8)
        if len(lengths) != 8:
            raise ValueError('PCD 压缩内容尚未写完')
        compressed, uncompressed = struct.unpack('<II', lengths)
        if uncompressed != expected or stat.st_size - offset - 8 < compressed:
            raise ValueError('PCD 压缩内容尚未写完')
    return {'bytes': stat.st_size, 'points': points, 'mtime_ns': stat.st_mtime_ns}


if __name__ == '__main__':
    try:
        command = sys.argv[1]
        if command == 'token':
            item = process(int(sys.argv[2]))
            if not item or item['state'] == 'Z':
                sys.exit(1)
            print(item['token'])
        elif command == 'check':
            state = group_state(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else None)
            sys.exit({'running': 0, 'stopped': 1, 'unverified': 2}[state])
        elif command == 'processes':
            print(json.dumps(processes(sys.argv[2]), ensure_ascii=False))
        elif command == 'pcd':
            print(json.dumps(pcd_info(sys.argv[2])))
        else:
            sys.exit(2)
    except (OSError, ValueError, IndexError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
