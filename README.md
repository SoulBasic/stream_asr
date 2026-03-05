# stream_asr (mock skeleton)

一个可运行的 FastAPI ASR 服务骨架，当前引擎为 mock，实现了 HTTP 文件转写与 WebSocket 流式协议，后续可替换为 qwen3-asr。

## 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 本地启动

```bash
bash scripts/run_dev.sh
```

环境变量：
- `ASR_DEVICE=cpu|cuda`（默认 `cpu`）
- `ASR_ENGINE=mock|qwen3`（默认 `mock`）
- `ASR_LOG_PATH`（默认 `logs/asr-service.log`）
- `ASR_LOG_LEVEL`（默认 `INFO`）
- `ASR_PARTIAL_BYTES_THRESHOLD`（默认 `24000`，balanced 主档）
- `ASR_PARTIAL_INTERVAL_MS`（默认 `180`，流式 partial 最大发送间隔）
- `ASR_VAD_ENERGY_THRESHOLD`（默认 `120`，轻量 VAD 能量阈值）
- `ASR_VAD_SILENCE_MS`（默认 `350`，轻量 VAD 静音时长阈值）
- `ASR_TRANSCRIBE_TIMEOUT_MS`（默认 `15000`，HTTP 转写超时，最小 500）
- `ASR_WS_IDLE_TIMEOUT_MS`（默认 `10000`，WS 会话空闲超时，最小 1000）

## 3. API 示例

### 健康检查

```bash
curl -s http://127.0.0.1:8000/healthz
```

`/healthz` 关键字段说明（保持向后兼容）：
- `ok`：服务存活状态
- `device`：当前设备（`cpu|cuda`）
- `model_loaded`：引擎模型是否已加载（历史字段，保留）
- `engine_ready`：真实引擎就绪状态（`model_loaded=true` 且非占位且无回退原因）
- `engine`：当前引擎名（`mock|qwen3`）
- `backend`：当前后端（`mock|cpu`）
- `engine_fallback_reason`：回退原因（无回退时为 `null`）
- `engine_capabilities`：引擎能力对象，当前包含：
  - `model_loaded`：与引擎侧状态一致
  - `is_placeholder`：是否占位实现（M2 护栏）
  - `model_source`：模型来源（占位/Mock 引擎会返回该字段，例如 `qwen3-placeholder`、`mock`；若 qwen3 真实入口可用则为 `qwen3_asr` 或 `qwen_asr`）

### 文件转写

```bash
curl -X POST "http://127.0.0.1:8000/v1/asr/transcribe" \
  -F "file=@./demo.pcm" \
  -F "lang=zh"
```

### WebSocket 流式（示例）

使用 `websocat`：

```bash
# 终端1：连接并发送 start
websocat ws://127.0.0.1:8000/v1/asr/stream
# 在连接内发送文本帧：
# {"type":"start","session_id":"sess_001","sample_rate":16000,"lang":"zh"}
# 然后发送二进制 PCM chunk，最后发送：{"type":"stop"}
```

事件说明：
- `start`：开始会话，`sample_rate` 必填（范围 `8000-48000`）
- `partial`：服务端增量结果；触发条件为「达到字节阈值」或「达到时间窗口（默认 200ms）」任一满足
- `final`：收到 `stop` 后返回最终结果并关闭连接
- `error`：错误事件，主要错误码：
  - `BAD_JSON`：无效 JSON 或不支持的文本事件
  - `BAD_START`：`start` 参数不合法（例如缺少/非法 `sample_rate`）
  - `BAD_AUDIO_STATE`：状态错误（例如未 `start` 就发 audio，或未 `start` 就 `stop`）
  - `BAD_AUDIO_FORMAT`：音频格式错误（非 PCM16 偶数字节）
  - `BAD_AUDIO_TOO_SHORT`：收到 `stop` 时累计音频过短
  - `SESSION_IDLE_TIMEOUT`：会话空闲超时（长时间未收到消息）
  - `INTERNAL_ERROR`：服务内部异常

一个最小交互序列：
```text
client -> {"type":"start","sample_rate":16000,"lang":"zh"}
server -> {"type":"status","message":"session_started",...}
client -> (binary pcm chunk)
server -> {"type":"partial",...}
client -> {"type":"stop"}
server -> {"type":"final",...}
server -> (close)
```

## 4. 运行测试

```bash
pytest -q
```

## 5. qwen3 本机冒烟

用于验收 `ASR_ENGINE=qwen3` 的真实本机依赖链路（不会把 mock 回退当作通过）。

```bash
bash scripts/smoke_qwen3.sh
```

