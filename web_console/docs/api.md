# G1 Web Gateway API v0.1

状态为“已实现”的接口可在本次框架运行。“占位”接口固定拒绝，不运行机器人命令；“规划”路径尚未注册。

## 传输和访问

- 页面、`/api/v1`、`/ws/state` 同源；不启用任意 CORS。
- 本机 local / mock 可以无口令；非回环监听地址以及 ros_readonly 模式必须设置 G1_WEB_TOKEN。
- `POST /api/v1/session` 用口令换取 12 小时 HttpOnly、SameSite=Strict Cookie；口令不放 URL 或浏览器存储。
- HTTP 写请求和 WebSocket 检查浏览器 Origin；请求体拒绝额外字段。
- 演示启动器提供 HTTP。正式 HTTPS 终止和访问权限属于真机控制接入阶段，配置 HTTPS 后设置 G1_WEB_COOKIE_SECURE=1。
- 无账号角色管理、登录限流或持久会话；本框架不作为公网入口。

## 已实现接口

| 方法/路径 | 用途 | 模式 |
| --- | --- | --- |
| GET /api/v1/health | 服务存活、模式与 schema_version | 无需会话；不代表机器人就绪 |
| GET /api/v1/session | 查询当前会话是否认证 | 所有模式 |
| POST /api/v1/session | {token} 登录 | 所有模式 |
| DELETE /api/v1/session | 注销当前会话 | 所有模式 |
| GET /api/v1/state | 获取最新状态信封 | 所有模式 |
| GET /api/v1/catalog | 地图标识、导航点、任务目录 | 所有模式；配置缺失返回 503 |
| GET /api/v1/openapi.json | 认证后的机器可读 HTTP 契约 | 所有模式 |
| POST /api/v1/control/acquire | {owner} 取得控制权，返回 lease_id、expires_in | 所有模式；local/ROS 用于配置编辑 |
| POST /api/v1/control/renew | 续租 | 已持有租约的设备 |
| POST /api/v1/control/release | 释放 | 同上 |
| POST /api/v1/missions/start | 开始模拟任务 | 仅 mock |
| POST /api/v1/missions/continue | 放行当前站点 | 仅 mock |
| POST /api/v1/missions/cancel | 取消指定运行 | 仅 mock |
| POST /api/v1/operations | 进程操作白名单占位 | 所有模式返回 501 |
| WS /ws/state | 每 0.5 秒最新状态；重连先发全量快照 | 所有模式；不接收控制命令 |

额外已实现的现场数据接口：

| 方法/路径 | 用途 | 模式 |
| --- | --- | --- |
| GET /api/v1/map | PGM 对应的像素尺寸、分辨率、origin、版本和图片地址 | local / ros_readonly |
| GET /api/v1/map/image?version=... | 实际 PGM 转换的 PNG；ETag/304；旧图片版本返回 409 | local / ros_readonly |
| POST /api/v1/waypoints | 新增 {id,name,x,y,yaw} | local / ros_readonly |
| PUT /api/v1/waypoints/{id} | 更新 {name,x,y,yaw}，保留采样元数据 | local / ros_readonly |
| DELETE /api/v1/waypoints/{id} | 删除未被任务引用的点 | local / ros_readonly |
| POST /api/v1/missions | 新增 {id,name,steps} | local / ros_readonly |
| PUT /api/v1/missions/{id} | 更新 {name,steps}，steps 沿用现有任务 YAML 结构 | local / ros_readonly |
| DELETE /api/v1/missions/{id} | 删除任务配置 | local / ros_readonly |

GET /catalog 返回 source=workspace、revision、files、导航点及任务的原始 steps；响应带 ETag。所有配置写入须同时携带 X-Control-Lease 与 If-Match（catalog 的 revision）。缺版本返回 428，版本变化返回 409，不覆盖打开编辑窗口后的其他修改。成功返回 {saved,revision,catalog,backup,message}。

保存先在临时文件调用现有 WaypointStore/load_missions 校验，备份两个原文件，再原子替换被编辑的单个 YAML。修改任务和导航点共享一个配置版本；任务锁、CLI 写入锁或 recovery_required 标记存在时拒绝保存。POST 重试使用相同 ID 会冲突，不自动重发。地图像素不提供编辑接口。

