"""
컨테이너 시작 시 uvicorn 서버를 실행합니다.
"""
import subprocess
import sys

print("  서버 시작 중...")
subprocess.run([
    sys.executable, "-m", "uvicorn", "main:app",
    "--host", "0.0.0.0", "--port", "8000"
])
