import sys
from pathlib import Path
from typing import Dict, Any

# 프로젝트 루트를 Python path에 추가하여 backend 모듈을 찾을 수 있게 함
BASE_DIR = Path(__file__).parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

try:
    from backend.model.detector import analyze_prompt
except ImportError:
    # 모듈을 찾지 못할 경우를 대비한 대체 로직
    analyze_prompt = None

def analyze_prompt_threat(prompt: str, model_type: int = 0) -> Dict[str, Any]:
    """
    AI 모델을 사용하여 프롬프트의 위험을 분석하고 군집화 분류 및 이상치 탐지 결과를 제공합니다.
    
    Args:
        prompt (str): 사용자의 입력 프롬프트
        model_type (int): 사용할 모델 타입 (0: Small, 1: Large)
        
    Returns:
        Dict[str, Any]: {
            "is_malicious": bool,
            "risk_score": int (0-100),
            "cluster_id": int 또는 None,
            "category": str 또는 None,
            "is_anomaly": bool
        }
    """
    if analyze_prompt:
        return analyze_prompt(prompt, model_type)
    
    # 모델 로드 실패 시 기본값 (정상 처리)
    print("Warning: MaliciousPromptDetector not found. Returning default values.")
    return {
        "is_malicious": False,
        "risk_score": 0,
        "cluster_id": None,
        "category": None,
        "is_anomaly": False
    }
