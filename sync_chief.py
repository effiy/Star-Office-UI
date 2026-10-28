#!/usr/bin/env python3
"""
Chief → Star 状态同步守护进程

每隔 2 秒从状态文件读取 Chief 的最新状态，推送到 Star-Office-UI 的 /set_state API，
让像素办公室里的 Star 实时反映 Chief DS Bot 的工作状态。

状态映射:
  idle → 待命（休息区呼吸动画）
  working/writing → 工作（办公桌打字动画）
  executing → 执行（工具动画）
  error → 告警（红色抖动）

状态文件: /tmp/chief_pixel_state.txt（一行，内容为上述状态之一）
"""

import time
import json
import requests
import os

STATE_FILE = "/tmp/chief_pixel_state.txt"
STAR_OFFICE_URL = "http://127.0.0.1:19000"

STATE_MAP = {
    "idle": "idle",
    "working": "writing",
    "writing": "writing",
    "executing": "executing",
    "researching": "researching",
    "syncing": "syncing",
    "error": "error",
}

last_state = None

print(f"🔄 Chief → Star 状态同步守护进程启动")
print(f"   状态文件: {STATE_FILE}")
print(f"   推送目标: {STAR_OFFICE_URL}/set_state")
print(f"   轮询间隔: 2s")
print()

while True:
    try:
        # 读取状态文件
        raw = "idle"
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                raw = f.read().strip().lower()
        
        # 映射到 Star-Office-UI 状态
        state = STATE_MAP.get(raw, "idle")
        
        # 状态变化时才推送
        if state != last_state:
            detail_map = {
                "idle": "待命中，随时准备服务",
                "writing": "正在写代码...",
                "executing": "执行任务中...",
                "researching": "研究中...",
                "syncing": "同步中...",
                "error": "遇到错误，需要关注",
            }
            detail = detail_map.get(state, "工作中...")
            
            r = requests.post(f"{STAR_OFFICE_URL}/set_state", json={
                "state": state,
                "detail": detail
            }, timeout=3)
            
            arrow = {"idle": "🛋", "writing": "💻", "executing": "🔧", "researching": "🔍", "syncing": "🔄", "error": "🐛"}
            print(f"{arrow.get(state, '❓')} [{state}] → {detail}  (HTTP {r.status_code})")
            last_state = state
        
    except Exception as e:
        print(f"⚠️ 同步异常: {e}")
    
    time.sleep(2)
