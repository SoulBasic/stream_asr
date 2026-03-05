# Windows 热键客户端（EXE）

这个客户端用于：
- 选择麦克风设备
- 配置全局快捷键
- 配置 WebSocket 服务地址
- 后台常驻（托盘）
- 按快捷键开始/停止录音，实时发送到 `/v1/asr/stream`
- 收到 `partial/final` 后把文本粘贴到当前焦点输入框

## 技术栈
- .NET 8 WinForms
- NAudio（麦克风采集）
- ClientWebSocket（流式传输）

## 项目路径
- `windows-client/WinAsrHotkeyClient`

## 打包为单文件 EXE（包含运行时）

在 **Windows** 上执行：

```powershell
cd windows-client/WinAsrHotkeyClient

dotnet restore

dotnet publish -c Release -r win-x64 --self-contained true /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true /p:PublishTrimmed=false
```

产物路径：
- `bin/Release/net8.0-windows/win-x64/publish/WinAsrHotkeyClient.exe`

> 该 EXE 为 self-contained，目标机器不需要额外安装 .NET 运行时。

## 使用说明
1. 打开 EXE。
2. 选择麦克风设备。
3. 设置服务器地址（例如：`ws://<server-ip>:8000/v1/asr/stream`）。
4. 设置快捷键（例如：`Ctrl+Shift+Space`）。
5. 点击“保存并应用”。
6. 最小化后程序驻留托盘。
7. 按快捷键开始录音，再按一次停止并输出最终结果。

## 实时输出行为
- `partial`：按增量文本实时粘贴（尽量一句一句）
- `final`：补齐最终文本

## 注意
- 若快捷键注册失败，通常是被其他软件占用。
- 粘贴通过“剪贴板 + Ctrl+V”实现，极少数受限窗口可能无法注入。
