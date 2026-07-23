# StudyLamp 部署指南（保姆级）

> 面向「只负责把软件集成到硬件上」的你。不需要懂电路、不需要焊接、不需要碰 Pico。
> 本文档假设你**从没用过树莓派、没部署过后端、没发过小程序**，每一步都写清楚「敲什么命令、看到什么算成功」。

---

## 📋 进度清单

策略：**先跑通「阶段一 本地联调」（零成本，把整条链路打通），确认 OK 后再做「阶段二 上生产」。** 每做完一项就把 `[ ]` 改成 `[x]`（GitHub / VS Code 里可直接点击勾选）。

### 阶段一：本地联调（零成本，只用你的电脑 + 树莓派 + 同一 WiFi）
- [ ] 后端在电脑上跑起来，浏览器打开 `http://localhost:8000/docs` 能看到 API 文档 → [见 §2](#2-后端-server)
- [ ] 树莓派能开机，能 SSH 进去 或 接显示器进入桌面 → [见 §3.2](#32-连上树莓派两种方式任选)
- [ ] 树莓派装好系统依赖和 Python 依赖 → [见 §3.3–3.5](#33-准备系统环境)
- [ ] 改好 3 处 Mac 专属代码，摄像头测试出画面 → [见 §3.6–3.7](#36-改-3-处-mac-专属代码关键)
- [ ] 树莓派跑 `run_headless.py`，事件能上传到电脑后端（后端日志能看到）→ [见 §3.8](#38-跑起来)
- [ ] 小程序（开发者工具开发版）能连上后端，看到实时状态/数据 → [见 §4](#4-小程序-miniprogram)

### 阶段二：上生产（确认阶段一整条链路 OK 后再做）
- [ ] 买云服务器 + 配好域名 + HTTPS 证书 → [见 §2.3](#23-后端部署到哪)
- [ ] 后端 3 处生产化改动：CORS 收紧 / 数据库 / 微信真登录 → [见 §2.2](#22-上生产必须改的-3-处)
- [ ] 树莓派配开机自启（systemd），插电即跑 → [见 §3.9](#39-配置开机自启插电就自动跑)
- [ ] 小程序配域名白名单 → 上传 → 提交审核 → 发布 → [见 §4.2](#42-小程序怎么部署和普通程序不一样)

---

## 1. 全局：三块东西，三个「家」

你的 StudyLamp 不是「一个程序」，而是**三个独立部件**，分别部署在三个地方：

```
① 采集端 (core/)        → 装在【树莓派】上，放在孩子书桌
② 后端 (server/)        → 装在【一台公网能访问的服务器】上   ← 你现在缺这个「家」
③ 小程序 (miniprogram/) → 上传到【微信】，在家长手机里
                    │
   ①树莓派 ──上传事件──▶ ②后端 ◀──拉数据── ③小程序
```

**关键规律**：①树莓派 和 ③小程序 **都要连 ②后端**。所以：
- **部署顺序必须是 后端 → 树莓派 → 小程序**（后两者都要填后端地址）。
- 后端要放在「公网能访问 + 有 HTTPS 域名」的地方——因为**微信小程序强制要求后端是 `https://`**，且不能放在家里的普通宽带（没有公网 IP）。

配套硬件（照片里那块板子 + 线材）：

| 物件 | 用途 | 何时用 |
|---|---|---|
| 树莓派（Pi 4/5，非 Pico） | 跑采集端 AI | 一直用 |
| 树莓派电源线 | 供电（**必须用原装，别用手机充电器**） | 一直用 |
| HDMI 线 | 接显示器 | 首次配置（之后可拔） |
| 摄像头数据线（USB） | 接 USB 摄像头 | 一直用 |
| 树莓派调试线（USB 转串口） | 高级调试 | 一般用不到，先无视 |

> **⚠️ 供电铁律**：只用配套的树莓派电源。电源不足会导致跑 AI 时突然重启、SD 卡损坏、检测卡顿——症状隐蔽，容易误以为是代码 bug。

---

## 2. 后端 server/

后端是**先部署的一块**，因为树莓派和小程序都要连它。

### 2.1 好消息：代码基本不用改就能跑
读过 `server/app.py`，部署常踩的坑你已处理好：CORS 已开、监听 `0.0.0.0`、有 Docker + docker-compose、有 `/health` 健康检查、有限流。

**本地/服务器起后端**（在项目根目录）：
```bash
# 方式一：Docker（推荐，一条命令）
cp .env.example .env      # 然后编辑 .env 填入密钥（见下）
docker-compose up -d      # 后台启动
# 访问 http://localhost:8000/docs 确认活着

# 方式二：直接跑（开发用）
pip install -r server/requirements.txt
python3 server/run.py     # 默认 0.0.0.0:8000
```

`.env` 关键变量（`.env.example` 已列全，没有的可留空）：

| 变量 | 说明 | 必须 |
|---|---|---|
| `GEMINI_API_KEY` | 作业批改用，没有则跳过批改 | 否 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信推送，没有则跳过 | 否 |
| `WECHAT_TEMPLATE_ALERT` / `_DAILY` | 微信模板消息 ID | 否 |
| `STUDYLAMP_DB` | 数据库路径 | 否（默认 SQLite 文件） |

### 2.2 上生产必须改的 3 处
本地联调不用管这些，**上线前**再改：

| # | 问题 | 现状 | 上线改法 |
|---|---|---|---|
| 1 | 数据库是 SQLite 单文件 | `studylamp.db` | 短期够用（docker 卷已持久化）。长期/多设备建议换 PostgreSQL（README 也这么规划） |
| 2 | CORS 全开 | `allow_origins=["*"]`（`app.py`） | 收紧到你自己的域名，否则任何网站都能调你的 API |
| 3 | 微信登录是假的 | `app.js` 里 `tmpOpenid = 'user_' + code.slice(0,8)` | 后端补一个 `/api/v1/login`，用小程序传来的 `code` 向微信换取真 `openid` |

### 2.3 后端部署到哪？
- **A. 云服务器（推荐上线用）**：买最便宜的云主机（阿里云/腾讯云轻量应用服务器，几十元/月），装 Docker → `docker-compose up -d`。**必须配域名 + HTTPS**（微信强制要求 `https://`）。
- **B. 你的电脑（阶段一联调用）**：够测试。树莓派和电脑连**同一 WiFi**，树莓派的 `STUDYLAMP_SERVER` 填电脑局域网 IP（如 `http://192.168.1.20:8000`，用 `ipconfig getifaddr en0` 查 Mac 的 IP）。电脑关机就断，仅联调用。
- **C. Serverless**：改造成本高，先不考虑。

---

## 3. 采集端（树莓派）

把现在在 Mac 上跑的 `core/` 代码搬到树莓派上跑起来。

### 3.1 判断是 Pi 4 还是 Pi 5、装的什么系统

- **情况 A：已装好系统（别人配好给你的）** → 直接跳 §3.2。
- **情况 B：裸板 + 空 microSD 卡** → 需先「烧系统」。在你的 **Mac** 上：
  1. 下载 **Raspberry Pi Imager**：https://www.raspberrypi.com/software/
  2. 插入 microSD 卡（可能需读卡器）
  3. 打开 Imager：设备选 Pi 4/5；系统选 **`Raspberry Pi OS (64-bit)`（必须 64 位，MediaPipe 需要）**；存储选 SD 卡
  4. 点齿轮 ⚙️ 预配（关键，省得接显示器）：主机名 `studylamp`；✅启用 SSH（密码登录）；用户名 `pi` + 密码；✅配置 WiFi（家里 WiFi 名 + 密码）；设时区
  5. 烧录 → 完成后把卡插回树莓派，接电源开机
- **情况 C：不确定** → 按情况 B 重烧一张，保证是干净 64 位系统。

### 3.2 连上树莓派（两种方式任选）

**方式一：接显示器当普通电脑用（新手首次推荐）**
接 HDMI + USB 键鼠 → 插电开机 → 打开桌面「终端」，后续命令都在这敲。

**方式二：从 Mac 远程连（SSH，配好后最方便）**
前提：树莓派和 Mac 同一 WiFi，且烧系统时开了 SSH。Mac 终端里：
```bash
ssh pi@studylamp.local
# 第一次问 yes/no 输 yes；输密码（不显示是正常的）
```
连不上就用 IP：`ssh pi@<IP>`（IP 在路由器后台看，或接显示器后 `hostname -I`）。

**✅ 成功标志**：提示符变成 `pi@studylamp:~ $`。

### 3.3 准备系统环境
```bash
sudo apt update && sudo apt upgrade -y     # 首次较久
sudo apt install -y git python3-pip python3-venv \
  libgl1 libglib2.0-0 libatlas-base-dev
```
> 后三个是 OpenCV / MediaPipe 运行必需的系统库，缺了会 `ImportError`。

### 3.4 把代码弄到树莓派上
```bash
# 方式一：git（代码已推远程）
cd ~ && git clone <你的仓库地址> studylamp && cd studylamp

# 方式二：从 Mac 拷（在 Mac 终端敲）
rsync -av --exclude 'node_modules' --exclude '__pycache__' \
  --exclude '.git' --exclude '*.db' \
  /Volumes/workplace/studylamp/ pi@studylamp.local:~/studylamp/
```

### 3.5 装 Python 依赖（树莓派版，跳过 rumps）
树莓派是 ARM 架构，`rumps`（Mac 菜单栏库）装不上也用不到。
```bash
cd ~/studylamp
python3 -m venv venv && source venv/bin/activate    # 提示符出现 (venv) 即对
pip install --upgrade pip
pip install opencv-python numpy websockets
pip install mediapipe        # 最容易出问题，见下
```
> **⚠️ mediapipe 装不上**：
> 1. 确认 64 位：`getconf LONG_BIT` 应输出 `64`（否则重烧 64 位系统）
> 2. 试指定版本：`pip install mediapipe==0.10.14`
> 3. 用社区树莓派专用包（搜 "mediapipe raspberry pi wheel" 或 `mediapipe-rpi4`）
> 4. 实在装不上 → 说明兼容性/性能有限，需回头讨论「更轻的姿态模型」降级方案

若后端也要跑在树莓派上：`pip install -r server/requirements.txt`。

### 3.6 改 3 处 Mac 专属代码（关键）
现有代码为 Mac 而写，3 处在树莓派上会出问题。**这部分可由 AI 在独立分支改好，你只需确认。**

1. **`config.py` — 数据路径**：`DATA_DIR = ~/Library/Application Support/StudyLamp`（Mac 专属）→ 改成通用路径如 `~/.studylamp`。
2. **`main.py` — 整个是 Mac 菜单栏应用**：依赖 `rumps` + `osascript`，树莓派没有菜单栏。**新建 `run_headless.py`**：不依赖 GUI，直接启动 `CameraLoop` + `CloudSync`，通知改为打印日志。核心逻辑全部复用。
3. **摄像头**：好消息——`core/camera.py` 用标准 `cv2.VideoCapture(CAMERA_INDEX)`，USB 摄像头基本即插即用。只需确认 `CAMERA_INDEX = 0` 是否正确（CSI 排线摄像头需额外配置，届时再说）。

### 3.7 先单独测摄像头（排除硬件问题）
```bash
source venv/bin/activate
python3 -c "import cv2; c=cv2.VideoCapture(0); ok,f=c.read(); print('摄像头OK' if ok else '读取失败', f.shape if ok else ''); c.release()"
```
输出 `摄像头OK (480, 640, 3)` → 正常；`读取失败` → 检查 USB 插好、换口、或 `CAMERA_INDEX` 改 1。

### 3.8 跑起来
改好代码后：
```bash
cd ~/studylamp && source venv/bin/activate
export STUDYLAMP_SERVER=http://<后端地址>:8000   # 阶段一填电脑局域网 IP
python3 run_headless.py
```
终端会打印状态日志（`状态: studying` / `warning` 等）。MediaPipe 首次加载较慢，耐心等；`Ctrl+C` 停止。
> **性能预期**：树莓派算力弱于 Mac。若 CPU 跑满/卡顿，把 `config.py` 的 `SAMPLE_INTERVAL_ACTIVE` 从 5 秒调大（如 10 秒）——学习监控本不需要高帧率。

### 3.9 配置开机自启（插电就自动跑）
```bash
sudo nano /etc/systemd/system/studylamp.service
```
粘贴（用户名 `pi` 如不同要改）：
```ini
[Unit]
Description=StudyLamp AI Monitor
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/studylamp
Environment=STUDYLAMP_SERVER=http://<后端地址>:8000
ExecStart=/home/pi/studylamp/venv/bin/python3 /home/pi/studylamp/run_headless.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
`Ctrl+O` 保存、`Ctrl+X` 退出，然后：
```bash
sudo systemctl daemon-reload
sudo systemctl enable studylamp     # 开机自启
sudo systemctl start studylamp      # 立即启动
sudo systemctl status studylamp     # 查看状态（q 退出）
journalctl -u studylamp -f          # 实时日志（Ctrl+C 退出）
```
**✅ 最终成功标志**：拔掉 HDMI 和键盘，只留电源和摄像头，重启后日志里状态在变化，且小程序能收到数据。

---

## 4. 小程序 miniprogram/

### 4.1 必须改的 2 处

| 改什么 | 位置 | 现状 → 改成 |
|---|---|---|
| 后端地址 | `app.js` 第 7 行 | `baseUrl: 'http://localhost:8000'` → 阶段一填电脑局域网 IP；上线填 `https://你的域名` |
| 登录换 openid | `app.js` `_login()` | 假 openid（`user_ + code`）→ 调后端真登录接口（配合 §2.2 第 3 点） |

> WebSocket（`pages/report/report.js`）会自动跟着 `baseUrl` 变成 `ws://` / `wss://`，无需单独改。

### 4.2 小程序怎么部署（和普通程序不一样）
1. 注册**微信小程序账号**（mp.weixin.qq.com，个人可注册），拿到 **AppID**
2. 用**微信开发者工具**打开 `miniprogram/` 目录，填入 AppID
3. **阶段一联调**：开发者工具里勾选「不校验合法域名」，即可连本地/局域网后端调试
4. **上线**：在小程序后台把后端 HTTPS 域名加到 **request 合法域名** 和 **socket 合法域名** 白名单 → 「上传」→ 提交审核 → 审核通过后「发布」
5. 家长扫码/搜索即可使用

---

## 5. 常见问题速查

| 现象 | 原因 | 解决 |
|---|---|---|
| 跑 AI 时突然重启 | 供电不足 | 用配套原装电源，别用充电器 |
| `import mediapipe` 报错 | 32 位系统 / 版本不对 | 确认 64 位；见 §3.5 |
| `import cv2` 报错缺 libGL | 缺系统库 | 重跑 §3.3 的 apt install |
| 摄像头读取失败 | 没插好 / index 错 | 见 §3.7 |
| 检测很卡、CPU 100% | 树莓派算力有限 | 调大 `SAMPLE_INTERVAL_ACTIVE` |
| 树莓派事件传不到后端 | 地址错 / 不同网段 | 确认 `STUDYLAMP_SERVER` 正确、两设备同 WiFi |
| 小程序连不上后端 | 域名未配 / 非 HTTPS | 开发版勾「不校验域名」；上线需 HTTPS + 白名单 |
| 小程序数据为空但后端有数据 | `deviceId` 不一致 | 确认小程序里的 deviceId 与树莓派 `STUDYLAMP_DEVICE_ID` 一致 |

---

## 6. 下一步（可选，非必须）

以上跑通后，「软件集成到硬件」的核心任务就完成了。若之后想让台灯更智能（用 GPIO 控制真实灯光、接传感器、坐姿不对时亮灯提醒），属于硬件扩展，可再单独规划——不是当前必须的。

---

*本文档针对 StudyLamp 现有代码（`main.py` / `config.py` / `core/camera.py` / `server/app.py` / `miniprogram/app.js` 等）编写。§2.2 与 §3.6 的代码改动可由 AI 在独立分支完成。*
