# StudyLamp 代码审查 & 待办清单

> 一次全项目代码审查(采集端 / 后端 / 小程序 / 工具 / 测试)的结论。
> **第一批已修复并提交**;**第二批 + 杂项**是已知但尚未处理的问题,按需推进。
> 勾选框可在 GitHub / VS Code 里直接点。

---

## ✅ 第一批:已修复(commit「Fix data-integrity bugs and add Raspberry Pi support」)

数据正确性 / 稳定性 / 跨平台,不改变对外行为契约,现有测试全绿。

- [x] 学习时长 `.seconds` 丢弃天数 → `total_seconds()` + 负值保护(`core/events.py`、`server/app.py`)
- [x] 同步与写入的数据丢失竞态 → sync 复用 `events.file_lock`,读-改-替换原子化(`core/sync.py`)
- [x] 摄像头资源泄漏 → `_loop` try/finally 释放句柄;单帧异常不崩线程;`stop()` 不再 use-after-close(`core/camera.py`)
- [x] 作业照片带骨骼线污染 OCR → 改用未标注原始帧(`core/camera.py`)
- [x] 配置热更新不生效 → camera/posture 改运行时读 `config.X`(`core/camera.py`、`core/posture.py`)
- [x] 颈部侧倾双重归一化 → 阈值直接比较(`core/posture.py`)
- [x] 后端 4 处重复聚合 → 抽 `_aggregate_events()` + `order_by`(`server/app.py`)
- [x] 跨平台数据目录 + `sys.executable` + 新建 `run_headless.py`(`config.py`、`ui/preview.py`)

---

## 🔴 第二批:上线运营前必须做(安全 / 鉴权)

**触发时机:真正对外给家长使用之前。** 这批工作量大、会改动前后端多处接口,需要先设计 token 方案,故与第一批分开。当前代码只适合本人/内网演示。

- [ ] **全站鉴权**:所有家长端接口目前无任何认证。任何人知道 `device_id` 就能查看孩子数据、**删库**(`DELETE /api/v1/data`)、删除绑定。需登录后签发 token(JWT/session),接口校验 token 且校验 `device_id` 归属该家长。(`server/app.py`)
- [ ] **真微信登录**:`app.js` 用 `code` 前 8 位当 openid —— code 每次变导致绑定丢失,前缀碰撞导致越权。需后端 `jscode2session` 换真 openid 并签发会话。(`miniprogram/app.js`、`server/app.py:/auth/login`)
- [ ] **禁止客户端自报 openid 作为身份**:`/children`、`/notify/*` 直接信任 body 里的 openid,可冒充任意家长、给任意人推微信。改为从 token 取身份。(`server/app.py`)
- [ ] **WebSocket 鉴权**:`ws://.../realtime/{device_id}` 任何人可连接监看任意设备;push 接口任何人可伪造状态。握手校验 token + 设备归属;push 仅允许采集端凭密钥。(`server/app.py`)
- [ ] **CORS 收紧**:`allow_origins=["*"]` → 收敛到小程序/后台白名单域名。(`server/app.py`)
- [ ] **文件上传校验**:作业上传无大小/类型限制,超大文件打爆内存;每次触发付费 Gemini 调用可被刷爆。加大小上限 + MIME/魔数校验 + 该接口单独限流 + `filename` 兜底。(`server/app.py`)
- [ ] **去掉 `eval()`**:徽章条件用 `eval` 执行,一旦条件可配置即 RCE。改比较函数/规则字典。(`server/points.py`)
- [ ] **积分幂等**:`/points/calc` 同一天调两次积分翻倍。先删当天流水再写,或加唯一约束 upsert。(`server/app.py`)

---

## 🟠 上生产/长期运行前该做(并发 / 性能)

**触发时机:多设备、长期 7×24 运行,或树莓派上跑几个月后。**

