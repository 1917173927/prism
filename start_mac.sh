#!/usr/bin/env bash
# ==============================================================================
# Prism Investment Copilot - macOS 一键启动脚本
# 规范标准: 金融工程与竞赛规范文风 (严格、客观、确定性)
# ==============================================================================

set -eo pipefail

# 1. 确定运行目录为项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || {
    echo "[FAIL] 无法进入项目根目录: $PROJECT_DIR"
    exit 1
}

# 2. 网络参数与配置
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "============================================================"
echo "Prism Investment Copilot - 决策支持工作台启动程序"
echo "============================================================"
echo "[INFO] 项目路径: $PROJECT_DIR"
echo "[INFO] 运行目标: http://${HOST}:${PORT}"

# 3. 运行环境与依赖探查
UVICORN_EXEC=""
if [ -f "$PROJECT_DIR/.venv/bin/uvicorn" ]; then
    UVICORN_EXEC="$PROJECT_DIR/.venv/bin/uvicorn"
    echo "[PASS] 定位到虚拟环境解释器: $PROJECT_DIR/.venv/bin/uvicorn"
elif command -v uv >/dev/null 2>&1; then
    UVICORN_EXEC="uv run uvicorn"
    echo "[PASS] 检测到 uv 包管理器环境"
elif command -v uvicorn >/dev/null 2>&1; then
    UVICORN_EXEC="uvicorn"
    echo "[PASS] 检测到系统路径 uvicorn"
else
    echo "[FAIL] 未检测到可用 Python 运行环境或 uvicorn 组件。"
    echo "[INFO] 请执行: uv sync 或 pip install -e \".[dev,web]\""
    exit 1
fi

# 4. 端口占用检查与自动释放
OCCUPIED_PID=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$OCCUPIED_PID" ]; then
    PROC_NAME=$(ps -p "$OCCUPIED_PID" -o comm= 2>/dev/null || echo "unknown")
    echo "[WARN] 目标端口 $PORT 当前已被占用 (PID: $OCCUPIED_PID, 进程: $PROC_NAME)"
    
    if [ ! -t 0 ]; then
        echo "[INFO] 非交互终端模式，自动注销陈旧进程 (PID: $OCCUPIED_PID)..."
        kill -9 "$OCCUPIED_PID" 2>/dev/null || true
        sleep 1
    else
        read -r -p "[PROMPT] 是否终止占用进程并重新绑定端口? [Y/n]: " user_choice
        user_choice="${user_choice:-Y}"
        if [[ "$user_choice" =~ ^[Yy]$ ]]; then
            echo "[INFO] 正在终止进程 (PID: $OCCUPIED_PID)..."
            kill -9 "$OCCUPIED_PID" 2>/dev/null || true
            sleep 1
        else
            echo "[FAIL] 端口未释放，启动中断。"
            exit 1
        fi
    fi
fi

# 5. 后台启动服务并注册信号捕获
SERVER_PID=""
cleanup() {
    echo ""
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "[STOPPED] 正在注销服务进程 (PID: $SERVER_PID)..."
        kill -TERM "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        echo "[PASS] 服务已优雅停机。"
    fi
    exit 0
}
trap cleanup INT TERM EXIT

echo "[INFO] 正在拉起 FastAPI/Uvicorn 服务进程..."
if [ "$UVICORN_EXEC" = "uv run uvicorn" ]; then
    uv run uvicorn app.api.main:app --host "$HOST" --port "$PORT" &
    SERVER_PID=$!
else
    "$UVICORN_EXEC" app.api.main:app --host "$HOST" --port "$PORT" &
    SERVER_PID=$!
fi

# 6. 健康检查轮询
echo "[CHECK] 等待服务初始化就绪 (http://${HOST}:${PORT}/api/health)..."
MAX_ATTEMPTS=30
ATTEMPT=0
SERVICE_UP=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "[FAIL] 服务进程异常退出，请查看上方日志输出排查异常。"
        exit 1
    fi

    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://${HOST}:${PORT}/api/health" 2>/dev/null || echo "000")
    if [ "$HTTP_STATUS" = "200" ]; then
        SERVICE_UP=1
        break
    fi

    sleep 0.5
    ATTEMPT=$((ATTEMPT + 1))
done

if [ $SERVICE_UP -ne 1 ]; then
    echo "[FAIL] 服务在 15 秒超时阈值内未返回正常响应 (HTTP 200)。"
    exit 1
fi

echo "[PASS] 系统健康检查通过 (HTTP 200 OK)"
echo "[INFO] 正在调用 macOS 系统默认浏览器打开工作台..."
if command -v open >/dev/null 2>&1; then
    open "http://${HOST}:${PORT}"
fi

echo "============================================================"
echo "Prism Investment Copilot 运行中"
echo "本地访问入口: http://${HOST}:${PORT}"
echo "API 文档地址: http://${HOST}:${PORT}/docs"
echo "状态: RUNNING (PID: $SERVER_PID)"
echo "注销说明: 请按 Ctrl+C 终止运行并释放端口"
echo "============================================================"

# 维持前台等待
wait "$SERVER_PID"
