using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using NAudio.Wave;

namespace WinAsrHotkeyClient;

public sealed class MainForm : Form
{
    private const int HotkeyId = 0x2333;
    private const int WmHotkey = 0x0312;

    private readonly ComboBox _micCombo = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly TextBox _serverBox = new();
    private readonly TextBox _langBox = new() { Text = "zh" };
    private readonly TextBox _hotkeyBox = new() { Text = "Ctrl+Shift+Space" };
    private readonly Button _saveBtn = new() { Text = "保存并应用" };
    private readonly Button _testBtn = new() { Text = "测试连接" };
    private readonly Label _status = new() { AutoSize = true, Text = "状态：空闲" };
    private readonly CheckBox _autoStartCheck = new() { Text = "启动后最小化到托盘", Checked = true };

    private readonly NotifyIcon _tray;

    private AppSettings _settings = AppSettings.Load();
    private WaveInEvent? _waveIn;
    private ClientWebSocket? _ws;
    private CancellationTokenSource? _recvCts;
    private bool _isRecording;
    private string _lastServerText = "";

    public MainForm()
    {
        Text = "Qwen3 ASR 热键客户端";
        Width = 560;
        Height = 300;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;

        var table = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            RowCount = 7,
            ColumnCount = 2,
            Padding = new Padding(12),
        };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        table.Controls.Add(new Label { Text = "服务器 WS", AutoSize = true }, 0, 0);
        table.Controls.Add(_serverBox, 1, 0);
        table.Controls.Add(new Label { Text = "语言", AutoSize = true }, 0, 1);
        table.Controls.Add(_langBox, 1, 1);
        table.Controls.Add(new Label { Text = "麦克风设备", AutoSize = true }, 0, 2);
        table.Controls.Add(_micCombo, 1, 2);
        table.Controls.Add(new Label { Text = "全局快捷键", AutoSize = true }, 0, 3);
        table.Controls.Add(_hotkeyBox, 1, 3);
        table.Controls.Add(_autoStartCheck, 1, 4);

