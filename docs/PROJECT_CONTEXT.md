# 项目上下文（给定时推进任务使用）

## 项目
qwen3-asr-1.7b 语音转文字服务

## 当前目标（V1）
- CPU/GPU 双模式可切换
- 低延迟流式识别（partial + final）
- 轻量可观测（本地日志）
- Docker/Portainer 放在后置阶段

## 已完成里程碑
- M1 骨架：FastAPI + /healthz + /v1/asr/transcribe + /v1/asr/stream
- 配置：ASR_DEVICE=cpu/cuda（默认 cpu）
- 日志：RotatingFileHandler（10MB*5）+ 控制台输出
- 测试：/healthz、/transcribe、ws 基础异常/正常流

## 当前阶段
M2：流式主链路强化（可持续优化）

## 原则
1. 每次定时执行必须有“实质推进”（代码、测试、文档、调研、验收之一）
2. 若发现阻塞，必须给出替代推进动作，不允许空转
3. 每次结束必须更新：
   - docs/PROJECT_PROGRESS.md
   - docs/PROJECT_TODO.md
4. 记录格式要包含：时间、做了什么、产出文件、测试结果、下一步
