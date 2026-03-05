# 部署手册（V1）

## 1. 前置条件
- 安装 Docker / Docker Compose
- 机器可访问项目目录

## 2. 启动服务
```bash
cd stream_asr
docker compose up -d --build
```

## 3. 验证服务
```bash
curl -s http://127.0.0.1:8000/healthz
```
预期 `ok=true`。

## 4. 查看日志
```bash
docker compose logs -f stream_asr
```

## 5. 停止服务
```bash
docker compose down
```

## 6. 常见问题
- 端口占用：修改 `docker-compose.yml` 的映射端口
- 健康检查失败：先看容器日志，再检查 `/healthz` 返回的 `engine_fallback_reason`
- qwen3 依赖未安装：先用 `ASR_ENGINE=mock` 验证容器链路，再切到 `qwen3`
