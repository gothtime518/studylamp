# StudyLamp AI

智能学习监控系统 — 通过 AI 摄像头实时分析孩子学习状态，为家长提供学习报告和实时提醒。

初期以 Mac 桌面应用验证核心能力，最终目标集成到智能台灯硬件。

## 功能概览

- **坐姿检测** — 头部前倾、肩膀不平、颈部侧倾、驼背、距离过近
- **活动识别** — 区分学习、玩手机、发呆、离开
- **学习时间统计** — 自动记录 session，统计每日学习时长
- **实时推送** — WebSocket 状态推送 + 微信订阅消息告警
- **日报/周报** — AI 生成学习摘要，展示趋势
- **作业批改** — Gemini Vision 识别作业并给出分析建议
- **积分激励** — 学习积分、成就徽章、连续专注奖励
- **隐私优先** — 不上传原始视频，仅传结构化事件 JSON

## 系统架构

```
Mac/台灯摄像头 → 本地 AI (MediaPipe) → 事件存储 (JSONL)
                                            ↓
                                       云同步 (HTTPS)
                                            ↓
                                    FastAPI 后端 (PostgreSQL)
                                            ↓
                                    微信小程序 (家长端)
```

## 快速启动

### 前置依赖

- Python 3.10+
- 摄像头（Mac 内置或 USB）
- pip

### 1. 安装依赖

```bash
# 本地采集端
pip install -r requirements.txt

# 服务端
pip install -r server/requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入实际值
```

关键环境变量：

| 变量 | 说明 | 必须 |
|------|------|------|
| `GEMINI_API_KEY` | Gemini API 密钥（作业批改） | 否（无则跳过批改） |
| `WECHAT_APP_ID` | 微信小程序 AppID | 否（开发模式可跳过） |
| `WECHAT_APP_SECRET` | 微信小程序密钥 | 否 |
| `STUDYLAMP_SERVER` | 后端地址，默认 `http://localhost:8000` | 否 |
| `STUDYLAMP_DEVICE_ID` | 设备标识，默认 `mac-dev-001` | 否 |
| `STUDYLAMP_DB` | 数据库路径，默认 `./studylamp.db` | 否 |

### 3. 启动服务端

```bash
cd server
uvicorn app:app --host 0.0.0.0 --port 8000
```

或使用 Docker：

```bash
docker-compose up
```

### 4. 启动本地采集端（Mac 菜单栏应用）

```bash
python main.py
```

启动后会在菜单栏显示状态图标，点击可以：
- 开始/停止监测
- 打开预览窗口（查看骨骼线叠加效果）
- 查看今日统计
- 手动触发云同步

## 项目结构

```
studylamp/
├── main.py                  # Mac 菜单栏应用入口 (rumps)
├── config.py                # 全局配置（采样间隔、阈值等）
├── core/                    # 本地核心模块
│   ├── camera.py            #   摄像头采集主循环
│   ├── posture.py           #   坐姿检测 (MediaPipe Pose)
│   ├── activity.py          #   活动分类 (MediaPipe Hands + 规则/模型)
│   ├── events.py            #   事件存储 (JSONL)
│   ├── sync.py              #   云同步 + 实时状态推送
│   ├── ocr.py               #   作业 OCR (PaddleOCR)
│   ├── config_watcher.py    #   配置文件热更新
│   ├── cleanup.py           #   过期图片自动清理
│   └── privacy_check.py     #   隐私合规自查
├── server/                  # FastAPI 后端
│   ├── app.py               #   API 路由（事件、日报、作业、积分、WebSocket）
│   ├── models.py            #   数据库模型 (SQLAlchemy)
│   ├── homework_ai.py       #   Gemini Vision 作业批改
│   ├── ai_summary.py        #   AI 日报摘要生成
│   ├── points.py            #   积分计算 + 徽章
│   ├── wechat.py            #   微信消息推送
│   └── run.py               #   服务端启动脚本
├── miniprogram/             # 微信小程序（家长端）
│   ├── pages/index/         #   首页（实时状态）
│   ├── pages/report/        #   日报
│   ├── pages/weekly/        #   周报
│   ├── pages/homework/      #   作业分析
│   ├── pages/points/        #   积分/徽章
│   └── pages/bind/          #   设备绑定
├── ui/                      # 本地 UI
│   └── preview.py           #   预览窗口（骨骼线叠加）
├── tools/                   # 开发工具
│   ├── simulate_session.py  #   模拟学习会话
│   ├── collect_dataset.py   #   采集训练数据集
│   ├── train_activity.py    #   训练活动分类模型
│   ├── export_report.py     #   导出报告
│   ├── check_setup.py       #   环境检查
│   └── reset_dev.py         #   重置开发环境
├── test_*.py                # 测试文件
├── Dockerfile               # 服务端容器
├── docker-compose.yml       # Docker Compose 配置
└── .env.example             # 环境变量模板
```

## API 接口

### 采集端 → 云端

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/events` | POST | 批量上报事件 |
| `/api/v1/homework` | POST | 上传作业图片 |
| `/api/v1/realtime/{device_id}/push` | POST | 推送实时状态 |

### 云端 → 家长端

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/report/daily/{date}` | GET | 日报 |
| `/api/v1/report/weekly` | GET | 周报 |
| `/api/v1/realtime/{device_id}` | WebSocket | 实时状态 |
| `/api/v1/homework/{id}/analysis` | GET | 作业分析结果 |
| `/api/v1/points/summary` | GET | 积分概览 |
| `/api/v1/children` | GET/POST | 多孩子管理 |
| `/api/v1/data` | DELETE | 删除所有数据 |
| `/health` | GET | 健康检查 |

启动服务端后访问 `http://localhost:8000/docs` 查看完整 API 文档。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 本地 AI | MediaPipe Pose/Hands | 姿态检测 + 手部活动识别 |
| OCR | PaddleOCR | 中文手写识别 |
| 摄像头 | OpenCV | 跨平台 |
| 本地存储 | JSONL | 追加写入，无需数据库 |
| Mac 应用 | rumps | 菜单栏驻留 |
| 后端 | FastAPI + SQLAlchemy | 异步 API |
| 大模型 | Gemini 2.0 Flash | 作业批改 + 日报生成 |
| 推送 | 微信订阅消息 | 免费 |
| 家长端 | 微信小程序 | 无需安装 App |

## 开发进度

- [x] Phase 1：本地 MVP（坐姿检测、活动分类、事件系统）
- [x] Phase 2：云端 + 推送（FastAPI、WebSocket、微信小程序、积分）
- [x] Phase 3：作业分析（OCR + Gemini Vision 批改）
- [ ] Phase 4：产品化（隐私合规审核、硬件评估、用户测试）

## 开发工具

```bash
# 检查开发环境
python tools/check_setup.py

# 模拟一次学习会话（无需摄像头）
python tools/simulate_session.py

# 采集活动分类训练数据
python tools/collect_dataset.py

# 训练自定义活动分类模型
python tools/train_activity.py

# 重置开发数据
python tools/reset_dev.py
```

## 运行测试

```bash
pytest test_mock.py       # 单元测试（mock 摄像头）
pytest test_e2e.py        # 端到端测试
pytest test_points.py     # 积分系统测试
pytest test_ws.py         # WebSocket 测试
```
