#!/bin/bash
# StudyLamp 一键启动脚本
# 用法：./start.sh [server|app|both]

set -e
cd "$(dirname "$0")"

MODE=${1:-both}

start_server() {
  echo "启动后端服务器..."
  python3 server/run.py --reload &
  SERVER_PID=$!
  echo "服务器 PID: $SERVER_PID"
  echo $SERVER_PID > .server.pid
}

start_app() {
  echo "启动 Mac 菜单栏 App..."
  python3 main.py &
  APP_PID=$!
  echo "App PID: $APP_PID"
  echo $APP_PID > .app.pid
}

stop_all() {
  [ -f .server.pid ] && kill $(cat .server.pid) 2>/dev/null; rm -f .server.pid
  [ -f .app.pid ]    && kill $(cat .app.pid)    2>/dev/null; rm -f .app.pid
  echo "已停止所有进程"
}

case $MODE in
  server) start_server ;;
  app)    start_app ;;
  stop)   stop_all ;;
  both)
    start_server
    sleep 2
    start_app
    echo ""
    echo "StudyLamp 已启动"
    echo "  API 文档: http://localhost:8000/docs"
    echo "  菜单栏图标: 查看屏幕右上角"
    echo "  停止: ./start.sh stop"
    wait
    ;;
  *)
    echo "用法: $0 [server|app|both|stop]"
    exit 1
    ;;
esac
