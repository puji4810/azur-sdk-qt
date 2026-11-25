#!/usr/bin/env python3
"""Start the original Steam command with the optional Qt SDK bridge installed."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from tempfile import NamedTemporaryFile


ROOT = Path(__file__).resolve().parent
OFFICIAL = json.loads((ROOT / "upstream-lock.json").read_text())["sdk"]


def checksum(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def atomic_copy(source, destination):
    with NamedTemporaryFile(dir=destination.parent, delete=False) as pending:
        temporary = Path(pending.name)
        try:
            with source.open("rb") as contents:
                shutil.copyfileobj(contents, pending)
            pending.flush()
            os.fsync(pending.fileno())
            temporary.chmod(0o755)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


class Bridge:
    def __init__(self, game):
        self.game = game
        sdk = game / "AzurPromilia_Data/Plugins/mj_sdk"
        self.target = sdk / "union_pcsdk.dll"
        self.backup = sdk / "union_pcsdk_original.dll"
        self.browser = sdk / "manjuu_sdk_browser.exe"
        binaries = (ROOT / "build/selected").resolve()
        self.proxy = binaries / "union_pcsdk.dll"
        self.host_source = binaries / "azur-sdk-host.exe"
        self.host = game / self.host_source.name
        self.state = game / ".azur-sdk-qt"

    def is_bridge_binary(self, path, source):
        if not path.is_file():
            return False
        matches = [source, ROOT / "build" / source.name, ROOT / "build/current" / source.name]
        matches.extend((ROOT / "build/releases").glob(f"*/{source.name}"))
        digest = checksum(path)
        return any(candidate.is_file() and checksum(candidate) == digest for candidate in matches)

    def check(self):
        for executable in (self.game / "AzurPromilia.exe", self.proxy, self.host_source):
            if not executable.is_file():
                raise RuntimeError(f"找不到 {executable}")
        if checksum(self.target) != OFFICIAL[self.target.name]:
            raise RuntimeError("官方 SDK 的 SHA-256 已变化，请确认客户端版本或先恢复。")
        if checksum(self.browser) != OFFICIAL[self.browser.name]:
            raise RuntimeError("官方 SDK 浏览器的 SHA-256 已变化，请确认客户端版本。")
        if self.backup.exists() or self.host.exists():
            raise RuntimeError("发现同名桥接文件，请先运行 --restore。")
        import PyQt6.QtWidgets  # noqa: F401

    def install(self):
        self.check()
        atomic_copy(self.target, self.backup)
        try:
            atomic_copy(self.host_source, self.host)
            atomic_copy(self.proxy, self.target)
        except BaseException:
            self.restore()
            raise

    def restore(self):
        if self.backup.exists():
            original = OFFICIAL[self.target.name]
            if checksum(self.backup) != original:
                raise RuntimeError("备份与已知官方 SDK 不一致，已保留现场。")
            if not self.target.exists() or self.is_bridge_binary(self.target, self.proxy):
                self.backup.replace(self.target)
            elif checksum(self.target) == original:
                self.backup.unlink()
            else:
                raise RuntimeError("启动器写入了其他版本的 SDK，已保留新文件和备份。")
        if self.is_bridge_binary(self.host, self.host_source):
            self.host.unlink()
        (self.state / "native-endpoint.json").unlink(missing_ok=True)


def launch(bridge, command):
    endpoint = bridge.state / "native-endpoint.json"
    endpoint.unlink(missing_ok=True)
    (bridge.state / "sdk-host-failure.log").unlink(missing_ok=True)
    bridge.install()
    ui = launcher = None
    try:
        env = os.environ.copy()
        env["AZUR_SDK_QT_NATIVE_UI"] = "1"
        ui = subprocess.Popen([sys.executable, "-B", str(ROOT / "run.py"), "--ui", str(endpoint)])
        # Keep the game window and its normal startup checks visible on Linux.
        env["FINEWINE_AZUR_PREVIEW"] = "1"
        launcher = subprocess.Popen(command, env=env)
        return launcher.wait()
    finally:
        if launcher is not None and launcher.poll() is None:
            launcher.terminate()
            try:
                launcher.wait(timeout=15)
            except subprocess.TimeoutExpired:
                launcher.kill()
                launcher.wait()
        if ui is not None and ui.poll() is None:
            ui.terminate()
            ui.wait()
        if bridge.target.exists() and checksum(bridge.target) == OFFICIAL[bridge.target.name] and not endpoint.exists():
            print("启动器已放回官方 SDK，本次桥接未被游戏加载。", file=sys.stderr)
        bridge.restore()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=ROOT.parent / "AzurPromilia_Game")
    parser.add_argument("--sdk-window", action="store_true", help=argparse.SUPPRESS)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--restore", action="store_true")
    modes.add_argument("--ui", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.ui is not None:
        from login_window import run
        return run(args.ui)
    bridge = Bridge(args.game.resolve())
    if args.check:
        bridge.check()
        print("游戏、SDK 哈希、桥接程序和 PyQt6 检查通过。")
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not args.restore and not command:
        parser.error("请通过 Steam 启动，或用 --check 检查。")
    bridge.state.mkdir(mode=0o700, exist_ok=True)
    bridge.state.chmod(0o700)
    with (bridge.state / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.restore:
            bridge.restore()
            return 0
        signal.signal(signal.SIGTERM, lambda *_: signal.raise_signal(signal.SIGINT))
        return launch(bridge, command)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        sys.exit(f"蓝色星原 Qt 桥接：{error}")
