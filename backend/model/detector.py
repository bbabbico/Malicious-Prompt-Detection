import os

# ── CPU 스레드 최적화  ──────────────
_N_THREADS = os.cpu_count() or 4
os.environ["OMP_NUM_THREADS"]  = str(_N_THREADS)
os.environ["MKL_NUM_THREADS"]  = str(_N_THREADS)
os.environ["OPENBLAS_NUM_THREADS"] = str(_N_THREADS)

import torch
torch.set_num_threads(_N_THREADS)

import pickle
import logging
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Any
from sentence_transformers import SentenceTransformer

_log = logging.getLogger("detector")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from intent_features import extract as extract_intent_single

BASE_DIR = Path(__file__).parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

MODEL_CONFIG = {
    0: {
        "name": "small",
        "embed_model": "intfloat/multilingual-e5-small",
        "clf_path":    ARTIFACTS_DIR / "small" / "detector_model.pkl",
        "intent_cache": ARTIFACTS_DIR / "small" / "intent_features.npy",
    },
    1: {
        "name": "large",
        "embed_model": "intfloat/multilingual-e5-large",
        "clf_path":    ARTIFACTS_DIR / "large" / "detector_model_large.pkl",
        "intent_cache": ARTIFACTS_DIR / "large" / "intent_features.npy",
    }
}

MAX_SEQ_LENGTH = 256


def _build_embedder(config: dict):
    embedder = SentenceTransformer(config["embed_model"])
    embedder.max_seq_length = MAX_SEQ_LENGTH
    print(f"  → SentenceTransformer (PyTorch) 사용: {config['embed_model']}")
    return embedder


