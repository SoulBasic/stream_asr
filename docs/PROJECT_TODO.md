# 项目待办（滚动维护）

## P0（当前）
- [x] 将 mock ASR engine 替换为 qwen3-asr-1.7b 真引擎适配层（先 CPU，2026-03-04 14:17 CST 已在真实依赖环境完成 `/healthz`、`/v1/asr/transcribe`、`/v1/asr/stream` 复验并通过离线验收；证据：`logs/smoke_qwen3/20260304_141613/`、`logs/stream_smoke_qwen3/20260304_141706/`）
- [x] 固化离线验收新鲜度策略到文档（2026-03-04 14:40 CST：README 新增“离线验收新鲜度策略（固定执行规范）”，明确双模式：CI 不设 `--max-age-minutes`；Cron/手工验收必设 30-180 分钟，并给出 HTTP/流式双脚本标准命令）
- [x] 建立双引擎装配与降级护栏（ASR_ENGINE + engine_factory + healthz 可观测）（2026-03-03 20:45 CST：新增 `server/asr_engine/engine_factory.py` 与 `server/asr_engine/qwen3_adapter.py`，qwen3 依赖缺失自动回退 mock；`.venv/bin/python -m pytest -q` 22 通过）
- [x] 补齐 qwen3 路径的工厂正向验收与适配器契约测试（2026-03-03 20:59 CST：`tests/test_engine_factory.py` 新增 qwen3 依赖可用正向选择断言；新增 `tests/test_qwen3_adapter_contract.py` 覆盖 transcribe/partial/final 契约与空音频边界；`.venv/bin/python -m pytest -q` 25 通过）
- [x] 落地引擎能力可观测护栏（healthz + capabilities 契约）（2026-03-03 21:21 CST：`BaseASREngine` 新增 `engine_capabilities()`；mock/qwen3 统一上报 `is_placeholder/model_source`；`/healthz` 新增 `engine_capabilities`；补充 API/契约测试与 README；`.venv/bin/python -m pytest -q` 27 通过）
- [x] 增加 `/v1/asr/transcribe` 双引擎输出结构一致性回归（2026-03-03 22:01 CST：新增 `tests/test_transcribe_consistency.py`，覆盖 `ASR_ENGINE=mock/qwen3` 顶层字段、metrics 与 segments 结构/类型一致性；并在 `Qwen3ASREngine` 新增 segments 归一化；`.venv/bin/python -m pytest -q` 29 通过）
- [x] 接入 qwen3 CPU 真实 `transcribe` 推理（首版）并保持现有 API 契约不变（2026-03-04 12:47 CST：已在真实依赖环境完成 `scripts/smoke_qwen3.sh` + `verify_smoke_run.py --json` 实机验收，证据见 `logs/smoke_qwen3/20260304_124722/`）
- [x] 完成真实音频样本的流式实机验证（`/v1/asr/stream`）（2026-03-04 12:47 CST：新增 `scripts/stream_smoke_qwen3.py`，使用 `logs/audio_samples/tts_zh_16k.wav` 验证通过，`partial_count=5`，证据见 `logs/stream_smoke_qwen3/20260304_124752/`）
- [x] 增加冒烟产物离线验收脚本（summary/healthz/transcribe/uvicorn）并补回归（2026-03-04 00:20 CST：新增 `scripts/verify_smoke_run.py` 与 `tests/test_verify_smoke_run.py`，覆盖通过/失败场景；README 增加验收命令；`.venv/bin/python -m pytest -q` 36 通过）
- [x] 加严离线验收一致性校验（summary 路径一致 + transcribe.segments 结构合法性）（2026-03-04 00:38 CST：`scripts/verify_smoke_run.py` 新增 `_verify_summary_consistency()` 与 `_verify_transcribe_segments()`；`tests/test_verify_smoke_run.py` 新增路径不一致/segment 非法失败回归；`.venv/bin/python -m pytest -q` 38 通过）
- [x] 离线验收支持“最新 run 自动选择 + 新鲜度门槛”（2026-03-04 00:58 CST：`scripts/verify_smoke_run.py` 新增 `--latest/--root-dir/--max-age-minutes` 与 `_resolve_latest_run_dir()`、`_assert_run_fresh()`；`tests/test_verify_smoke_run.py` 新增最新目录选择与超时失败回归；README 增补命令示例；`.venv/bin/python -m pytest -q` 40 通过）
- [x] 离线验收支持 `--json` 机器可读输出（2026-03-04 01:20 CST：`scripts/verify_smoke_run.py` 新增 `--json` 与 `_json_report()`，PASS/FAIL 均可输出结构化结果；`tests/test_verify_smoke_run.py` 新增 CLI JSON 成功/失败回归；README 新增 CI 用法示例；`.venv/bin/python -m pytest -q` 42 通过）
- [x] 新增流式离线验收脚本（基于 `logs/stream_smoke_qwen3/<timestamp>/events.jsonl` 校验 start/partial/final 时序与指标字段）（2026-03-04 13:15 CST：新增 `scripts/verify_stream_smoke_run.py` 与 `tests/test_verify_stream_smoke_run.py`，支持 `--latest/--root-dir/--max-age-minutes/--json`；实测 `--latest` 验收 PASS，见 `logs/stream_smoke_qwen3/20260304_124752/`）
- [x] 将流式离线验收接入 CI（2026-03-04 13:45 CST：新增 `.github/workflows/stream-verify.yml`，在 GitHub Actions 中执行 `pytest -q` + `python scripts/verify_stream_smoke_run.py --latest --root-dir logs/stream_smoke_qwen3 --json`，完成 artifact 门禁）
- [x] 增加 qwen3 本机冒烟验收脚本与基础回归（2026-03-03 22:18 CST：新增 `scripts/smoke_qwen3.sh`，覆盖依赖预检、`/healthz` 强校验、`/v1/asr/transcribe` 最小冒烟与 PASS/FAIL 汇总；新增 `tests/test_smoke_script.py` 与 README 章节；`.venv/bin/python -m pytest -q` 31 通过）
- [x] 新增 `engine_ready` 就绪信号并接入冒烟强校验（2026-03-03 23:18 CST：`/healthz` 新增 `engine_ready` 字段（`model_loaded && !is_placeholder && fallback_reason is None`）；`scripts/smoke_qwen3.sh` 增加 `engine_ready` 判定；同步更新 `tests/test_api.py`、`tests/test_api_qwen3_runtime_fallback.py`、`tests/test_smoke_script.py` 与 README；`.venv/bin/python -m pytest -q` 33 通过）
- [x] 增加 qwen3 运行时失败回退护栏（2026-03-03 22:39 CST：`Qwen3ASREngine.transcribe` 新增异常/非法返回兜底，故障时回退占位输出并上报 `runtime_fallback_reason`；新增 `test_qwen3_transcribe_runtime_failure_falls_back_to_placeholder`；`.venv/bin/python -m pytest -q` 32 通过）
- [x] 增加 API 级黑盒回归：qwen3 运行时异常下 transcribe 可用性 + healthz 回退原因联动（2026-03-03 23:00 CST：`server/app.py` 将 `engine_fallback_reason` 优先联动运行期 `engine_capabilities.fallback_reason`；新增 `tests/test_api_qwen3_runtime_fallback.py`，验证 `ASR_ENGINE=qwen3` + 后端异常注入时 `/v1/asr/transcribe` 返回 200 且 `/healthz` 回退原因一致；`.venv/bin/python -m pytest -q` 33 通过）
- [x] 增加 API 级黑盒回归：qwen3 运行时异常后可恢复成功且清除 fallback 状态（2026-03-03 23:42 CST：`tests/test_api_qwen3_runtime_fallback.py` 新增“首调失败、次调恢复”用例，验证 `/healthz.engine_ready` 从 false 恢复为 true，`engine_fallback_reason` 与 `engine_capabilities.fallback_reason` 自动清空；`.venv/bin/python -m pytest -q tests/test_api_qwen3_runtime_fallback.py` 2 通过，全集 `.venv/bin/python -m pytest -q` 34 通过）
- [x] 增加流式端到端测试（更真实 chunk 时序）（2026-03-03 18:58 CST：新增抖动+静音间隙场景，验证时间阈值触发 partial 与延迟指标关系，`.venv/bin/python -m pytest -q` 通过）
- [x] 增加首字延迟/句子延迟日志字段（2026-03-03 18:39 CST：已在 ws partial/final 回包与日志落地，并补测试）
- [x] 完成 CPU 参数安全边界回归（Config + VAD）（2026-03-03 19:20 CST：新增 `tests/test_config_vad_baseline.py`，覆盖配置兜底/钳制与 VAD 切句核心行为，`.venv/bin/python -m pytest -q` 通过）
- [x] 在 CPU 环境完成参数组合基线（partial interval / bytes threshold / VAD）并给出推荐默认档位（2026-03-03 19:38 CST：新增 `docs/CPU_BASELINE_MATRIX.md`，沉淀 balanced/interactive/stability 三档建议；`.venv/bin/python -m pytest -q` 通过）
- [x] 将推荐主档（balanced）落到默认配置并补参数切换回归测试（2026-03-03 20:01 CST：`server/config.py` 默认值更新为 24000/180/120/350；新增默认档与 stability 切换回归测试；`.venv/bin/python -m pytest -q` 通过）
- [x] 补“引擎能力契约测试”（为 mock→qwen3 真引擎替换建立兼容护栏）（2026-03-03 20:20 CST：新增 `tests/test_engine_contract.py`，覆盖 Base 抽象可实现性 + Mock transcribe/partial/final 字段/类型/时长一致性；`.venv/bin/python -m pytest -q` 通过）

