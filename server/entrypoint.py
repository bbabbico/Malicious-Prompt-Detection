"""
컨테이너 시작 시 ONNX 모델 존재 여부를 확인하고,
없으면 변환 후 uvicorn 서버를 실행합니다.

변환된 ONNX 파일은 ./backend 볼륨에 저장되므로
최초 1회만 변환이 실행됩니다.
"""
import subprocess
import sys
from pathlib import Path

ONNX_SMALL = Path("/app/backend/artifacts/onnx/e5-small/model_quantized.onnx")
ONNX_LARGE = Path("/app/backend/artifacts/onnx/e5-large/model_quantized.onnx")
CONVERT_SCRIPT = Path("/app/backend/scripts/convert_to_onnx.py")

if not ONNX_SMALL.exists() or not ONNX_LARGE.exists():
    print("=" * 60)
    print("  ONNX 모델 없음 → 변환 시작 (최초 1회, 약 10~20분 소요)")
    print("=" * 60)
    subprocess.run([sys.executable, str(CONVERT_SCRIPT)], check=True)
    print("  ONNX 변환 완료")
else:
    print("  ONNX 모델 확인 완료 → 서버 시작")

subprocess.run([
    sys.executable, "-m", "uvicorn", "main:app",
    "--host", "0.0.0.0", "--port", "8000"
])
