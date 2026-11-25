# 蓝色星原 Linux Qt SDK 桥接

游戏通过 DW-Proton 运行。桥接进程加载原版 Qt 登录 SDK，Linux 本机的 PyQt6 窗口显示官方 SDK 画面并转发输入。原版 SDK 浏览器仍由 Proton 运行，协议、登录和验证由官方组件处理。包内没有官方 SDK 或游戏文件。

## 启动

在桥接项目目录里运行以下命令检查配置。默认游戏目录为项目旁边的 `AzurPromilia_Game`，也可以用 `--game` 指定游戏本体目录。

```sh
python3 ./run.py --check
```

退出游戏和启动器后，在 Steam 里选择 DW-Proton 11.0-17，并将目标设为已安装的官方 `launcher.exe`。以下示例假设桥接项目位于 `$HOME/azur-sdk-qt`。

```sh
python3 "$HOME/azur-sdk-qt/run.py" -- %command%
```

如果需要复用其他 Steam 条目的 Proton prefix，可以在同一行开头加上 `STEAM_COMPAT_DATA_PATH`，值填写自己的 `compatdata` 子目录。

从启动器点「开始游戏」。协议或登录画面出现时，Qt 窗口会自动打开。本版保留官方浏览器入口；如果官方浏览器或游戏内 Vuplex 在 Proton 下打不开，Qt 桥接无法代替它。

较小的官方 SDK 浏览器弹窗会请求扩大到至少 640 × 480（受显示器工作区限制）。如果滑块出现在 Linux Qt 窗口内，可按住 Ctrl 滚动鼠标滚轮，以指针所在处为中心放大。Ctrl+0 恢复原大小。

启动器退出后，包装器会恢复原 SDK。如果启动器主动覆盖了代理或拒绝加载，步骤会留下诊断信息。若进程被强制结束，请在游戏和启动器都退出后执行：

```sh
python3 ./run.py --restore
```

SDK 宿主日志位于 `AzurPromilia_Game/.azur-sdk-qt/sdk-bridge.log`。它记录请求类型、字数和窗口状态。宿主在登录完成前退出时，`sdk-host-failure.log` 会记录退出码和可捕获的异常位置。安装前校验官方 DLL 和浏览器 SHA-256，遇到新 SDK 会停止接入。恢复时保留启动器写入的新版 SDK 和原版备份。

## 构建

需要 Python 3.11+ 与 PyQt6。运行 `./build.sh` 构建两个 x86-64 PE 文件。脚本优先使用 Zig，另支持带 64 位 PE 开发库的 Wine、Clang 和 LLD。

本项目基于 [AzurPromilia-SDK-Repair](https://github.com/rakuyoao/AzurPromilia-SDK-Repair/tree/08a5b7c4862e5e30655297eb1db0bc8c9249ef12) 的桥接代码，按 GPL-3.0-or-later 提供。Linux 版本使用 PyQt6 及官方 SDK 的窗口画面，不加载 CrossOver 或 FineWine 二进制。