## P1（随后）
- [x] Windows 热键客户端首版（2026-03-04 14:46 CST：新增 WinForms 工程，支持麦克风选择/快捷键/托盘常驻/WebSocket 实时推流/partial+final 自动粘贴；含 self-contained 单文件 EXE 打包说明）
- [ ] Windows 真机打包与链路验收（麦克风、快捷键、后台驻留、实时粘贴）
- [ ] GPU(5090) 实机联调与参数优化
- [x] 补充异常恢复策略（超时、断流、坏音频）
  - [x] 子项A：`/v1/asr/transcribe` 引擎异常不再直接 500，改为 503 可恢复错误（2026-03-05）
  - [x] 子项B：WebSocket 重连幂等会话基线（同 `session_id` 重连允许，新增回归测试）（2026-03-05）
  - [x] 子项C：坏音频/极短音频策略（HTTP+WS 统一错误码与提示，新增回归测试）（2026-03-05）
  - [x] 子项D：超时恢复策略（HTTP 504 + WS 空闲超时错误码 + 配置化阈值）（2026-03-05）
- [ ] 提供性能对比报告（CPU vs GPU）
  - [x] 子项A：CPU 基线自动汇总脚本 + 报告模板（`scripts/generate_perf_report.py`，输出 `docs/perf/*`）（2026-03-05）
  - [ ] 子项B：5090 实测数据回填（同口径指标）

## P2（后置）
- [x] Dockerfile + compose（Portainer Stack）
- [x] 部署手册（基础版）+ 常见故障排查（2026-03-05）