控制权凭证通过 `X-Control-Lease` 请求头传递，不出现在快照中。首版租约 15 秒，建议 5 秒续租。

## 命令示例

开始：

```json
{
  "request_id": "045de9a2-203c-4228-855b-76222f9fc66f",
  "mission_id": "five_point_tour"
}
```

人工放行：

```json
{
  "request_id": "79134957-5c34-44c5-88fb-a7ce1d9c58b9",
  "run_id": "从最新任务状态获取",
  "wait_id": "从最新 WAITING_FOR_CONTINUE 状态获取"
}
```

取消：`{request_id, run_id}`。所有 request_id 必须为 UUID v4。

成功返回 HTTP 202：`{accepted: true, simulated: true, request_id, operation_id, run_id, message}`。表示已接受，最终执行结果通过状态查询。页面不自动重试命令。

同一租约和 request_id 的重试在 10 分钟、最多 256 条的内存缓存内返回原响应；换命令内容返回 REQUEST_ID_CONFLICT。租约仍须有效。网关重启会清空缓存，真机接入前须加入持久命令记录和恢复核对。

## 状态信封

```json
{
  "type": "state",
  "schema_version": 1,
  "instance_id": "每次后台实例重新生成",
  "sequence": 42,
  "server_time": 1790000000.0,
  "data": {
    "mode": "mock",
    "simulated": true,
    "localization": {"state": "TRACKING", "valid": true, "stale": false},
    "pose": {"x": 2.0, "y": 2.0, "yaw": 0.0},
    "mission": {
      "active": true,
      "simulated": true,
      "run_id": "...",
      "mission_id": "five_point_tour",
      "mission_name": "五站双语讲解巡航",
      "state": "WAITING_FOR_CONTINUE",
      "current_step": 1,
      "total_steps": 5,
      "current_waypoint": "point_01",
      "next_waypoint": "point_02",
      "wait_id": "...",
      "message": "等待放行",
      "gate_closed": true,
      "goals_terminal": true,
      "distance_remaining": null
    },
    "control": {"held": true, "owner": "浏览器 A", "remaining_sec": 12.0},
    "map": {"available": true, "simulated": true, "id": "demo_map"},
    "capabilities": {"mission_control": true, "process_control": false, "waypoint_write": false, "teleop": false, "video": false},
    "logs": []
  }
}
```

- 前端用 instance_id 识别网关重启，丢弃旧租约；同一实例内丢弃 sequence 较旧的数据。
- local 模式默认加载现场地图和配置，pose=null，定位/任务未知。ros_readonly 在同一地图与配置基础上接入 ROS 定位及任务状态；机器人运动命令仍返回 501。
- data.configuration 包含 available、revision、error、write_blocker；前端根据版本变化重取目录。data.map 含地图资源版本，原图或 YAML 变化后自动刷新。waypoint_write / mission_write 表示文件编辑能力。
- 未接入可靠机器人来源时 gate_closed/goals_terminal 为 null，不显示确认成功。
- ROS 定位检查接收间隔、stamp_ns、last_success_stamp_ns 和状态；超过 1 秒未更新或成功扫描超过 3 秒则 valid=false。
- ROS 任务服务超过 2 秒没有有效响应则 mission.stale=true。状态过期不意味着任务已经停止。
- WS 认证失败关闭码 4401，Origin 不匹配为 4403；登录过期后重新认证。

## 错误

```json
{"error": {"code": "STALE_WAIT", "message": "任务或等待标识已过期，请重新查询状态"}}
```

401：会话/口令错误；403：来源不符；404：任务不存在；409：租约、任务互斥或标识冲突；422：请求体或配置校验失败；428：缺少 If-Match 版本；501：功能未接入；503：现场配置不可用。

## 规划接口（当前未注册）

- 实时 TF/规划路径状态。
- POST /waypoints/record，使用机器人实时位置采样。
- GET /operations/{operation_id} 与后台进程操作队列。
- POST /navigation/initial-pose、运动桥就绪与启用/禁用接口。
- POST /audio/speak 与终止结果。
- 后续真实 RobotAdapter 使用现有 ROS Action/Service；禁止将 mock 结果用于真机确认。