- [ ] **SQLite 并发写雪崩**:每个 `/events` 请求都 `threading.Thread` + 开新 session,无池无上限,配合 SQLite 全库锁会崩。开 WAL + `busy_timeout`;写入走后台任务队列(单消费线程/`BackgroundTasks`);生产迁 PostgreSQL。(`server/app.py`、`server/models.py`)
- [ ] **events.jsonl 无限增长**:每次统计全量读、每次同步全量重写。树莓派 SD 卡上几个月后卡顿。按日期分文件 / 定期归档已同步的旧事件。(`core/events.py`、`core/sync.py`)
- [ ] **缺数据库索引**:`StudyEvent` 建 `(device_id, timestamp)` 复合索引;`PointsLedger` 建 `(device_id, date)`。(`server/models.py`)
- [ ] **时区一致性**:服务端用 UTC 日期,客户端上传可能是本地时间,`startswith(date)` 匹配会错位漏统计。统一约定 UTC 或在比较时对齐时区。(`server/app.py`)
- [ ] **内存聚合改 SQL 聚合**:周报/积分把全部行拉进内存循环,数据量大后延迟线性上升。改 `func.sum`/`count`/`GROUP BY`。(`server/app.py`)
- [ ] **实时推送/后台线程**:采集端每采样周期新建线程做 HTTP 推送;服务端每请求新建线程。改长期单 worker + 队列。(`core/camera.py`、`server/app.py`)

---

## 🟡 杂项建议(不紧急,顺手可做)

- [ ] **测试不是真 pytest**:`test_*.py` 是脚本式(无 `assert`/`def test_`,末尾 `sys.exit`),`pytest` 收集不到还会崩。README 命令跑不通。改用 `python3 test_x.py` 直接跑(并修 README),或改造成真 pytest。端口写死(18765+)无法并行,建议用随机端口。
- [ ] **README 与实现不符**:架构图写 PostgreSQL,实际用 SQLite。改文档或注明「开发 SQLite,生产可切 PG」。
- [ ] **`tools/reset_dev.py` 删数据无二次确认**:`DELETE /api/v1/data` 可被环境变量指向生产。加交互确认或 `--force`。
- [ ] **`tools/check_setup.py` off-by-one**:`results[:10]` 把「数据目录可写」排除、却把摄像头算作必需,无摄像头 CI 会误报未就绪。
- [ ] **`start.sh` 仅 macOS**:`app` 模式起 rumps,树莓派上会失败。加平台检测或文档注明。
- [ ] **隐私声明与行为矛盾**:`privacy_check.py` 声称「不上传原始图片」且自查项恒 True,但实际上传了作业原图。对未成年人数据需如实声明 + 告知。
- [ ] **AppleScript 通知未转义**:`main.py` 的 `_notify` 把服务器返回文本直接插进 `display notification`,含引号会语法错误/注入。转义或换通知库。(仅 macOS)
- [ ] **弃用 API**:`@app.on_event("startup")` → `lifespan`;`datetime.utcnow()` → `datetime.now(timezone.utc)`。
- [ ] **小程序死代码**:`app.js:1` 顶层 `getApp()` 返回 undefined;`weekly.js` `barWidth()` 未被调用;`report.js` WebSocket 重连可能泄漏旧 `_pingTimer`。
- [ ] **统一日志**:全项目 `print` → `logging`;`except: pass` 吞异常改为至少记录。

---

## 做得好、无需改的地方

- `.gitignore` 完整(`.db`/`.env`/图片/`project.private.config.json` 全忽略),`studylamp.db` 与密钥均未入库。
- 架构分层清晰(采集/后端/小程序解耦),OCR/摄像头缺失能优雅降级。
- 小程序页面加载/错误/空态三态清晰,report 页生命周期正确清理 WebSocket。
- 工具脚本统一 argparse + 环境变量,导出报告用 `utf-8-sig` 兼容 Excel。

---

*本清单由一次全项目审查(2026-07)生成。第一批修复见对应 commit;其余按上述触发时机推进。*
