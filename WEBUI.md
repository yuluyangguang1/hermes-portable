# Hermes Web UI 集成说明

## 📦 已集成功能

Hermes Portable 现已支持自动启动第三方 Web 管理界面（[EKKOLearnAI/hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui)）。

---

## 🔧 配置方法

### 1. 安装 Web UI（首次使用前）

在 Hermes Portable 的 Python 环境中全局安装：

```bash
# 进入便携包目录
cd /path/to/HermesPortable

# 使用内置 Python 安装
./venv/bin/pip install -g hermes-web-ui
```

或直接使用 npm（需先安装 Node.js ≥ 23.0.0）：

```bash
npm install -g hermes-web-ui
```

### 2. 启用自动启动

打开配置面板（`Hermes.command` 或 `Hermes.bat`），进入 **「偏好设置」** 选项卡：

找到 **「启动时自动打开 Web UI 管理界面」** 开关并启用 ✅

保存后，下次启动 Hermes 时将自动：
1. 后台启动 `hermes-web-ui` 服务（默认端口 `8648`）
2. 自动打开浏览器访问 `http://127.0.0.1:8648`

### 3. 手动启动

如果未启用自动启动，也可手动运行：

```bash
# 在 Hermes Portable 目录下
hermes-web-ui start --port 8648 --upstream http://127.0.0.1:8642
```

然后访问 http://127.0.0.1:8648

---

## 📁 代码变更记录

### 修改文件清单

| 文件 | 变更内容 |
|------|----------|
| `config_server.py` | +153 行（WEB_UI 配置 + HTML toggle + JS 处理） |
| `Hermes.command` | +21 行（Web UI 自动启动检测 + 浏览器打开） |
| `Hermes.bat` | +23 行（同上，Windows 批处理） |

### 核心修改点

#### Python (config_server.py)

1. **常量定义**（第 40 行前）：
```python
WEB_UI = {
    "id": "web_ui",
    "name": "Hermes Web UI",
    "desc": "浏览器管理界面 (EKKOLearnAI/hermes-web-ui)",
    "requires": "npm install -g hermes-web-ui",
    "default_port": 8648,
    "upstream_url": "http://127.0.0.1:8642",
}
```

2. **read_config()** 返回中增加 `"web_ui": WEB_UI`（第 145 行后）

3. **save_config()** 生成配置：
```python
"web_ui": {
    "auto_open": data.get("auto_open_web_ui", True),
},
```

4. **HTML**  Settings 卡片新增 toggle（第 880 行附近）：
```html
<div class="toggle-row">
  <div class="toggle-info">
    <div class="toggle-label">启动时自动打开 Web UI 管理界面</div>
    <div class="toggle-desc">需先安装: npm install -g hermes-web-ui</div>
  </div>
  <label class="switch"><input type="checkbox" id="auto_open_web_ui" checked><span class="slider"></span></label>
</div>
```

5. **JavaScript init()** 恢复状态（第 1082 行）：
```js
if (cfg.web_ui) document.getElementById('auto_open_web_ui').checked = cfg.web_ui.auto_open !== false;
```

6. **JavaScript saveConfig()** 收集字段（第 1112 行后）：
```js
auto_open_web_ui: document.getElementById('auto_open_web_ui').checked,
```

#### 启动器

**Hermes.command**（Bash）和 **Hermes.bat**（Windows）增加检测逻辑：

```bash
# 检查配置文件中的 auto_open_web_ui 开关
AUTO_WEB_UI=$(grep -E '^auto_open_web_ui:' "$HERE/data/config.yaml" ...)
if [ "$AUTO_WEB_UI" != "false" ]; then
    if command -v hermes-web-ui >/dev/null 2>&1; then
        hermes-web-ui start --port 8648 --upstream http://127.0.0.1:8642 &
        sleep 2
        open "http://127.0.0.1:8648"  # 或 xdg-open
    fi
fi
```

---

## ⚙️ 配置存储

Web UI 配置保存在 `data/config.yaml`：

```yaml
web_ui:
  auto_open: true   # 启动时自动打开（true/false）
```

---

## 🚨 注意事项

1. **Node.js 版本**：hermes-web-ui 需要 Node.js ≥ 23.0.0
2. **端口占用**：Web UI 默认使用 `8648`，确保该端口未被占用
3. **上游地址**：默认连接 `http://127.0.0.1:8642`（Hermes Agent gateway）
4. **无 Hermes 不启动**：未检测到 `hermes-web-ui` 命令时不弹窗，不影响 Hermes 正常启动
5. **API Key 前置**：必须先在配置面板填写至少一个 API Key 后，Web UI 启动逻辑才会执行

---

## 📊 端口对照表

| 服务 | 端口 | 说明 |
|------|------|------|
| Hermes Agent Gateway | 8642 | 内部 API 服务 |
| Hermes Web UI | 8648 | 浏览器管理界面 |
| Config Panel | 17520 | 本地配置服务器 |

---

## 🎯 故障排查

| 问题 | 检查点 |
|------|--------|
| Web UI 未弹出 | 1. 确认 `auto_open_web_ui` 开关已启用<br>2. 运行 `which hermes-web-ui` 确认命令存在<br>3. 查看 `data/config.yaml` 中 web_ui 段 |
| 无法访问 http://127.0.0.1:8648 | 1. 确认 8648 端口未被占用<br>2. 手动运行 `hermes-web-ui start` 查看错误 |
| 页面空白或报错 | 1. 确认 Hermes Agent 已在后台运行（gateway 端口 8642）<br>2. 检查浏览器控制台网络请求 |
| 配置不保存 | 1. 确认点击「保存」按钮且提示「已保存」<br>2. 检查 `data/config.yaml` 文件权限 |

---

## 🔄 版本信息

- **Hermes Portable**: v0.11.0
- **集成日期**: 2026-04-29
- **Web UI 上游**: EKKOLearnAI/hermes-web-ui v0.4.9
- **修改文件**: `config_server.py`, `Hermes.command`, `Hermes.bat`

---

*最后更新: 2026-05-06*
