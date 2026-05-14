#!/usr/bin/env python3
"""
启动 StudyLamp 后端服务器
用法：python3 server/run.py [--port 8000] [--reload]
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StudyLamp API Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    import uvicorn
    print(f"StudyLamp API 启动中 → http://{args.host}:{args.port}")
    print(f"API 文档 → http://localhost:{args.port}/docs")
    uvicorn.run(
        "server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
