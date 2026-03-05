# qwen3-asr-1.7b 语音转文字服务（V1）项目方案

## 1. 目标与范围

### 目标
- 基于 qwen3-asr-1.7b 提供可用的语音转文字服务
- 支持两种推理模式：
  - CPU 模式（本地开发与测试）
  - GPU 模式（5090 生产部署）
- 支持低延迟流式识别：边说边出字，句级 final
- 先做原生运行开发，Docker/Portainer 放到收尾阶段

### 非目标（V1 不做）
- 不做复杂监控栈（Prometheus/Grafana）
- 不做多模型路由
- 不做分布式扩缩容

---

## 2. 系统架构（简化版）

- API 层：FastAPI
- 流式通道：WebSocket `/v1/asr/stream`
- 文件转写：HTTP `/v1/asr/transcribe`
- 推理核心：ASR Engine（统一接口，CPU/GPU 后端可切换）
- 切句策略：VAD + 静音阈值 + 最大句长兜底
- 日志：本地滚动日志（按天切分 + request_id）

---

## 3. 运行模式设计

### CPU 模式（默认开发模式）
- `ASR_DEVICE=cpu`
- 降低并发和 chunk 频率，保证本地稳定
- 用于功能正确性、协议联调、回归测试

### GPU 模式（5090）
- `ASR_DEVICE=cuda`
- 常驻模型 + 预热
- 优化 chunk 推理节奏，降低首字延迟和句子确认延迟

---

## 4. 接口契约（V1）

### 4.1 WebSocket `/v1/asr/stream`
客户端事件：
1. `start`
```json
{ "type": "start", "session_id": "xxx", "sample_rate": 16000, "lang": "zh" }
```
2. `audio`（二进制 PCM16 mono）
3. `stop`
```json
{ "type": "stop" }
```

服务端事件：
- `partial`：增量识别
- `final`：句级确认
- `status`：状态/提示
- `error`：错误

### 4.2 HTTP `/v1/asr/transcribe`
- 输入：音频文件
- 输出：完整文本 + 基础耗时

---

## 5. 日志与排障（本地轻量）

- 日志文件：`logs/asr-service.log`
- 记录项：
  - 时间、级别、request_id、session_id
  - 关键耗时（加载、首字、final）
  - 错误栈
- 日志轮转：10MB x 5 文件

---

## 6. 验收标准（V1）

### 功能验收
- WebSocket 流式可用，支持 partial/final
- HTTP 文件转写可用
- CPU 与 GPU 两种模式可切换且均可识别

### 性能验收（阶段目标）
- CPU 开发环境：
  - 功能优先，延迟不做硬 KPI
- 5090 GPU 环境：
  - 首个 partial < 800ms（目标）
  - final 延迟 < 1.5s（普通语速目标）

### 稳定性验收
- 连续 2 小时流式测试无崩溃（V1）

---

## 7. 实施里程碑

### M1：骨架搭建（今天）
- 项目目录
- 配置系统（CPU/GPU 切换）
- FastAPI + WebSocket 基础路由
- 本地日志框架

### M2：流式主链路（下一步）
- chunk 接收与缓冲
- VAD 切句
- partial/final 输出

### M3：本地联调与回归
- CPU 模式压测脚本
- 断连重连、异常音频、长会话测试

### M4：GPU 优化与部署收尾
- 5090 上 GPU 参数调优
- Dockerfile + compose（Portainer 可导入）
- 部署文档与运维手册

---

## 8. 风险与对策

1. qwen3-asr 流式能力接口差异
- 对策：先做抽象层（ASR Engine），必要时加中间缓存逻辑

2. CPU 模式太慢影响联调
- 对策：缩短音频片段、降低采样负载、先验证事件正确性

3. GPU 环境依赖版本冲突
- 对策：锁定 PyTorch/CUDA 版本矩阵，最后阶段容器化固化

---

## 9. 目录草案

```text
stream_asr/
  docs/
    PROJECT_PLAN.md
    API_CONTRACT.md
  server/
    app.py
    config.py
    logger.py
    asr_engine/
      base.py
      qwen_engine.py
      vad.py
    routes/
      ws_stream.py
      transcribe.py
  tests/
  scripts/
  logs/
```
