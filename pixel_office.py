#!/usr/bin/env python3
"""像素办公室管理工具 v2 — Star-Office + Sync Bridge + DS Bot Watcher"""

import os, sys, time, json, signal, subprocess
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
PID_MAP = {
    "star":  ("/tmp/star-office.pid",      19000),
    "bridge":("/tmp/chief-sync-bridge.pid", 19001),
    "watcher":("/tmp/ds-bot-watcher.pid",   None),
}
SCRIPTS = {
    "star":   ("backend/app.py",   "Star-Office-UI"),
    "bridge": ("sync_bridge.py",   "Sync Bridge"),
    "watcher":("ds_bot_watcher.py","DS Bot Watcher"),
}

def _pid(name):
    try:
        with open(PID_MAP[name][0]) as f: return int(f.read().strip())
    except: return None
def _alive(pid): return bool(pid) and not os.kill(pid, 0) if False else (lambda p: p and not (lambda: os.kill(p,0))() if False else True)(pid) if False else True  # simple: just check PID file
def _alive(pid):
    if not pid: return False
    try: os.kill(pid, 0); return True
    except OSError: return False
def _kill(name, path):
    pid = _pid(name)
    if pid and _alive(pid):
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        if _alive(pid): os.kill(pid, signal.SIGKILL)
        print(f"  ✓ 停止 {SCRIPTS[name][1]} (PID {pid})")
    try: os.remove(path)
    except: pass

def status():
    print("═══ 像素办公室 v2 ═══\n")
    for name in ["star","bridge","watcher"]:
        pid_file, port = PID_MAP[name]
        pid = _pid(name)
        ok = _alive(pid)
        label = SCRIPTS[name][1]
        print(f"  {'🟢' if ok else '🔴'} {label:18s}", end="")
        if port: print(f" :{port}", end="")
        print(f"  PID={pid or '—'}")
    print()
    try:
        r = requests.get("http://127.0.0.1:19000/agents", timeout=2)
        agents = r.json()
        act = sum(1 for a in agents if a['state']!='idle')
        print(f"  👥 {len(agents)} 个 Agent（{act} 活跃）")
    except: pass
    print()

def start():
    for name in ["star","bridge","watcher"]:
        pid_file, _ = PID_MAP[name]
        script, label = SCRIPTS[name]
        if _alive(_pid(name)):
            print(f"  {label} 已在运行")
            continue
        p = subprocess.Popen([sys.executable, script], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(pid_file,"w") as f: f.write(str(p.pid))
        time.sleep(1)
        print(f"  ✓ {label} 启动 (PID {p.pid})")
    print()
    status()

def stop():
    for name in ["watcher","bridge","star"]:
        pid_file, _ = PID_MAP[name]
        _kill(name, pid_file)
    print("\n  已全部停止")

def restart():
    stop(); time.sleep(2); start()

def main():
    cmd = sys.argv[1] if len(sys.argv)>1 else ""
    {"start":start,"stop":stop,"restart":restart,"status":status}.get(cmd, lambda: print(__doc__))()

if __name__=="__main__":
    main()