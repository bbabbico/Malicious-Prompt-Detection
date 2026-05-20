import pickle
import numpy as np
import os
from pathlib import Path
from typing import Tuple, Dict, Any, Union
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize
import joblib

# 경로 설정 (backend 디렉토리 기준)
BASE_DIR = Path(__file__).parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# 모델 구성 설정
# 0: e5-small + LightGBM (경량 모델)
# 1: e5-large + LightGBM (고성능 모델)
MODEL_CONFIG = {
    0: {
        "name": "small",
        "embed_model": "intfloat/multilingual-e5-small",
        "clf_path": ARTIFACTS_DIR / "small" / "detector_model.pkl"
    },
    1: {
        "name": "large",
        "embed_model": "intfloat/multilingual-e5-large",
        "clf_path": ARTIFACTS_DIR / "large" / "detector_model_large.pkl"
    }
}

class MaliciousPromptDetector:
    def __init__(self):
        # 모델 및 임베더 캐싱을 위한 딕셔너리
        self._models: Dict[int, Any] = {}
        self._embedders: Dict[int, SentenceTransformer] = {}
        
        # 클러스터링 및 이상치 탐지를 위한 서빙 아티팩트
        self._cluster_pca = None
        self._cluster_umap = None
        self._cluster_knn = None
        self._cluster_to_category = None
        self._anomaly_threshold = None
        
        # 클러스터링 매핑용 small 임베더 고정 캐싱 (차원 불일치 방지용)
        self._small_embedder_for_clustering = None

    def _load_resources(self, model_type: int):
        """모델 파일과 임베딩 모델을 메모리에 로드합니다."""
        # 1. 분류 모델 및 기본 임베더 로드
        if model_type not in self._models:
            config = MODEL_CONFIG.get(model_type)
            if not config:
                raise ValueError(f"지원하지 않는 모델 타입입니다: {model_type} (0: Small, 1: Large)")

            if not config["clf_path"].exists():
                raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {config['clf_path']}")

            print(f"[{config['name']}] 리소스 로딩 중...")
            
            # 머신러닝 분류 모델(LightGBM) 로드
            with open(config["clf_path"], "rb") as f:
                self._models[model_type] = pickle.load(f)
            
            # 임베딩 모델(SentenceTransformer) 로드
            self._embedders[model_type] = SentenceTransformer(config["embed_model"])
            
            print(f"[{config['name']}] 로드 완료.")

        # 2. 군집 매핑 및 이상치 탐지 아티팩트 로드 (최초 1회만 수행)
        if self._cluster_knn is None:
            cluster_dir = ARTIFACTS_DIR / "small"
            print("[System] 군집화 및 이상치 탐지 엔진 로드 중...")
            try:
                self._cluster_pca = joblib.load(cluster_dir / "cluster_pca.pkl")
                
                umap_path = cluster_dir / "cluster_umap.pkl"
                if umap_path.exists():
                    self._cluster_umap = joblib.load(umap_path)
                
                self._cluster_knn = joblib.load(cluster_dir / "cluster_knn.pkl")
                self._cluster_to_category = joblib.load(cluster_dir / "cluster_to_category.pkl")
                self._anomaly_threshold = float(np.load(cluster_dir / "anomaly_threshold.npy")[0])
                
                # 매핑 시에는 차원 불일치를 막기 위해 항상 multilingual-e5-small 임베더를 병행 사용함
                if model_type == 0:
                    self._small_embedder_for_clustering = self._embedders[0]
                else:
                    self._small_embedder_for_clustering = SentenceTransformer("intfloat/multilingual-e5-small")
                
                print(f"[System] 군집 매핑 엔진 로드 완료. (임계값: {self._anomaly_threshold:.5f}, 군집 수: {len(self._cluster_to_category)-1})")
            except Exception as e:
                print(f"[ERROR] 군집 매핑 아티팩트 로드 중 오류 발생 (DBSCAN.py가 먼저 실행되었는지 확인하세요): {e}")

        return self._embedders[model_type], self._models[model_type]

    def analyze(self, prompt: str, model_type: int = 0) -> Dict[str, Any]:
        """
        프롬프트를 분석하여 악성 여부, 위험도 점수, 악성 유형, 신종 공격(이상치) 여부를 반환합니다.
        
        Args:
            prompt (str): 사용자 입력 텍스트
            model_type (int): 0 (Small), 1 (Large)
            
        Returns:
            Dict[str, Any]: {
                "is_malicious": bool,
                "risk_score": int (0-100),
                "cluster_id": int 또는 None,
                "category": str 또는 None,
                "is_anomaly": bool
            }
        """
        result = {
            "is_malicious": False,
            "risk_score": 0,
            "cluster_id": None,
            "category": None,
            "is_anomaly": False
        }
        
        import traceback
        
        try:
            # prompt가 str 타입이 아닐 경우를 대비해 확실히 str로 캐스팅하고 공백을 제거함
            prompt_str = str(prompt).strip()
            
            embedder, classifier = self._load_resources(model_type)
            
            # 1. 악성 탐지 (이진 분류)
            formatted_prompt = f"query: {prompt_str}"
            embedding = embedder.encode([formatted_prompt], show_progress_bar=False)
            prob = classifier.predict(embedding)[0]
            
            is_malicious = bool(prob >= 0.5)
            risk_score = int(prob * 100)
            
            result["is_malicious"] = is_malicious
            result["risk_score"] = risk_score
            
            # 2. 악성인 경우에만 군집화 매핑 및 신종 이상치 분석을 진행 (스펙 정합성)
            if is_malicious and self._cluster_knn is not None:
                # 차원 정합성을 위해 항상 multilingual-e5-small 모델로 재임베딩 생성
                small_emb = self._small_embedder_for_clustering.encode([formatted_prompt], show_progress_bar=False)
                
                # PCA 차원 축소 (384 -> 50)
                reduced = self._cluster_pca.transform(small_emb)
                
                # UMAP 차원 축소 (50 -> 10)
                if self._cluster_umap is not None:
                    reduced = self._cluster_umap.transform(reduced)
                
                # L2 정규화 (코사인 유사도 기반 거리 정렬과 동일 효과)
                reduced = normalize(reduced, norm='l2')
                
                # KNN 이웃까지의 평균 거리를 계산하여 이상치 여부 탐지
                distances, indices = self._cluster_knn.kneighbors(reduced)
                avg_distance = float(distances[0].mean())
                
                # 이상치 임계값과 비교
                if avg_distance > self._anomaly_threshold:
                    result["is_anomaly"] = True
                    result["cluster_id"] = -1
                    result["category"] = "Noise / New Unknown Attack Type (신종 변종 공격 유형)"
                else:
                    # 정상적인 기존 유형인 경우 클러스터 번호 및 한국어 카테고리 매핑
                    cluster_id = int(self._cluster_knn.predict(reduced)[0])
                    result["is_anomaly"] = False
                    result["cluster_id"] = cluster_id
                    # 딕셔너리에서 악성 카테고리 텍스트 매핑
                    result["category"] = self._cluster_to_category.get(cluster_id, "Unknown Attack Type")
            else:
                # 안전한 프롬프트인 경우
                result["is_anomaly"] = False
                result["cluster_id"] = -2
                result["category"] = "Safe / Non-Violent"
            
            return result
            
        except Exception as e:
            print(f"[ERROR] 분석 중 예외 발생:")
            traceback.print_exc()
            return result

