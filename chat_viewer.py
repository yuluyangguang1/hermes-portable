#!/usr/bin/env python3
"""
Hermes Portable — 聊天记录查看器
查看所有历史对话记录。
"""
import json
import os
import webbrowser
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
# Portable data dir (set by the launchers via HERMES_HOME=$HERE/data).
PORTABLE_SESSIONS = SCRIPT_DIR / "data" / "sessions"
# System-wide data dir (used when hermes was started without the launcher).
SYSTEM_SESSIONS = Path.home() / ".hermes" / "sessions"

PORT = 17521


def _candidate_session_dirs():
    """All directories we may find hermes session files in.

    Unioning them means we show everything — whether the user launched
    via Hermes.sh (portable `data/`) or by running `hermes` directly
    outside the portable folder (~/.hermes/).
    """
    seen = set()
    for d in (PORTABLE_SESSIONS, SYSTEM_SESSIONS):
        if d.exists() and d.is_dir():
            resolved = d.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield d


def list_sessions():
    """List all sessions, newest first (by last_updated, falling back to mtime)."""
    seen_ids = set()
    sessions = []
    for sdir in _candidate_session_dirs():
        for f in sdir.glob("session_*.json"):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh)
                msg_count = len(data.get("messages", []))
                chat_msgs = [m for m in data.get("messages", [])
                             if m.get("role") in ("user", "assistant")]
                if not chat_msgs:
                    continue

                first_user = next((m for m in chat_msgs if m["role"] == "user"), {})
                first_msg = str(first_user.get("content", ""))[:80]
                if not first_msg:
                    continue

                sid = data.get("session_id") or f.stem
                # De-duplicate across dirs: same session id shouldn't appear twice
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)

                # Use last_updated for sort; fall back to mtime.
                sort_key = data.get("last_updated") or data.get("session_start") or ""
                if not sort_key:
                    try:
                        sort_key = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                    except Exception:
                        sort_key = ""

                sessions.append({
                    "_sort": sort_key,
                    "file": f.name,
                    "session_id": sid,
                    "model": data.get("model", "unknown"),
                    "start": data.get("session_start", ""),
                    "updated": data.get("last_updated", ""),
                    "message_count": msg_count,
                    "chat_count": len(chat_msgs),
                    "preview": first_msg,
                })
            except Exception:
                # Malformed session file — skip it silently, but let
                # callers detect the miss via the missing count.
                continue
    sessions.sort(key=lambda s: s["_sort"], reverse=True)
    for s in sessions:
        s.pop("_sort", None)
    return sessions


