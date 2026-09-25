<div align="center">

[Tiếng Việt](README.md) · [English](README.en.md) · **中文**

# NTA-Agent

**《Ninety Thousand Acres》自动游戏助手：建造、扩张领地、重铸装备、编组军队，全部在浏览器控制面板中操作。**

[![下载最新版](https://img.shields.io/github/v/release/Relieq/NTA-Agent?label=%E4%B8%8B%E8%BD%BD&style=for-the-badge)](https://github.com/Relieq/NTA-Agent/releases/latest)
![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows)
![内存](https://img.shields.io/badge/RAM-~0.5%20GB-2ea44f?style=for-the-badge)

<img src="docs/images/overview.png" alt="NTA-Agent 控制面板" width="900">

</div>

Agent **直接与游戏服务器通信**（不模拟点击屏幕），因此轻量、快速，日常运行无需打开模拟器。
所有有风险的决策都遵守你设定的上限（例如"不损失士兵"）。

> ⚠ **风险提示：** 使用脚本可能违反游戏服务条款并导致**封号**，请自行承担风险。
>
> ⚠ **单一会话：** Agent 运行时，模拟器/手机上的游戏会被登出（反之亦然）。
> 想自己玩时请先按 **⏹ Stop**。

> ℹ 控制面板界面为越南语，本页说明各部分的作用。

---

## 功能

### 🏰 总览：资源、建筑、建造队列
跟踪粮食、木材、石料、铁、金币等，并按照**你排好的建造顺序**自动升级建筑（可拖动排序、勾选跳过）。

### ⚔ 军队与编组
<img src="docs/images/armies.png" alt="军队" width="900">

- 使用**游戏自身战斗引擎的模拟**占领领地周边的地块：只有在预测损失不超过你设定的上限时才出击。
- 自动征兵、复活、补满队伍，并用经验书升级士兵。
- 选择**刷怪队伍**交给 Agent 单独管理。

### 🧠 与"大脑"对话（可选，需要 OpenAI Key）
<img src="docs/images/chat.png" alt="对话：创建编组" width="760">

用自然语言下达指令，例如 _"创建 5 支队伍：1 支大盾兵和 4 支 IMP，依次命名为 Đội 1 到 Đội 5"_。
大脑给出方案，**你点击确认**后 Agent 才会执行：从混编队伍中抽调士兵、招募缺额并自动命名。
改队名、调整战术等也可以通过对话完成。

### 🔨 按条件重铸装备
<img src="docs/images/forge.png" alt="重铸装备" width="760">

为每件装备的**每个效果数值设置最低值**（会显示可随机范围，如 150–180%），并设定**铁的预算**。
Agent 会持续重铸直到全部达标，预算用完即停止。

### 🗺 领地与据点
<img src="docs/images/territory.png" alt="领地地图" width="760">

实时领地地图：已占领地块、边界、敌军，以及建议建造**据点**的区域（点击地块即可让 Agent 建造）。
根据敌人远近自动选择螺旋式或章鱼式扩张。

### 🧭 顾问与警报
<img src="docs/images/advisor.png" alt="顾问" width="760">

敌军逼近警报、仓库将满预测、防守建议。Agent 会**记录每一场损失士兵的战斗**，
并用模拟器回放以总结经验（例如应该让哪支队伍先上）。

### ⚙ 7 步自检式设置
<img src="docs/images/setup.png" alt="设置" width="760">

每一步都会自我检查，失败时给出修复提示。无需安装 Python 或 Node，程序已内置。

---

## 安装（便携版）

1. 从 [Releases 页面](https://github.com/Relieq/NTA-Agent/releases/latest)下载 **`NTA-Agent-<版本>-full.zip`**。
2. 解压到**你有写入权限**的文件夹，例如 `D:\NTA-Agent\`（不要放在 `C:\Program Files`）。
3. 运行 **`NTA-Agent.exe`**，浏览器会打开控制面板 `http://127.0.0.1:8787`。
   - 若被 Windows SmartScreen 拦截：点击 **更多信息 → 仍要运行**（程序未签名）。
   - 若杀毒软件拦截 `NTA-Agent.exe`：改用 **`NTA-Agent.bat`**，两者功能完全相同。
4. 首次启动会打开 **Thiết lập & Cài đặt**（设置）标签页，按下面 7 个步骤操作。
   7 步全部 ✅ 之前 **▶ Start** 按钮会被锁定。

## 准备工作

- **LDPlayer 9**（Android 9），在 ldplayer.net 下载。仅设置时需要，见[日常使用](#daily-use)。
- 在 LDPlayer 中安装 **Ninety Thousand Acres**，版本需与本程序支持的一致（第 4 步）。
- （可选）**OpenAI API Key**，用于启用策略"大脑"与对话。

## 设置步骤

在设置页点击 **▶ Chạy tất cả**（全部运行）或逐步运行。失败 ❌ 的步骤会显示提示，修复后点击 **Chạy lại**（重新运行）。

1. **查找 ADB**：自动找到 LDPlayer 的 `adb.exe`（通常在 `D:\LDPlayer\LDPlayer9\adb.exe`），否则请在设置中填写路径。
2. **连接模拟器**：打开 LDPlayer，在 **LDPlayer 设置 → 其他 → ADB 调试** 中选择**开启本地连接**。多开时请在设置中填写设备名（如 `emulator-5554`）。
3. **Root 权限**：**LDPlayer 设置 → 其他 → ROOT 权限 = 开启**，保存并重启 LDPlayer。Root 仅用于读取游戏的设备 ID 与登录令牌（只读）。
4. **游戏版本**：检查已安装的游戏版本是否与程序支持的一致。游戏刚更新时可选择**跳过**（风险自负）或等待程序更新。
5. **游戏数据**：程序**不附带**任何游戏数据，而是从**你自己的模拟器**中取得游戏 APK，把协议、数据表和战斗引擎解到你的数据目录。解密密钥会**自动从你的游戏中找到**。约需 10–30 秒；重新运行前请先停止 Agent；游戏每次更新后需重新运行。
6. **设备 ID**：读取游戏登录时使用的设备 ID。失败时请先打开游戏进入主界面一次再重试。
7. **登录令牌**：在 LDPlayer 中打开游戏并**登录**（Google/Facebook 等），然后**彻底关闭游戏**，再运行此步骤（需先停止 Agent）。

7 步全部 ✅ 后，点击右上角 **▶ Start**。

---

<a id="daily-use"></a>
## 日常使用

### 需要一直开着 LDPlayer 吗？

**不需要。** Agent 直接与游戏服务器通信，平时可以关闭 LDPlayer（可省约 1.7 GB 内存）。

游戏的登录令牌只能使用一次：Agent 每次登录，服务器都会返回新令牌，Agent 会自动保存以供下次使用。
因此重启 Agent 或重启电脑都不需要 LDPlayer。

只有以下情况需要 LDPlayer：

| 情况 | 处理方式 |
|---|---|
| 首次设置，或游戏更新后 | 运行设置步骤（第 5 步重新提取游戏数据）。 |
| **令牌链断开**，通常发生在你自己登录游戏（模拟器或手机）之后 | 若 LDPlayer 已打开，Agent 会自动获取新令牌；否则会显示 **CRASHED**：打开 LDPlayer 登录游戏、彻底关闭游戏、重新运行第 7 步后点击 Start。 |
| 你想自己玩 | 先 **⏹ Stop** Agent（同一时间只能有一个会话）。 |

### 重启

- **重启控制面板：** Agent 会继续运行，新面板会自动接管。
- **重启电脑：** 不会自动启动。运行 `NTA-Agent.exe` 后点击 **▶ Start**，Agent 会用已保存的令牌登录。
- Agent 显示 **CRASHED** 时，点击 Start 旁边的 **📄 Xem lỗi**（查看错误）。

### 占用多少内存？

在一台 Windows 11 电脑上实测：

| 组件 | 内存 |
|---|---|
| 战斗模拟器（Node，运行游戏的战斗引擎） | 约 380 MB |
| Agent（Python） | 约 45 MB |
| 控制面板（Python） | 约 40 MB |
| **合计** | **约 0.5 GB** |
| _（LDPlayer，打开时）_ | _约 1.7 GB，日常运行无需打开_ |

---

## 设置项

| 设置 | 说明 |
|---|---|
| OpenAI API key | 可选。启用大脑与对话，费用计入你的 OpenAI 账户；**Kiểm tra OpenAI key** 可免费测试。 |
| 模型 / 调用上限 | 从你的 OpenAI 账户可用列表中选择模型（默认 `gpt-4o-mini`），以及每次运行的最大调用次数。 |
| XXTEA key | 留空即可：程序会从你的游戏中自动找到密钥。仅当第 5 步提示找不到时才需填写。 |
| adb.exe / ADB 设备 | 仅在程序无法自动检测时填写。 |

密钥**使用你的 Windows 账户加密**，设置文件拷到其他电脑无法读取；面板永远不会完整显示密钥。

## 更新

- 有新版本时顶部会出现蓝色的 **⬆ Có bản mới**（有新版本）提示。点击 **Cập nhật**（更新）：Agent 停止，程序下载更新（校验 checksum），约 1 分钟后自动重启。
- 新版本启动失败时会**自动回滚**。
- 手动回滚：设置 → **↩ Quay về bản trước**（保留最近 2 个版本）。
- 更新不会改动你的数据、密钥和设置。

## 数据存放位置

你的所有数据都在 `%LOCALAPPDATA%\NTA-Agent\`：`settings.json`（设置、加密后的密钥）、`token.txt`（登录令牌）、
`gamedata\`（从你的 APK 提取的游戏数据）、`run\`（Agent 状态与日志：`agent.log`、`errors.jsonl`）、`backups\`（旧版本）。

**卸载：** 删除程序文件夹以及 `%LOCALAPPDATA%\NTA-Agent`。

## 常见问题

| 现象 | 解决方法 |
|---|---|
| 浏览器没有打开 | 手动打开 `http://127.0.0.1:8787`。端口被占用时程序会改用 8788、8789… |
| Start 提示设置未完成 | 打开设置页，运行标记 ❌ 的步骤。 |
| Agent 显示 CRASHED | 点击 **📄 Xem lỗi**，或查看 `run\agent.log` / `run\errors.jsonl`。令牌问题见[日常使用](#daily-use)。 |
| 模拟器里的游戏被登出 | 正常现象：Agent 与游戏共用一个会话。 |
| 改队名没有生效 | 游戏只允许修改空闲队伍的名字；队伍回来后 Agent 会自动重试。 |
| 第 5 步提示找不到密钥 | 游戏可能改变了密钥存放方式：请告知分享程序的人，或在设置中手动填写 XXTEA key。 |

---

## 开发者

Python 3.12（虚拟环境 `.venv`），战斗模拟 sidecar 需 Node ≥ 18。架构与路线图见 `docs/ROADMAP.md`，
Agent 运维说明见 `CLAUDE.md`。

```bash
.venv/Scripts/python.exe -m pytest -q                  # 测试
.venv/Scripts/python.exe -m ruff check nta_agent tests # 代码检查
.venv/Scripts/python.exe tools/launch_detached.py dashboard   # 运行控制面板（开发）
```

打包发布（请先提交：只有被 git 跟踪的文件会被打包）：

```bash
.venv/Scripts/python.exe tools/package.py --version 0.1.0 --notes "..."
# -> dist/NTA-Agent-<v>-full.zip, dist/NTA-Agent-<v>-app.zip, dist/manifest.json
gh release create v0.1.0 dist/NTA-Agent-0.1.0-full.zip dist/NTA-Agent-0.1.0-app.zip dist/manifest.json
```

程序会从本仓库的 `releases/latest` 自动更新：内置运行时（Python/Node）未变时使用较小的 `app` 包，否则使用 `full` 包。
