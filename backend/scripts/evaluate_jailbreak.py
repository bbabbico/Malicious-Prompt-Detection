import sys
import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics import f1_score, confusion_matrix
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

try:
    from datasets import load_dataset
except ImportError:
    print("Error: 'datasets' library is not installed. Please install it with 'pip install datasets'.")
    sys.exit(1)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

# Paths
BASE_DIR = Path(__file__).parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# Model Configurations
MODEL_CONFIG = {
    "small_lgb": {
        "name": "Small (LightGBM)",
        "embed_model": "intfloat/multilingual-e5-small",
        "clf_path": ARTIFACTS_DIR / "small" / "detector_model.pkl",
        "type": "lgb"
    },
    "large_lgb": {
        "name": "Large (LightGBM)",
        "embed_model": "intfloat/multilingual-e5-large",
        "clf_path": ARTIFACTS_DIR / "large" / "detector_model_large.pkl",
        "type": "lgb"
    },
    "small_xgb": {
        "name": "Small (XGBoost)",
        "embed_model": "intfloat/multilingual-e5-small",
        "clf_path": ARTIFACTS_DIR / "small" / "detector_model_xgb_small.json",
        "type": "xgb"
    },
    "large_xgb": {
        "name": "Large (XGBoost)",
        "embed_model": "intfloat/multilingual-e5-large",
        "clf_path": ARTIFACTS_DIR / "large" / "detector_model_xgb_large.json",
        "type": "xgb"
    }
}

def calculate_fpr(y_true, y_pred):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    return fpr

def load_classifier(config: Dict[str, Any]):
    clf_path = config["clf_path"]
    if config["type"] == "lgb":
        with open(clf_path, "rb") as f:
            return pickle.load(f)
    elif config["type"] == "xgb":
        if not XGB_AVAILABLE:
            raise ImportError("xgboost is not installed.")
        model = xgb.Booster()
        model.load_model(str(clf_path))
        return model
    return None

def evaluate_model(model_key: str, dataset_name: str = "jackhhao/jailbreak-classification"):
    config = MODEL_CONFIG.get(model_key)
    if not config:
        print(f"Unknown model key: {model_key}")
        return

    clf_path = config["clf_path"]
    if not clf_path.exists():
        print(f"Model file not found: {clf_path}")
        return

    if config["type"] == "xgb" and not XGB_AVAILABLE:
        print(f"Skipping {config['name']} (xgboost not installed)")
        return

    print(f"\n" + "="*60)
    print(f" Evaluating Model: {config['name']}")
    print(f"="*60)
    
    # 1. Load Dataset
    print(f"Loading dataset: {dataset_name}...")
    ds = load_dataset(dataset_name)
    
    available_splits = list(ds.keys())
    eval_split = "test" if "test" in available_splits else "train"
    print(f"Using split: {eval_split} ({len(ds[eval_split])} samples)")
    
    df = pd.DataFrame(ds[eval_split])
    
    # Map types to labels: jailbreak -> 1, benign -> 0
    if 'type' in df.columns:
        df['label'] = df['type'].map({'jailbreak': 1, 'benign': 0})
    elif 'label' in df.columns:
        # Some datasets might already have 'label'
        pass
    else:
        print("Error: Could not find label column (expected 'type' or 'label')")
        return
    
    y_true = df['label'].values
    prompts = df['prompt'].tolist()

    # 2. Load Models
    print(f"Loading embedding model: {config['embed_model']}...")
    embedder = SentenceTransformer(config["embed_model"])
    
    print(f"Loading classifier: {clf_path.name}...")
    classifier = load_classifier(config)

    # 3. Generate Embeddings
    print("Generating embeddings (adding 'query: ' prefix)...")
    formatted_prompts = [f"query: {p}" for p in prompts]
    embeddings = embedder.encode(formatted_prompts, batch_size=32, show_progress_bar=True)

    # 4. Inference
    print("Running inference...")
    if config["type"] == "lgb":
        y_prob = classifier.predict(embeddings)
    elif config["type"] == "xgb":
        y_prob = classifier.predict(xgb.DMatrix(embeddings))
    
    y_pred = (y_prob >= 0.5).astype(int)

    # 5. Metrics
    f1 = f1_score(y_true, y_pred)
    fpr = calculate_fpr(y_true, y_pred)
    
    print(f"\n[Final Results for {config['name']}]")
    print(f"F1 Score: {f1:.4f}")
    print(f"FPR (False Positive Rate): {fpr:.4f} ({fpr*100:.2f}%)")
    
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    print(f"Confusion Matrix: TN={tn}, FP={fp}, FN={fn}, TP={tp}")
    print(f"Total Samples: {len(y_true)}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate malicious prompt detector models.")
    parser.add_argument("--model", type=str, choices=list(MODEL_CONFIG.keys()) + ["all"], default="all",
                        help="Model to evaluate (default: all)")
    args = parser.parse_args()

    if args.model == "all":
        for key in MODEL_CONFIG.keys():
            try:
                evaluate_model(key)
            except Exception as e:
                print(f"Error evaluating {key}: {e}")
    else:
        evaluate_model(args.model)