def get_session(filename):
    """Load a single session by filename (looked up in any candidate dir)."""
    # Security: strict pattern on the filename.
    import re
    if not re.match(r'^session_[a-zA-Z0-9_\-]+\.json$', filename):
        return None
    for sdir in _candidate_session_dirs():
        f = sdir / filename
        if not f.exists():
            continue
        # Path-traversal defence: resolved file must live directly inside sdir.
        try:
            if f.resolve().parent != sdir.resolve():
                continue
        except Exception:
            continue
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
        except Exception:
            return None
        messages = [m for m in data.get("messages", [])
                    if m.get("role") in ("user", "assistant")]
        return {
            "session_id": data.get("session_id", ""),
            "model": data.get("model", ""),
            "start": data.get("session_start", ""),
            "messages": messages,
        }
    return None


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes 聊天记录</title>
<style>
  :root {
    --bg: #0f1117;
    --card: #1a1d27;
    --card2: #12141c;
    --border: #2a2d3a;
    --accent: #6c5ce7;
    --accent2: #a29bfe;
    --green: #00b894;
    --user-bg: rgba(108,92,231,0.12);
    --asst-bg: rgba(255,255,255,0.04);
    --text: #e4e6eb;
    --muted: #8b8fa3;
    --radius: 12px;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); height:100vh; overflow:hidden; }

  .layout { display:flex; height:100vh; }

  /* ── Sidebar ── */
  .sidebar {
    width: 340px; min-width: 340px;
    background: var(--card);
    border-right: 1px solid var(--border);
    display: flex; flex-direction: column;
    overflow: hidden;
  }
  .sidebar-header {
    padding: 20px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
  }
  .sidebar-header h2 {
    font-size: 16px; font-weight: 700;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .session-count { font-size: 12px; color: var(--muted); }
  .search-box {
    padding: 12px 20px; border-bottom: 1px solid var(--border);
  }
  .search-box input {
    width: 100%; padding: 8px 12px;
    background: var(--card2); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text);
    font-size: 13px; outline: none;
  }
  .search-box input:focus { border-color: var(--accent); }
  .session-list {
    flex: 1; overflow-y: auto; padding: 8px;
  }
  .session-item {
    padding: 14px 16px; border-radius: var(--radius);
    cursor: pointer; transition: all 0.15s;
    margin-bottom: 4px;
  }
  .session-item:hover { background: rgba(255,255,255,0.04); }
  .session-item.active { background: var(--user-bg); border: 1px solid rgba(108,92,231,0.3); }
  .session-item .preview {
    font-size: 13px; color: var(--text); font-weight: 500;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    margin-bottom: 6px;
  }
  .session-item .meta {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11px; color: var(--muted);
  }
  .session-item .model {
    background: rgba(108,92,231,0.1); padding: 2px 8px;
    border-radius: 6px; font-size: 10px;
  }

  /* ── Chat Area ── */
  .chat-area {
    flex: 1; display: flex; flex-direction: column;
    overflow: hidden; background: var(--bg);
  }
  .chat-header {
    padding: 16px 24px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    background: var(--card);
  }
  .chat-header .info { font-size: 14px; }
  .chat-header .info .model { color: var(--accent2); font-weight: 600; }
  .chat-header .info .time { color: var(--muted); font-size: 12px; margin-left: 12px; }
  .chat-messages {
    flex: 1; overflow-y: auto; padding: 24px;
    scroll-behavior: smooth;
  }
  .msg {
    max-width: 780px; margin: 0 auto 20px;
    display: flex; gap: 12px;
  }
  .msg.user { flex-direction: row-reverse; }
  .msg-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; flex-shrink: 0;
  }
  .msg.user .msg-avatar { background: var(--user-bg); }
  .msg.assistant .msg-avatar { background: rgba(0,184,148,0.12); }
  .msg-bubble {
    padding: 12px 16px; border-radius: var(--radius);
    font-size: 14px; line-height: 1.7;
    max-width: 85%; word-break: break-word;
    white-space: pre-wrap;
  }
  .msg.user .msg-bubble {
    background: var(--user-bg);
    border: 1px solid rgba(108,92,231,0.2);
    border-bottom-right-radius: 4px;
  }
  .msg.assistant .msg-bubble {
    background: var(--asst-bg);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
  }
  .msg-bubble code {
    background: rgba(255,255,255,0.06); padding: 2px 6px;
    border-radius: 4px; font-size: 13px;
    font-family: 'SF Mono', Menlo, monospace;
  }
  .msg-bubble pre {
    background: var(--card2); padding: 12px; border-radius: 8px;
    margin: 8px 0; overflow-x: auto; font-size: 12px;
    font-family: 'SF Mono', Menlo, monospace;
  }

  .empty-state {
    flex: 1; display: flex; align-items: center; justify-content: center;
    flex-direction: column; gap: 12px; color: var(--muted);
  }
  .empty-state .emoji { font-size: 48px; }
  .empty-state p { font-size: 14px; }

  .back-btn {
    background: none; border: 1px solid var(--border); color: var(--text);
    padding: 6px 14px; border-radius: 8px; cursor: pointer;
    font-size: 13px; transition: all 0.2s;
  }
  .back-btn:hover { border-color: var(--accent); }

  @media (max-width: 768px) {
    .sidebar { width: 100%; min-width: 100%; }
    .layout.chat-open .sidebar { display: none; }
    .layout.chat-open .chat-area { display: flex; }
    .chat-area { display: none; }
  }
</style>
</head>
<body>
<div class="layout" id="layout">
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>💬 聊天记录</h2>
      <span class="session-count" id="count"></span>
    </div>
    <div class="search-box">
      <input type="text" id="search" placeholder="搜索对话..." oninput="filterSessions()">
    </div>
    <div class="session-list" id="sessionList"></div>
  </div>
  <div class="chat-area" id="chatArea">
    <div class="empty-state" id="emptyState">
      <div class="emoji">💬</div>
      <p>选择左侧对话查看详情</p>
    </div>
    <div id="chatContent" style="display:none">
      <div class="chat-header">
        <div class="info">
          <span class="model" id="chatModel"></span>
          <span class="time" id="chatTime"></span>
        </div>
        <button class="back-btn" onclick="goBack()" id="backBtn" style="display:none">← 返回</button>
      </div>
      <div class="chat-messages" id="chatMessages"></div>
    </div>
  </div>
