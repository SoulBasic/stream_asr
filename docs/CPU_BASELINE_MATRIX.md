# CPU 参数组合基线（M2）

更新时间：2026-03-03 19:38 CST

## 目标
在当前 mock 引擎 + 轻量 VAD 实现下，给出一组可落地的 CPU 默认参数档位，平衡：
- 首包延迟（first partial latency）
- 断句稳定性（VAD cut）
- partial 频率（避免过高频率导致抖动）

## 已验证基础
- 自动化测试：`.venv/bin/python -m pytest -q` → `12 passed`
- 已覆盖：
  - `ASR_PARTIAL_BYTES_THRESHOLD` 最小值钳制（>=1024）
  - `ASR_PARTIAL_INTERVAL_MS` 最小值钳制（>=50ms）
  - VAD 阈值非法输入兜底
  - 流式 jitter + silence 场景下时间阈值触发 partial

## 调研结论（基于当前代码行为）

### 1) partial 触发主导关系
在 16kHz / 16bit / mono 下，码率约 **32KB/s**。

- `partial_bytes_threshold=32000` 相当于约 **1000ms** 音频量。
- 若 `partial_interval_ms=200`，则实际常由**时间阈值**先触发（约每 200ms 一次）。

=> 结论：默认组合下，`partial_interval_ms` 是首包与增量节奏的主要控制项；`partial_bytes_threshold` 主要是兜底阈值。

### 2) VAD 能量阈值敏感性（100ms 帧）
通过脚本验证（2 段静音后注入语音帧）：
- `energy_threshold` 偏高（300~500）时，中等能量语音可能仍被当作静音，断句会偏激进。
- `energy_threshold` 在 100 左右时，中等能量语音可有效重置静音累计，行为更稳。

### 3) VAD 静音时长阈值
- `silence_ms_threshold=200`：切句快，但容易碎句
- `=300`：较均衡
- `=500`：更保守，句子完整性更好但终句更晚

## 推荐默认档位（CPU / 通用语音）

### 推荐主档（balanced）
- `ASR_PARTIAL_INTERVAL_MS=180`
- `ASR_PARTIAL_BYTES_THRESHOLD=24000`
- `ASR_VAD_ENERGY_THRESHOLD=120`
- `ASR_VAD_SILENCE_MS=350`

预期：
- 首包通常 < 250ms（受 chunk 节奏影响）
- partial 频率适中（约 5~6 次/秒上限）
- 断句不易过碎，兼顾响应速度

### 低延迟档（interactive）
- `ASR_PARTIAL_INTERVAL_MS=120`
- `ASR_PARTIAL_BYTES_THRESHOLD=16000`
- `ASR_VAD_ENERGY_THRESHOLD=100`
- `ASR_VAD_SILENCE_MS=280`

### 稳定档（stability）
- `ASR_PARTIAL_INTERVAL_MS=240`
- `ASR_PARTIAL_BYTES_THRESHOLD=32000`
- `ASR_VAD_ENERGY_THRESHOLD=150`
- `ASR_VAD_SILENCE_MS=500`

## 风险与后续
- 当前结论基于 mock 引擎与能量型 VAD，迁移到 qwen3-asr-1.7b 真引擎后需复测。
- 下一步应在真实语料（安静/噪声/远讲）上做离线回放，形成客观指标（首包 P50/P95、误切率、漏切率）。