class MaliciousPromptDetector:
    def __init__(self):
        self._models: Dict[int, Any] = {}
        self._embedders: Dict[int, Any] = {}
        self._use_intent: Dict[int, bool] = {}

    def _load_resources(self, model_type: int):
        if model_type not in self._models:
            config = MODEL_CONFIG.get(model_type)
            if not config:
                raise ValueError(f"지원하지 않는 모델 타입입니다: {model_type} (0: Small, 1: Large)")

            if not config["clf_path"].exists():
                raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {config['clf_path']}")

            _log.info(f"[모델 로딩] {config['name']} — 분류기 로드 중...")
            with open(config["clf_path"], "rb") as f:
                self._models[model_type] = pickle.load(f)
            _log.info(f"[모델 로딩] {config['name']} — 임베딩 모델 로드 중...")
            self._embedders[model_type] = _build_embedder(config)

            self._use_intent[model_type] = config["intent_cache"].exists()
            status = "Intent 피처 적용" if self._use_intent[model_type] else "Intent 피처 미적용"
            _log.info(f"[모델 로딩] {config['name']} 로드 완료 — {status}")

        return self._embedders[model_type], self._models[model_type], self._use_intent[model_type]

    def _analyze_single(self, text: str, embedder, classifier, use_intent) -> float:
        """단일 텍스트에 대한 악성 확률값 반환 (내부용)."""
        emb = embedder.encode([f"query: {text}"], show_progress_bar=False)
        if use_intent:
            intent = np.array([extract_intent_single(text)], dtype=np.float32)
            feat = np.concatenate([emb, intent], axis=1)
        else:
            feat = emb
        return float(classifier.predict(feat)[0])

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """문장 단위로 분리. 빈 문장 제외."""
        import re
        parts = re.split(r'[.?!。\n]+', text)
        return [p.strip() for p in parts if len(p.strip()) >= 5]

    def analyze(self, prompt: str, model_type: int = 0) -> Tuple[bool, int]:
        try:
            model_name = MODEL_CONFIG.get(model_type, {}).get("name", str(model_type))
            _log.info(f"[탐지] 임베딩 생성 중... (모델: e5-{model_name})")
            embedder, classifier, use_intent = self._load_resources(model_type)

            formatted_prompt = f"query: {prompt}"
            embedding = embedder.encode([formatted_prompt], show_progress_bar=False)

            if use_intent:
                intent_feat = np.array([extract_intent_single(prompt)], dtype=np.float32)
                feat = np.concatenate([embedding, intent_feat], axis=1)
                has_edu       = intent_feat[0][1]
                has_attack    = intent_feat[0][3]
                has_target    = intent_feat[0][4]
                has_defensive = intent_feat[0][8]
                has_research  = intent_feat[0][9]
                has_jailbreak = intent_feat[0][10]

                if (has_defensive or has_research) and not has_target:
                    threshold = 0.92
                elif has_edu and not has_attack and not has_target and not has_jailbreak:
                    threshold = 0.92
                else:
                    threshold = 0.58
            else:
                feat = embedding
                threshold = 0.58

            prob = classifier.predict(feat)[0]

            # ── 긴 문장 내 숨겨진 명령 감지 ──────────────────────────────
            # 전체 확률이 임계값 미만이고 다수 문장인 경우, 각 문장을 개별 분석해
            # 가장 높은 악성 확률을 최종값으로 사용
            if prob < threshold and len(prompt) > 60:
                sentences = self._split_sentences(prompt)
                if len(sentences) >= 2:
                    sent_probs = [
                        self._analyze_single(s, embedder, classifier, use_intent)
                        for s in sentences
                    ]
                    max_sent_prob = max(sent_probs)
                    if max_sent_prob > prob:
                        prob = max_sent_prob
                        # 문장별 intent도 재검사
                        if use_intent:
                            for s in sentences:
                                si = np.array([extract_intent_single(s)], dtype=np.float32)
                                has_attack    = has_attack    or bool(si[0][3])
                                has_jailbreak = has_jailbreak or bool(si[0][10])

            risk_score = int(prob * 100)

            # ── 공격/jailbreak 패턴 명시 감지 시 강제 악성 처리 ──────────
            # 방어/연구 맥락 + 특정 타겟 없음 → 모의해킹 등 정상 문맥이므로 강제 악성 제외
            if use_intent and has_attack and not (has_defensive and not has_target):
                is_malicious = True
                risk_score = max(risk_score, 70)
            elif use_intent and has_jailbreak and prob >= 0.40:
                is_malicious = True
                risk_score = max(risk_score, 60)
            else:
                is_malicious = bool(prob >= threshold)

            return is_malicious, risk_score

        except Exception as e:
            _log.error(f"[탐지] 오류 발생: {e}")
            # fail closed: 오류 시 악성으로 처리해 악성 프롬프트 통과를 방지
            raise RuntimeError(f"프롬프트 분석 중 오류 발생: {e}") from e

    def analyze_xai_explain(self, prompt: str, model_type: int = 0):
        try:
            import shap
            _log.info("[XAI] SHAP 분석 시작 — 악성 기여 단어 추출 중...")
            embedder, classifier, use_intent = self._load_resources(model_type)

            def prediction_function(texts):
                formatted_texts = [f"query: {t}" for t in texts]
                embeddings = embedder.encode(formatted_texts, show_progress_bar=False)
                if use_intent:
                    intent = np.array([extract_intent_single(t) for t in texts], dtype=np.float32)
                    feat = np.concatenate([embeddings, intent], axis=1)
                else:
                    feat = embeddings
                return classifier.predict(feat)

            # shap_values.data[0] contains tokens, shap_values.values[0] contains SHAP weights
            explainer = shap.Explainer(prediction_function, shap.maskers.Text(r"\W"))
            shap_values = explainer([prompt])
            
            highlights = []
            tokens = shap_values.data[0]
            weights = shap_values.values[0]
            
            # 가장 큰 SHAP 가중치를 기준으로 정규화 (0.0 ~ 1.0)
            max_w = max([float(w) for w in weights] + [0.0001])
            
            for t, w in zip(tokens, weights):
                normalized_w = max(0.0, float(w) / max_w)
                highlights.append({"text": str(t), "weight": normalized_w})

            top = sorted(highlights, key=lambda x: -x["weight"])[:5]
            _log.info(f"[XAI] 분석 완료 — 상위 단어: {[h['text'].strip() for h in top if h['weight'] > 0.05]}")
            return highlights
        except Exception as e:
            _log.error(f"[XAI] 오류 발생: {e}")
            return []

    def preload_models(self):
        _log.info("[모델 로딩] 프리로딩 시작 (small + large)...")
        for model_type in [0, 1]:
            embedder, _, _ = self._load_resources(model_type)
            # JIT 워밍업
            for _ in range(3):
                embedder.encode(["query: warmup"], show_progress_bar=False)
        _log.info("[모델 로딩] 프리로딩 완료 — 모든 모델 준비됨")


_detector_instance = MaliciousPromptDetector()

def preload_all_models():
    """앱 시작 시 모델을 메모리에 미리 로드하기 위한 외부 호출 함수"""
    _detector_instance.preload_models()

def analyze_prompt(prompt: str, model_type: int = 0) -> Tuple[bool, int]:
    """외부에서 호출할 메인 함수"""
    return _detector_instance.analyze(prompt, model_type)

if __name__ == "__main__":
    print("\n" + "="*50)
    print("   Malicious Prompt Detector Interactive Test")
    print("="*50)

    m_type_str = input("Select Model Type (0: Small, 1: Large) [default: 0]: ").strip()
    m_type = int(m_type_str) if m_type_str in ["0", "1"] else 0

    print(f"\nUsing {'LARGE' if m_type == 1 else 'SMALL'} model.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        user_input = input("Prompt >>> ").strip()
        if not user_input:
            continue
        if user_input.lower() in ["exit", "quit"]:
            break
        is_mal, score = analyze_prompt(user_input, model_type=m_type)
        status = " [!] MALICIOUS" if is_mal else " [v] NORMAL"
        print(f"Result: {status} | Risk Score: {score}/100")
        print("-" * 30)
