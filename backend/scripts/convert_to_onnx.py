"""
SentenceTransformer 모델을 ONNX + INT8 양자화로 변환하는 스크립트.
"""
import sys
from pathlib import Path
from optimum.onnxruntime import ORTModelForFeatureExtraction, ORTQuantizer
from optimum.onnxruntime.configuration import AutoQuantizationConfig
from transformers import AutoTokenizer

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
ONNX_DIR = ARTIFACTS_DIR / "onnx"

MODELS = [
    ("intfloat/multilingual-e5-small", "e5-small"),
    ("intfloat/multilingual-e5-large", "e5-large"),
]


def convert(model_name: str, folder: str):
    out_dir = ONNX_DIR / folder
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  {folder}  ({model_name})")
    print(f"{'='*60}")

    for old in out_dir.glob("*.onnx"):
        old.unlink()

    print("  [1/3] ONNX export 중...")
    model = ORTModelForFeatureExtraction.from_pretrained(model_name, export=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"  [1/3] 완료 -> {out_dir}/model.onnx")

    print("  [2/3] INT8 quantization 중...")
    quantizer = ORTQuantizer.from_pretrained(out_dir, file_name="model.onnx")
    qconfig = AutoQuantizationConfig.avx2(is_static=False, per_channel=False)
    quantizer.quantize(save_dir=out_dir, quantization_config=qconfig)
    print(f"  [2/3] 완료 -> {out_dir}/model_quantized.onnx")

    fp32_size = (out_dir / "model.onnx").stat().st_size / 1024 / 1024
    int8_size = (out_dir / "model_quantized.onnx").stat().st_size / 1024 / 1024
    print(f"  [3/3] 파일 크기: FP32={fp32_size:.1f}MB -> INT8={int8_size:.1f}MB ({int8_size/fp32_size*100:.0f}%)")


if __name__ == "__main__":
    print("ONNX + INT8 변환 시작")
    for model_name, folder in MODELS:
        convert(model_name, folder)
    print(f"\n변환 완료. 저장 위치: {ONNX_DIR}")
