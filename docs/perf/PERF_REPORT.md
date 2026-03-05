# 性能对比报告（模板）

生成时间：2026-03-05T16:53:41

## CPU 基线（已实测）
- HTTP run: `logs/smoke_qwen3/20260304_141613`
- HTTP transcribe elapsed(ms): `0`
- Stream run: `logs/stream_smoke_qwen3/20260304_141706`
- Stream partial_count: `5`
- First token latency mean/p95(ms): `460.4` / `624`
- Sentence latency mean/p95(ms): `949` / `949`

## GPU 5090（待实测）
- 状态：pending-5090-validation
- 方法：复用同一批音频、同一脚本，填入同结构指标即可横向对比
