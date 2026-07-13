#!/usr/bin/env python3
"""
Hermes Portable — 桌面版管理器

管理桌面版应用的启动、配置和生命周期。

Usage:
  python3 lib/desktop_manager.py start          # 启动桌面版
  python3 lib/desktop_manager.py stop           # 停止桌面版
  python3 lib/desktop_manager.py status         # 检查状态
  python3 lib/desktop_manager.py setup          # 初始化便携环境
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class DesktopManager:
    """桌面版管理器"""

    def __init__(self, portable_dir=None):
        if portable_dir:
            self.portable_dir = Path(portable_dir)
        else:
            # 自动检测便携包根目录
            self.portable_dir = Path(__file__).parent.parent

        self.data_dir = self.portable_dir / "data"
        self.desktop_data_dir = self.data_dir / "desktop-userdata"
        self.runtime_dir = self.portable_dir / "runtime" / "desktop"
        self.pid_file = self.data_dir / "desktop.pid"
        self.log_file = self.data_dir / "logs" / "desktop.log"

    def setup_environment(self):
        """设置便携模式环境变量"""
        # 创建必要的目录
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.desktop_data_dir.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # 创建 HOME 沙箱
        home_dir = self.portable_dir / "_home"
        home_dir.mkdir(exist_ok=True)

        # 创建 .hermes 符号链接
        hermes_link = home_dir / ".hermes"
        if not hermes_link.exists():
            if sys.platform == "win32":
                # Windows 使用 junction
                subprocess.run(
                    ["mklink", "/J", str(hermes_link), str(self.data_dir)],
                    shell=True,
                    check=False,
                )
            else:
                hermes_link.symlink_to(self.data_dir)

        # 设置环境变量
        env = os.environ.copy()
        env["HOME"] = str(home_dir)
        env["HERMES_HOME"] = str(self.data_dir)
        env["HERMES_DESKTOP_USER_DATA_DIR"] = str(self.desktop_data_dir)
        env["HERMES_PORTABLE_ROOT"] = str(self.portable_dir)
        env["HERMES_PORTABLE_MODE"] = "1"

        if sys.platform == "win32":
            env["USERPROFILE"] = str(home_dir)

        return env

    def get_desktop_executable(self):
        """获取桌面版可执行文件路径"""
        if sys.platform == "darwin":
            # macOS: 查找 .app 包
            for arch in ["mac-arm64", "mac"]:
                app_path = self.runtime_dir / "dist" / arch / "Hermes.app"
                if app_path.exists():
                    return app_path
            return None
        elif sys.platform == "win32":
            # Windows: 查找 exe
            exe_path = self.runtime_dir / "dist" / "win-unpacked" / "Hermes.exe"
            return exe_path if exe_path.exists() else None
        else:
            # Linux: 查找可执行文件或 AppImage
            for candidate in [
                self.runtime_dir / "dist" / "linux-unpacked" / "Hermes",
                self.runtime_dir / "dist" / "Hermes.AppImage",
            ]:
                if candidate.exists():
                    return candidate
            return None

    def is_running(self):
        """检查桌面版是否运行"""
        if not self.pid_file.exists():
            return False

        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)  # 检查进程是否存在
            return True
        except (OSError, ValueError):
            self.pid_file.unlink(missing_ok=True)
            return False

    def start(self, wait=True):
        """启动桌面版"""
        if self.is_running():
            print("桌面版已在运行")
            return True

        exe_path = self.get_desktop_executable()
        if not exe_path:
            print("错误: 桌面版未找到")
            print("请先运行: python3 tools/build.py")
            return False

        env = self.setup_environment()

        print("启动桌面版...")
        print(f"  数据目录: {self.data_dir}")
        print(f"  可执行文件: {exe_path}")

        # 启动桌面应用
        if sys.platform == "darwin":
            # macOS: 使用 open 命令启动 .app
            process = subprocess.Popen(
                ["open", str(exe_path)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        elif sys.platform == "win32":
            # Windows: 直接启动 exe
            process = subprocess.Popen(
                [str(exe_path)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            # Linux: 直接启动
            process = subprocess.Popen(
                [str(exe_path)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        # 保存 PID
        self.pid_file.write_text(str(process.pid))
        print(f"  PID: {process.pid}")

        if wait:
            # 等待应用启动
            time.sleep(2)
            if self.is_running():
                print("桌面版已启动 ✓")
                return True
            else:
                print("警告: 桌面版可能未正常启动")
                return False

        return True

    def stop(self):
        """停止桌面版"""
        if not self.is_running():
            print("桌面版未运行")
            return True

        try:
            pid = int(self.pid_file.read_text().strip())
            print(f"停止桌面版 (PID: {pid})...")

            if sys.platform == "win32":
                # Windows: 使用 taskkill
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
            else:
                # Unix: 发送 SIGTERM
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass

            self.pid_file.unlink(missing_ok=True)
            print("桌面版已停止 ✓")
            return True
        except Exception as e:
            print(f"停止桌面版失败: {e}")
            self.pid_file.unlink(missing_ok=True)
            return False

    def status(self):
        """检查桌面版状态"""
        exe_path = self.get_desktop_executable()
        running = self.is_running()

        print("桌面版状态:")
        print(f"  可执行文件: {'✓ 存在' if exe_path else '✗ 不存在'}")
        if exe_path:
            print(f"    路径: {exe_path}")
        print(f"  运行状态: {'✓ 运行中' if running else '✗ 未运行'}")
        print(f"  数据目录: {self.data_dir}")
        print(f"  桌面数据: {self.desktop_data_dir}")

        if running:
            pid = self.pid_file.read_text().strip()
            print(f"  PID: {pid}")

        return running

    def setup(self):
        """初始化便携环境"""
        print("初始化便携环境...")

        env = self.setup_environment()

        # 创建配置文件
        config_dir = self.data_dir / "desktop"
        config_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "portableMode": True,
            "dataDir": str(self.data_dir),
            "desktopDataDir": str(self.desktop_data_dir),
            "hermesHome": str(self.data_dir),
        }

        config_file = config_dir / "portable-config.json"
        config_file.write_text(json.dumps(config, indent=2))

        print(f"  ✓ 数据目录: {self.data_dir}")
        print(f"  ✓ 桌面数据: {self.desktop_data_dir}")
        print(f"  ✓ 配置文件: {config_file}")
        print()
        print("便携环境初始化完成 ✓")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 lib/desktop_manager.py <command>")
        print()
        print("命令:")
        print("  start   启动桌面版")
        print("  stop    停止桌面版")
        print("  status  检查状态")
        print("  setup   初始化便携环境")
        sys.exit(1)

    command = sys.argv[1]
    manager = DesktopManager()

    if command == "start":
        success = manager.start()
        sys.exit(0 if success else 1)
    elif command == "stop":
        success = manager.stop()
        sys.exit(0 if success else 1)
    elif command == "status":
        running = manager.status()
        sys.exit(0 if running else 1)
    elif command == "setup":
        manager.setup()
        sys.exit(0)
    else:
        print(f"未知命令: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