        var buttonPanel = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.LeftToRight };
        buttonPanel.Controls.Add(_saveBtn);
        buttonPanel.Controls.Add(_testBtn);
        table.Controls.Add(buttonPanel, 1, 5);

        table.Controls.Add(_status, 1, 6);
        Controls.Add(table);

        _tray = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Visible = true,
            Text = "Qwen3 ASR 热键客户端"
        };
        var menu = new ContextMenuStrip();
        menu.Items.Add("显示", null, (_, _) => ShowFromTray());
        menu.Items.Add("退出", null, (_, _) => Close());
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (_, _) => ShowFromTray();

        Load += OnLoad;
        FormClosing += OnFormClosing;
        Resize += OnResize;

        _saveBtn.Click += (_, _) => SaveAndApply();
        _testBtn.Click += async (_, _) => await TestConnectionAsync();
    }

    private void OnLoad(object? sender, EventArgs e)
    {
        _serverBox.Text = _settings.ServerWsUrl;
        _langBox.Text = _settings.Lang;
        _hotkeyBox.Text = _settings.Hotkey;
        _autoStartCheck.Checked = _settings.MinimizeToTrayOnStart;

        LoadMics();
        if (_settings.MicDeviceIndex >= 0 && _settings.MicDeviceIndex < _micCombo.Items.Count)
            _micCombo.SelectedIndex = _settings.MicDeviceIndex;

        RegisterConfiguredHotkey();

        if (_autoStartCheck.Checked)
        {
            BeginInvoke(() =>
            {
                WindowState = FormWindowState.Minimized;
                Hide();
            });
        }
    }

    private void LoadMics()
    {
        _micCombo.Items.Clear();
        for (var i = 0; i < WaveInEvent.DeviceCount; i++)
        {
            var cap = WaveInEvent.GetCapabilities(i);
            _micCombo.Items.Add($"{i}: {cap.ProductName}");
        }
        if (_micCombo.Items.Count > 0 && _micCombo.SelectedIndex < 0)
            _micCombo.SelectedIndex = 0;
    }

    private void SaveAndApply()
    {
        if (_micCombo.SelectedIndex < 0)
        {
            MessageBox.Show("请先选择麦克风设备");
            return;
        }

        _settings = new AppSettings
        {
            ServerWsUrl = _serverBox.Text.Trim(),
            Lang = string.IsNullOrWhiteSpace(_langBox.Text) ? "zh" : _langBox.Text.Trim(),
            MicDeviceIndex = _micCombo.SelectedIndex,
            Hotkey = _hotkeyBox.Text.Trim(),
            MinimizeToTrayOnStart = _autoStartCheck.Checked,
        };

        _settings.Save();
        RegisterConfiguredHotkey();
        SetStatus($"设置已保存，热键：{_settings.Hotkey}");
    }

    private async Task TestConnectionAsync()
    {
        try
        {
            using var ws = new ClientWebSocket();
            await ws.ConnectAsync(new Uri(_serverBox.Text.Trim()), CancellationToken.None);
            await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "test", CancellationToken.None);
            SetStatus("连接测试成功");
        }
        catch (Exception ex)
        {
            SetStatus($"连接测试失败：{ex.Message}");
        }
    }

    protected override async void WndProc(ref Message m)
    {
        if (m.Msg == WmHotkey && m.WParam.ToInt32() == HotkeyId)
        {
            try
            {
                if (_isRecording) await StopRecordingAsync();
                else await StartRecordingAsync();
            }
            catch (Exception ex)
            {
                SetStatus($"热键处理失败：{ex.Message}");
                _isRecording = false;
            }
        }
        base.WndProc(ref m);
    }

    private async Task StartRecordingAsync()
    {
        if (_isRecording) return;

        _lastServerText = "";
        _ws = new ClientWebSocket();
        await _ws.ConnectAsync(new Uri(_settings.ServerWsUrl), CancellationToken.None);

        var start = JsonSerializer.Serialize(new { type = "start", sample_rate = 16000, lang = _settings.Lang });
        await _ws.SendAsync(Encoding.UTF8.GetBytes(start), WebSocketMessageType.Text, true, CancellationToken.None);

        _recvCts = new CancellationTokenSource();
        _ = Task.Run(() => ReceiveLoopAsync(_recvCts.Token));

        _waveIn = new WaveInEvent
        {
            DeviceNumber = _settings.MicDeviceIndex,
            WaveFormat = new WaveFormat(16000, 16, 1),
            BufferMilliseconds = 120,
        };
        _waveIn.DataAvailable += async (_, e) =>
        {
            if (_ws?.State == WebSocketState.Open)
            {
                try
                {
                    await _ws.SendAsync(e.Buffer.AsMemory(0, e.BytesRecorded), WebSocketMessageType.Binary, true, CancellationToken.None);
                }
                catch { }
            }
        };
        _waveIn.StartRecording();
        _isRecording = true;
        SetStatus("录音中...再次按快捷键停止");
    }

    private async Task StopRecordingAsync()
    {
        if (!_isRecording) return;
        _isRecording = false;

        try
        {
            _waveIn?.StopRecording();
            _waveIn?.Dispose();
            _waveIn = null;

            if (_ws?.State == WebSocketState.Open)
            {
                var stop = JsonSerializer.Serialize(new { type = "stop" });
                await _ws.SendAsync(Encoding.UTF8.GetBytes(stop), WebSocketMessageType.Text, true, CancellationToken.None);
            }
        }
        catch (Exception ex)
        {
            SetStatus($"停止录音异常：{ex.Message}");
        }

        SetStatus("等待最终识别结果...");
    }

    private async Task ReceiveLoopAsync(CancellationToken ct)
    {
        if (_ws == null) return;

        var buffer = new byte[8192];
        var ms = new MemoryStream();

        try
        {
            while (!ct.IsCancellationRequested && _ws.State == WebSocketState.Open)
            {
                ms.SetLength(0);
                WebSocketReceiveResult result;
                do
                {
                    result = await _ws.ReceiveAsync(buffer, ct);
                    if (result.MessageType == WebSocketMessageType.Close)
                        return;
                    ms.Write(buffer, 0, result.Count);
                } while (!result.EndOfMessage);

                var json = Encoding.UTF8.GetString(ms.ToArray());
                HandleServerEvent(json);
            }
        }
        catch
        {
            // ignore background receive errors
        }
        finally
        {
            try
            {
                if (_ws.State == WebSocketState.Open)
                    await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "done", CancellationToken.None);
            }
            catch { }
            _ws.Dispose();
            _ws = null;
        }
    }

    private void HandleServerEvent(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        var type = root.TryGetProperty("type", out var t) ? t.GetString() : "";

        if (type == "error")
        {
            var msg = root.TryGetProperty("message", out var m) ? m.GetString() : "unknown";
            SetStatus($"服务端错误：{msg}");
            return;
        }

        if (type is "partial" or "final")
        {
            var text = root.TryGetProperty("text", out var txt) ? txt.GetString() ?? "" : "";
            if (!string.IsNullOrWhiteSpace(text))
            {
                var delta = ComputeDelta(_lastServerText, text);
                if (!string.IsNullOrEmpty(delta))
                {
                    PasteToFocusedInput(delta);
                }
                _lastServerText = text;
            }
            if (type == "final")
            {
                SetStatus("识别完成，已输出到当前焦点输入框");
            }
            else
            {
                SetStatus("实时识别中...");
            }
        }
    }

    private static string ComputeDelta(string oldText, string newText)
    {
        if (string.IsNullOrEmpty(oldText)) return newText;
        if (newText.StartsWith(oldText, StringComparison.Ordinal))
            return newText[oldText.Length..];
        return "\n" + newText;
    }

    private void SetStatus(string text)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => SetStatus(text));
            return;
        }
        _status.Text = "状态：" + text;
    }

    private void RegisterConfiguredHotkey()
    {
        UnregisterHotKey(Handle, HotkeyId);

        var (mods, key) = HotkeyParser.Parse(_hotkeyBox.Text.Trim());
        if (key == Keys.None)
        {
            MessageBox.Show("快捷键格式不正确，例如 Ctrl+Shift+Space");
            return;
        }

        if (!RegisterHotKey(Handle, HotkeyId, (uint)mods, (uint)key))
        {
            MessageBox.Show("快捷键注册失败，可能已被其他程序占用");
        }
    }

    private void PasteToFocusedInput(string text)
    {
        if (string.IsNullOrEmpty(text)) return;

        // 使用剪贴板 + Ctrl+V，兼容大多数焦点输入控件。
        // 这里在 UI 线程执行，避免 Clipboard 跨线程异常。
        BeginInvoke(() =>
        {
            try
            {
                var backup = Clipboard.ContainsText() ? Clipboard.GetText() : null;
                Clipboard.SetText(text);
                SendCtrlV();
                if (backup is not null)
                    Clipboard.SetText(backup);
            }
            catch
            {
                // ignore paste failures
            }
        });
    }

    private static void SendCtrlV()
    {
        var inputs = new INPUT[4];
        inputs[0] = INPUT.KeyDown(Keys.ControlKey);
        inputs[1] = INPUT.KeyDown(Keys.V);
        inputs[2] = INPUT.KeyUp(Keys.V);
        inputs[3] = INPUT.KeyUp(Keys.ControlKey);
        SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
    }

    private void OnResize(object? sender, EventArgs e)
    {
        if (WindowState == FormWindowState.Minimized)
        {
            Hide();
        }
    }

    private void ShowFromTray()
    {
        Show();
        WindowState = FormWindowState.Normal;
        Activate();
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        UnregisterHotKey(Handle, HotkeyId);
        _tray.Visible = false;
        _recvCts?.Cancel();
        _waveIn?.Dispose();
        _ws?.Dispose();
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint type;
        public InputUnion U;

        public static INPUT KeyDown(Keys key) => new() { type = 1, U = new InputUnion { ki = new KEYBDINPUT { wVk = (ushort)key } } };
        public static INPUT KeyUp(Keys key) => new()
        {
            type = 1,
            U = new InputUnion
            {
                ki = new KEYBDINPUT { wVk = (ushort)key, dwFlags = 0x0002 }
            }
        };
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {
        [FieldOffset(0)]
        public KEYBDINPUT ki;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public nint dwExtraInfo;
    }
}

