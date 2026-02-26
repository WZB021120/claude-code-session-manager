#!/bin/bash

# Session Manager Web 启动脚本

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
WEB_DIR="$SKILL_DIR/assets/web"

echo "🚀 Session Manager Web 启动中..."

# 检查依赖
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "❌ 错误: 未找到 node"
    exit 1
fi

# 安装 Python 依赖
echo "📦 检查 Python 依赖..."
pip3 install flask flask-cors -q

# 安装前端依赖
if [ ! -d "$WEB_DIR/node_modules" ]; then
    echo "📦 安装前端依赖..."
    cd "$WEB_DIR"
    npm install
fi

# 启动后端 API
echo "🔧 启动后端 API (端口 5001)..."
cd "$SCRIPT_DIR"
python3 api.py &
API_PID=$!

# 等待 API 启动
sleep 2

# 启动前端开发服务器
echo "🎨 启动前端服务器 (端口 3000)..."
cd "$WEB_DIR"
npm run dev &
WEB_PID=$!

echo ""
echo "✅ Session Manager Web 已启动！"
echo ""
echo "📍 访问地址: http://localhost:3000"
echo "📍 API 地址: http://localhost:5001"
echo ""
echo "按 Ctrl+C 停止服务"

# 捕获退出信号
trap "echo ''; echo '🛑 正在停止服务...'; kill $API_PID $WEB_PID 2>/dev/null; exit" INT TERM

# 等待进程
wait
