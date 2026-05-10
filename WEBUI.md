# Hermes Web UI 集成说明

Hermes Portable 会在启动时**自动**在后台拉起第三方 Web 管理界面
[EKKOLearnAI/hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui)（如果它已安装）。
没有开关需要你打开，也没有"偏好设置"选项 —— 启动器会先 `which hermes-web-ui` / `where hermes-web-ui`，
找到就起；找不到就静默跳过，不影响主流程。

---

## 它在哪

构建完成的便携包里会携带一份已经装好的 `hermes-web-ui`，路径是：

| 平台 | 可执行文件 |
|---|---|
| macOS / Linux | `node/bin/hermes-web-ui`（Universal 包：`node-<platform>/bin/hermes-web-ui`） |
| Windows | `node\hermes-web-ui.cmd`（Universal：`node-windows-x64\hermes-web-ui.cmd`） |

启动器 `Hermes.command` / `Hermes.sh` / `Hermes.bat` 会把 `node` 目录加入 `PATH`，所以
`hermes-web-ui` 命令在子进程里就是可用的。

默认端口 **8648**，默认上游 **http://127.0.0.1:8642**（Hermes Agent 的 gateway）。

---

## 手动安装（重新下载后丢失等情况）

如果你的便携包缺失 `hermes-web-ui`，补装它需要 Node.js ≥ 23.0.0：

**macOS / Linux**

```bash
cd /path/to/HermesPortable
./node/bin/npm install -g hermes-web-ui --prefix ./node
```

**Windows**

```cmd
cd C:\path\to\HermesPortable
node\npm.cmd install -g hermes-web-ui --prefix .\node
```

注意：这里是 `npm install -g`（Node 的 `-g` = global），**不是** `pip install -g`（pip 没有这个参数）。

---

## 手动启动

如果你不想让启动器自动拉起 Web UI，可以：

1. 把 `hermes-web-ui` 从 `PATH` 中移除（或直接改名 `hermes-web-ui` → `hermes-web-ui.off`）
2. 或者启动 Hermes 之前手动启动：
   ```bash
   hermes-web-ui start --port 8648 --upstream http://127.0.0.1:8642
   ```
   然后浏览器访问 http://127.0.0.1:8648

---

## 端口对照

| 服务 | 端口 | 说明 |
|---|---|---|
| Hermes Agent gateway | 8642 | Hermes 内部 API |
| Hermes Web UI        | 8648 | 浏览器管理界面 |
| Config Panel         | 17520 | 本地配置面板（首次启动自动打开） |

端口被占用时：目前启动器不做探测和回退，Web UI 启动会静默失败。遇到时请手动释放端口或
修改启动器参数。

---

## 常见问题

| 现象 | 排查 |
|---|---|
| 启动 Hermes 后浏览器没有自动打开 Web UI | 启动器只负责后台起进程，不主动开浏览器。请手动访问 http://127.0.0.1:8648 |
| `hermes-web-ui: command not found` | 便携包里的 `node/bin` 没在 PATH 里（通常是自己绕过启动器跑了 hermes）；或 Node 目录在 Universal 包中名为 `node-<platform>` |
| 页面访问 8648 空白 / 报错 | 确认 Hermes Agent 本身在运行；Web UI 只是前端，gateway 8642 挂掉就没数据 |
| 启动器提示 "Hermes already running" | 上次退出没清理锁文件。删除 `data/.hermes.lock` 后重试 |

---

*对齐代码版本：build.py 单入口 + 启动器为仓库真实文件（非内嵌字符串）*