# 싱글톤 인스턴스
_detector_instance = MaliciousPromptDetector()

def analyze_prompt(prompt: str, model_type: int = 0) -> Dict[str, Any]:
    """외부에서 호출할 메인 함수"""
    return _detector_instance.analyze(prompt, model_type)

if __name__ == "__main__":
    import sys
    # Windows 환경에서 한글 및 다양한 유니코드 프롬프트의 깨짐과 입출력 오류 방지
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
        
    print("\n" + "="*60)
    print("   Malicious Prompt Detector & Clustering Serving Pipeline Test")
    print("="*60)
    
    # 모델 타입 선택
    m_type_str = input("Select Model Type (0: Small, 1: Large) [default: 0]: ").strip()
    m_type = int(m_type_str) if m_type_str in ["0", "1"] else 0
    
    print(f"\nUsing {'LARGE (1024-dim)' if m_type == 1 else 'SMALL (384-dim)'} model for detection.")
    print("Type 'exit' or 'quit' to stop.\n")
    
    # 미리 캐싱 로드
    _detector_instance._load_resources(m_type)
    print("="*60 + "\n")
    
    while True:
        user_input = input("Prompt >>> ").strip()
        
        if not user_input:
            continue
        if user_input.lower() in ["exit", "quit"]:
            break
            
        res = analyze_prompt(user_input, model_type=m_type)
        
        status = " [!] MALICIOUS (악성)" if res["is_malicious"] else " [v] NORMAL (정상)"
        print(f"Result: {status} | Risk Score: {res['risk_score']}/100")
        
        if res["is_malicious"]:
            print(f"  └─ Anomaly Status : {'⚠️ SHIELD ALERT: 신종 변종 공격 유형 감지!' if res['is_anomaly'] else '✅ Known Attack Type (기존 유형)'}")
            print(f"  └─ Cluster ID     : {res['cluster_id']}")
            print(f"  └─ Classified Type: \033[91m{res['category']}\033[0m")
        print("-" * 50)
