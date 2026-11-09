import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
import httpx
import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="启动或停止智链产教本地服务")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    runtime = ROOT / "runtime" / "server"
    runtime.mkdir(parents=True, exist_ok=True)
    pid_file = runtime / "pid"
    if args.stop:
        if not pid_file.exists():
            raise SystemExit("没有本项目保存的进程记录")
        process = psutil.Process(int(pid_file.read_text()))
        targets = list(reversed(process.children(recursive=True))) + [process]
        for target in targets:
            command = target.cmdline()
            if not any(str(Path(arg).resolve()) == str(Path(__file__).resolve()) for arg in command if arg.endswith("serve.py")):
                raise SystemExit("进程归属不匹配，未终止进程")
        for target in targets:
            try:
                target.terminate()
            except psutil.NoSuchProcess:
                continue
        _, alive = psutil.wait_procs(targets, timeout=10)
        if alive:
            raise SystemExit("本项目进程尚未退出，保留进程记录以便检查")
        pid_file.unlink()
        print("本项目服务已停止")
        return
    if args.background:
        if pid_file.exists():
            process_id = int(pid_file.read_text())
            if psutil.pid_exists(process_id):
                raise SystemExit("已有进程记录，请先检查服务状态或停止本项目服务")
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        executable = str(pythonw if pythonw.exists() else Path(sys.executable))
        with (runtime / "server.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen([executable, str(Path(__file__).resolve()), "--port", str(args.port), "--host", args.host], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        pid_file.write_text(str(process.pid))
        deadline = time.monotonic() + 45
        with httpx.Client(timeout=1, trust_env=False) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pid_file.unlink(missing_ok=True)
                    raise SystemExit("服务启动失败，请查看runtime/server/server.log")
                try:
                    response = client.get(f"http://127.0.0.1:{args.port}/api/health")
                    ready = response.status_code == 200 and response.json().get("name") == "智链产教"
                except httpx.HTTPError:
                    ready = False
                if ready:
                    family = {process.pid, *(p.pid for p in psutil.Process(process.pid).children(recursive=True))}
                    listening = any(c.pid in family and c.status == "LISTEN" and c.laddr.port == args.port for c in psutil.net_connections(kind="tcp"))
                    if listening:
                        print(f"服务已就绪 http://127.0.0.1:{args.port}，进程 {process.pid}")
                        return
                time.sleep(.15)
        raise SystemExit("服务未在45秒内就绪，请查看runtime/server/server.log")
    from backend.app import create_app
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
