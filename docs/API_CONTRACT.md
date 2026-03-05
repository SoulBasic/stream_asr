# API 契约（V1 草案）

## 1) 健康检查
### GET /healthz
响应（关键字段）：
```json
{
  "ok": true,
  "device": "cpu|cuda",
  "model_loaded": true,
  "engine_ready": true,
  "engine": "mock|qwen3",
  "backend": "mock|cpu",
  "engine_fallback_reason": null,
  "engine_capabilities": {
    "model_loaded": true,
    "is_placeholder": false,
    "model_source": "qwen3_asr|qwen_asr|mock"
  }
}
```

## 2) 文件转写
### POST /v1/asr/transcribe
- Content-Type: `multipart/form-data`
- 字段：
  - `file`: 音频文件（PCM16 mono）
  - `lang`: 可选，默认 `zh`
- 校验与错误：
  - 空文件：`400 empty file`
  - 非偶数字节（非 PCM16）：`400 invalid pcm16 payload`
  - 过短音频（<320 bytes）：`400 audio too short`
  - 引擎不可用：`503 asr engine unavailable`
  - 转写超时：`504 asr transcribe timeout`

响应：
```json
{
  "text": "...",
  "segments": [
    {"start_ms": 0, "end_ms": 1200, "text": "..."}
  ],
  "metrics": {
    "processing_ms": 1234
  }
}
```

## 3) 流式转写
### WebSocket /v1/asr/stream

客户端文本帧：
- start
```json
{ "type": "start", "session_id": "sess_001", "sample_rate": 16000, "lang": "zh" }
```
- stop
```json
{ "type": "stop" }
```

客户端二进制帧：
- PCM16 mono little-endian chunk（建议 20~40ms）

服务端文本帧：
- status
```json
{ "type": "status", "message": "session_started" }
```
- partial
```json
{ "type": "partial", "text": "我正在", "start_ms": 0, "end_ms": 680 }
```
- final
```json
{ "type": "final", "sentence_id": 3, "text": "我正在测试流式识别。", "start_ms": 0, "end_ms": 1240 }
```
- error
```json
{ "type": "error", "code": "BAD_AUDIO_FORMAT", "message": "pcm16 payload must be even-length bytes" }
```

常见 WebSocket 错误码：
- `BAD_JSON`：JSON 非法或不支持的事件
- `BAD_START`：`start` 参数不合法（例如 sample_rate 缺失/越界）
- `BAD_AUDIO_STATE`：状态不合法（未 start 就发音频，或 stop 前无音频）
- `BAD_AUDIO_FORMAT`：二进制 chunk 非 PCM16（奇数字节）
- `BAD_AUDIO_TOO_SHORT`：stop 时累计音频过短
- `SESSION_IDLE_TIMEOUT`：会话空闲超时
- `INTERNAL_ERROR`：服务内部异常