internal static class HotkeyParser
{
    public static (KeyModifiers Modifiers, Keys Key) Parse(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return (0, Keys.None);

        var parts = value.Split('+', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var mods = KeyModifiers.None;
        Keys key = Keys.None;

        foreach (var p in parts)
        {
            switch (p.ToLowerInvariant())
            {
                case "ctrl":
                case "control":
                    mods |= KeyModifiers.Control;
                    break;
                case "shift":
                    mods |= KeyModifiers.Shift;
                    break;
                case "alt":
                    mods |= KeyModifiers.Alt;
                    break;
                case "win":
                case "windows":
                    mods |= KeyModifiers.Win;
                    break;
                default:
                    if (Enum.TryParse<Keys>(p, true, out var parsedKey))
                        key = parsedKey;
                    break;
            }
        }

        return (mods, key);
    }
}

[Flags]
internal enum KeyModifiers : uint
{
    None = 0,
    Alt = 0x0001,
    Control = 0x0002,
    Shift = 0x0004,
    Win = 0x0008,
}

internal sealed class AppSettings
{
    public string ServerWsUrl { get; set; } = "ws://127.0.0.1:8000/v1/asr/stream";
    public string Lang { get; set; } = "zh";
    public int MicDeviceIndex { get; set; } = 0;
    public string Hotkey { get; set; } = "Ctrl+Shift+Space";
    public bool MinimizeToTrayOnStart { get; set; } = true;

    private static string SettingsPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "Qwen3AsrHotkeyClient",
        "settings.json");

    public static AppSettings Load()
    {
        try
        {
            if (!File.Exists(SettingsPath)) return new AppSettings();
            var json = File.ReadAllText(SettingsPath, Encoding.UTF8);
            return JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
        }
        catch
        {
            return new AppSettings();
        }
    }

    public void Save()
    {
        var dir = Path.GetDirectoryName(SettingsPath)!;
        Directory.CreateDirectory(dir);
        var json = JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(SettingsPath, json, Encoding.UTF8);
    }
}