</div>

<script>
let allSessions = [];
let currentSession = null;

async function loadSessions() {
  const resp = await fetch('/api/sessions');
  allSessions = await resp.json();
  document.getElementById('count').textContent = allSessions.length + ' 条对话';
  renderSessions(allSessions);
}

function renderSessions(sessions) {
  const list = document.getElementById('sessionList');
  list.innerHTML = sessions.map((s, i) => `
    <div class="session-item ${currentSession === s.file ? 'active' : ''}"
         onclick="loadChat('${s.file.replace(/'/g, "\\'")}')">
      <div class="preview">${escapeHtml(s.preview)}</div>
      <div class="meta">
        <span>${formatTime(s.start || s.updated)}</span>
        <span class="model">${s.model.split('/').pop()}</span>
        <span>${s.chat_count} 条消息</span>
      </div>
    </div>
  `).join('');
}

function filterSessions() {
  const q = document.getElementById('search').value.toLowerCase();
  const filtered = allSessions.filter(s =>
    s.preview.toLowerCase().includes(q) ||
    s.model.toLowerCase().includes(q)
  );
  renderSessions(filtered);
}

async function loadChat(file) {
  currentSession = file;
  renderSessions(allSessions);
  document.getElementById('layout').classList.add('chat-open');

  const resp = await fetch('/api/session/' + file);
  const data = await resp.json();
  if (!data.messages) return;

  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('chatContent').style.display = 'flex';
  document.getElementById('chatContent').style.flexDirection = 'column';
  document.getElementById('chatContent').style.flex = '1';
  document.getElementById('chatContent').style.overflow = 'hidden';
  document.getElementById('chatModel').textContent = data.model;
  document.getElementById('chatTime').textContent = formatTime(data.start);
  document.getElementById('backBtn').style.display = window.innerWidth <= 768 ? 'block' : 'none';

  const container = document.getElementById('chatMessages');
  container.innerHTML = data.messages.map(m => {
    const isUser = m.role === 'user';
    const content = formatContent(m.content || '');
    return `
      <div class="msg ${m.role}">
        <div class="msg-avatar">${isUser ? '👤' : '🤖'}</div>
        <div class="msg-bubble">${content}</div>
      </div>
    `;
  }).join('');

  container.scrollTop = container.scrollHeight;
}

function goBack() {
  document.getElementById('layout').classList.remove('chat-open');
  currentSession = null;
  renderSessions(allSessions);
}

function formatContent(text) {
  if (typeof text !== 'string') text = JSON.stringify(text, null, 2);
  // Escape HTML
  let html = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  return html;
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function formatTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    const now = new Date();
    const diff = now - d;
    if (diff < 86400000) return d.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
    if (diff < 604800000) return d.toLocaleDateString('zh-CN', {weekday:'short', hour:'2-digit',minute:'2-digit'});
    return d.toLocaleDateString('zh-CN', {month:'short', day:'numeric'});
  } catch { return ts; }
}

loadSessions();
</script>
</body>
</html>"""


class ChatHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send(200, HTML_PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/sessions":
            self._send(200, json.dumps(list_sessions(), ensure_ascii=False))
        elif self.path.startswith("/api/session/"):
            fname = self.path.split("/api/session/")[1]
            data = get_session(fname)
            self._send(200, json.dumps(data or {}, ensure_ascii=False))
        else:
            self.send_error(404)

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if "text/html" in ctype:
            self.send_header("Content-Security-Policy",
                "default-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body.encode() if isinstance(body, str) else body)

    def log_message(self, *a):
        pass


def main():
    server = HTTPServer(("127.0.0.1", PORT), ChatHandler)
    url = f"http://127.0.0.1:{PORT}"
    dirs = list(_candidate_session_dirs())
    total = sum(len(list(d.glob("session_*.json"))) for d in dirs)

    dir_listing = "\n".join(f"    {d}" for d in dirs) or "    (none found yet)"

    print(f"""
  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  聊天记录

  📂 会话目录:
{dir_listing}
  💬 共 {total} 条对话
  🌐 查看: {url}
""")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