脚本行为：
- 自动以 `ASR_ENGINE=qwen3` 启动 FastAPI（后台运行，结束自动清理）
- 对 `/healthz` 做强校验，输出关键字段：
  - `engine=...`
  - `engine_ready=...`
  - `engine_capabilities=...`
- 对 `/v1/asr/transcribe` 做最小转写冒烟
- 若未提供样本音频，会自动生成 1 秒静音 wav
- 若缺少 `qwen3_asr` 与 `qwen_asr` 依赖，会明确报错并返回非 0

预期输出示例（关键行）：
- 通过时会看到多行 `PASS: ...`，以及最终 `Summary: PASS=N, FAIL=0`
- 依赖缺失时会看到：`FAIL: qwen3 dependency missing...`，并以非 0 退出

脚本会自动归档产物到 `logs/smoke_qwen3/<timestamp>/`，包含：
- `summary.json`
- `healthz.json`
- `transcribe.json`
- `uvicorn.log`

可使用校验脚本对某次 run 进行离线验收：

```bash
python scripts/verify_smoke_run.py logs/smoke_qwen3/<timestamp>
```

也可直接验收“最近一次 run”，并要求产物在指定时间窗内（避免误用过旧 PASS 记录）：

```bash
python scripts/verify_smoke_run.py --latest --root-dir logs/smoke_qwen3 --max-age-minutes 180
```

如需给 CI/自动化流程消费机器可读结果，可加 `--json`：

```bash
python scripts/verify_smoke_run.py --latest --root-dir logs/smoke_qwen3 --max-age-minutes 180 --json
```

输出示例：`{"result":"PASS","run_dir":"...","notes":[...]}`。

通过时会输出 `PASS: artifact verification ok ...`（或 `--json` 的 PASS 对象），失败会返回非 0 并给出缺失字段/文件原因。

流式冒烟产物也可离线验收（校验 start/partial/final 时序、metrics 字段与 partial 下限）：

```bash
python scripts/verify_stream_smoke_run.py --latest --root-dir logs/stream_smoke_qwen3 --max-age-minutes 180 --json
```

输出示例：`{"result":"PASS","run_dir":"logs/stream_smoke_qwen3/<timestamp>","notes":[...]}`。

## 性能报告生成（CPU 基线）

可基于最新 HTTP/流式冒烟产物自动生成性能报告：

```bash
python scripts/generate_perf_report.py \
  --smoke-root logs/smoke_qwen3 \
  --stream-root logs/stream_smoke_qwen3 \
  --out-dir docs/perf
```

产物：
- `docs/perf/perf_report.json`
- `docs/perf/PERF_REPORT.md`

说明：GPU 5090 指标位置会保留为待填充（pending-5090-validation）。

### 离线验收新鲜度策略（固定执行规范）

为避免“历史 PASS 产物误判当前状态”，HTTP 与流式离线验收统一采用双模式：

1) **CI 门禁模式（不设新鲜度）**
- 目的：验证仓库内已提交的验收产物结构与内容是否仍满足门禁规则；
- 规则：`verify_*_smoke_run.py` 不传 `--max-age-minutes`；
- 推荐命令：

```bash
python scripts/verify_smoke_run.py --latest --root-dir logs/smoke_qwen3 --json
python scripts/verify_stream_smoke_run.py --latest --root-dir logs/stream_smoke_qwen3 --json
```

2) **定时/手工实机验收模式（必须设新鲜度）**
- 目的：确认本轮刚跑出的实机结果，而不是旧 run；
- 规则：必须传 `--max-age-minutes`，建议区间 **30~180**（默认推荐 30~60）；
- 推荐命令：

```bash
python scripts/verify_smoke_run.py --latest --root-dir logs/smoke_qwen3 --max-age-minutes 30 --json
python scripts/verify_stream_smoke_run.py --latest --root-dir logs/stream_smoke_qwen3 --max-age-minutes 30 --json
```

判定口径：
- 返回 `{"result":"PASS", ...}` 才可视为通过；
- 任一脚本 FAIL 或返回非 0，必须视为验收失败并先修复后再推进。

## 6. Docker / Compose

```bash
docker compose up -d --build
curl -s http://127.0.0.1:8000/healthz
docker compose logs -f stream_asr
```

说明：
- 镜像定义：`Dockerfile`
- 编排文件：`docker-compose.yml`
- 部署手册：`docs/DEPLOYMENT.md`

## 7. 日志

- 控制台 + 本地滚动日志
- 路径：`logs/asr-service.log`
- 轮转：`10MB * 5`
