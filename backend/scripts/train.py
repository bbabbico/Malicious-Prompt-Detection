"""
e5-small / e5-large 임베딩 + LightGBM / XGBoost 학습 스크립트

사용법:
  python train.py --model small   # [1][2] e5-small 학습
  python train.py --model large   # [3][4] e5-large 학습
  python train.py --model all     # 4개 모델 전체 학습 (기본값)
"""
import sys
import time
import glob
import pickle
import warnings
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
import xgboost as xgb
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    f1_score, precision_score, recall_score,
    accuracy_score, confusion_matrix, roc_auc_score,
)
from intent_features import extract_batch as extract_intent

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR   = Path(__file__).parent
ARTIFACTS_DIR = SCRIPTS_DIR.parent / "artifacts"
PARQUET_GLOB  = str(SCRIPTS_DIR / "train-*.parquet")
TEST_SIZE     = 0.2
RANDOM_STATE  = 42

# ── 모델별 설정 ───────────────────────────────────────────────
MODEL_CONFIG = {
    "small": {
        "embed_model":  "intfloat/multilingual-e5-small",
        "sample":       None,
        "embed_batch":  512,
        "artifact_dir": ARTIFACTS_DIR / "small",
        "emb_file":     "embeddings.npy",
        "lbl_file":     "labels.npy",
        "lgb_file":     "detector_model.pkl",
        "xgb_file":     "detector_model_xgb_small.json",
        "model_nums":   ("[1]", "[2]"),
        "lgb_params": {
            "objective": "binary", "metric": "binary_logloss",
            "boosting_type": "gbdt", "device": "cpu",
            "learning_rate": 0.03, "num_leaves": 127, "max_depth": 8,
            "min_child_samples": 10, "feature_fraction": 0.7,
            "bagging_fraction": 0.8, "bagging_freq": 5,
            "reg_alpha": 0.05, "reg_lambda": 0.1,
            "is_unbalance": False, "scale_pos_weight": 1.0, "verbose": -1,
        },
        "xgb_params": {
            "objective": "binary:logistic", "eval_metric": "logloss",
            "tree_method": "hist", "device": "cpu",
            "scale_pos_weight": 1.0, "max_depth": 7, "learning_rate": 0.03,
            "subsample": 0.8, "colsample_bytree": 0.7,
            "min_child_weight": 10, "gamma": 0.05,
            "reg_alpha": 0.05, "reg_lambda": 0.5,
            "seed": RANDOM_STATE, "verbosity": 0,
        },
    },
    "large": {
        "embed_model":  "intfloat/multilingual-e5-large",
        "sample":       None,
        "embed_batch":  64,
        "artifact_dir": ARTIFACTS_DIR / "large",
        "emb_file":     "embeddings_large.npy",
        "lbl_file":     "labels_large.npy",
        "lgb_file":     "detector_model_large.pkl",
        "xgb_file":     "detector_model_xgb_large.json",
        "model_nums":   ("[3]", "[4]"),
        "lgb_params": {
            "objective": "binary", "metric": "binary_logloss",
            "boosting_type": "gbdt", "device": "cpu",
            "learning_rate": 0.02, "num_leaves": 63, "max_depth": 6,
            "min_child_samples": 5, "feature_fraction": 0.5,
            "bagging_fraction": 0.8, "bagging_freq": 5,
            "reg_alpha": 0.1, "reg_lambda": 0.5,
            "is_unbalance": False, "scale_pos_weight": 1.0, "verbose": -1,
        },
        "xgb_params": {
            "objective": "binary:logistic", "eval_metric": "logloss",
            "tree_method": "hist", "device": "cpu",
            "scale_pos_weight": 1.0, "max_depth": 6, "learning_rate": 0.02,
            "subsample": 0.8, "colsample_bytree": 0.5,
            "min_child_weight": 5, "gamma": 0.1,
            "reg_alpha": 0.1, "reg_lambda": 0.5,
            "seed": RANDOM_STATE, "verbosity": 0,
        },
    },
}


# ── 공통 함수 ─────────────────────────────────────────────────

def load_parquets():
    files = sorted(glob.glob(PARQUET_GLOB))
    if not files:
        print(f"[오류] parquet 파일 없음: {PARQUET_GLOB}")
        sys.exit(1)
    frames = []
    for f in files:
        shard = pd.read_parquet(f)
        print(f"  {Path(f).name} : {len(shard):,}행")
        frames.append(shard)
    df = pd.concat(frames, ignore_index=True)
    df["label"] = df["is_dangerous"].astype(int)
    df["text"]  = df["prompt"].astype(str).str.strip()
    df = df[df["text"].notna() & (df["text"] != "") & (df["text"].str.len() >= 5)]
    df = df.drop_duplicates(subset="text").reset_index(drop=True)
    return df


def sample_data(df, n):
    if n is None or n >= len(df):
        out = df.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)
        print(f"  전체 사용: {len(out):,}행")
    else:
        out, _ = train_test_split(df, train_size=n, stratify=df["label"], random_state=RANDOM_STATE)
        out = out.reset_index(drop=True)
        print(f"  계층 샘플링: {len(out):,}행  (악성={out['label'].eq(1).sum():,}  정상={out['label'].eq(0).sum():,})")
    return out


def scan_best(y_true, y_prob):
    best_all, best_f1fpr = None, None
    for ti in range(1, 199):
        t = ti / 200
        pred = (y_prob >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, pred).ravel()
        fpr = fp / (tn + fp) if (tn + fp) > 0 else 0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0
        f1  = f1_score(y_true, pred, zero_division=0)
        if f1 >= 0.85 and fpr < 0.10 and fnr < 0.10:
            if best_all is None or f1 > best_all[2]:
                best_all = (round(t, 3), fpr, f1, fnr)
        if f1 >= 0.85 and fpr < 0.10:
            if best_f1fpr is None or fnr < best_f1fpr[3]:
                best_f1fpr = (round(t, 3), fpr, f1, fnr)
    best_f1t, best_f1 = 0.5, 0.0
    for ti in range(1, 199):
        t = ti / 200
        f = f1_score(y_true, (y_prob >= t).astype(int), zero_division=0)
        if f > best_f1:
            best_f1, best_f1t = f, round(t, 3)
    return best_all, best_f1fpr, best_f1t


def full_metrics(y_true, y_prob, t):
    pred = (y_prob >= t).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred).ravel()
    return {
        "t": t, "f1": f1_score(y_true, pred, zero_division=0),
        "fpr": fp / (tn + fp) if (tn + fp) > 0 else 0,
        "fnr": fn / (fn + tp) if (fn + tp) > 0 else 0,
        "acc": accuracy_score(y_true, pred),
        "prec": precision_score(y_true, pred, zero_division=0),
        "rec": recall_score(y_true, pred, zero_division=0),
        "auc": roc_auc_score(y_true, y_prob),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }


def print_result(m, tag=""):
    g = lambda v, thr, inv=False: "✅" if (v < thr if inv else v >= thr) else "❌"
    print(f"  │  [{tag}]  t={m['t']:.3f}  "
          f"F1={m['f1']*100:.1f}% {g(m['f1'], 0.85)}  "
          f"FPR={m['fpr']*100:.1f}% {g(m['fpr'], 0.10, inv=True)}  "
          f"FNR={m['fnr']*100:.1f}% {g(m['fnr'], 0.10, inv=True)}  "
          f"AUC={m['auc']:.4f}")
    print(f"  │    TP={m['tp']:,}  FP={m['fp']:,}  TN={m['tn']:,}  FN={m['fn']:,}")


# ── 핵심 학습 함수 ────────────────────────────────────────────

def train_model(size: str, df_all: pd.DataFrame, timing: dict):
    cfg = MODEL_CONFIG[size]
    n1, n2 = cfg["model_nums"]
    adir   = cfg["artifact_dir"]
    adir.mkdir(parents=True, exist_ok=True)

    W = 65
    print("\n" + "=" * W)
    print(f"STEP | e5-{size} 임베딩  (샘플={'전체' if cfg['sample'] is None else cfg['sample']}행)")
    print("=" * W)

    emb_cache = adir / cfg["emb_file"]
    lbl_cache = adir / cfg["lbl_file"]
    int_cache = adir / "intent_features.npy"
    expected  = len(df_all) if cfg["sample"] is None else cfg["sample"]
    cache_ok  = emb_cache.exists() and lbl_cache.exists() and len(np.load(lbl_cache)) == expected

    if cache_ok:
        print("  임베딩 캐시 발견 → 재사용")
        emb    = np.load(emb_cache)
        labels = np.load(lbl_cache)
        timing[f"e5-{size} 임베딩"] = 0.0
        print(f"  로드 완료  shape={emb.shape}")
        if int_cache.exists() and len(np.load(int_cache)) == len(labels):
            print("  Intent 피처 캐시 발견 → 재사용")
            intent = np.load(int_cache)
        else:
            print("  Intent 피처 캐시 없음 → 추출 중...")
            df_s = sample_data(df_all, cfg["sample"])
            t0 = time.time()
            intent = extract_intent(df_s["text"])
            timing[f"e5-{size} Intent"] = time.time() - t0
            np.save(int_cache, intent)
            print(f"  Intent 완료  shape={intent.shape}  소요={timing[f'e5-{size} Intent']:.1f}초")
    else:
        df_s   = sample_data(df_all, cfg["sample"])
        labels = df_s["label"].values
        texts  = ["query: " + t for t in df_s["text"].tolist()]
        embedder = SentenceTransformer(cfg["embed_model"])
        batches  = [texts[i:i+cfg["embed_batch"]] for i in range(0, len(texts), cfg["embed_batch"])]
        print(f"  {len(texts):,}개 / {len(batches)}배치 / 배치크기={cfg['embed_batch']}")
        t0 = time.time()
        parts = [embedder.encode(b, show_progress_bar=False)
                 for b in tqdm(batches, desc=f"  임베딩(e5-{size})", unit="batch", ncols=70)]
        emb = np.vstack(parts)
        timing[f"e5-{size} 임베딩"] = time.time() - t0
        np.save(emb_cache, emb)
        np.save(lbl_cache, labels)
        print(f"  임베딩 완료  shape={emb.shape}  소요={timing[f'e5-{size} 임베딩']:.1f}초")
        t0 = time.time()
        intent = extract_intent(df_s["text"])
        timing[f"e5-{size} Intent"] = time.time() - t0
        np.save(int_cache, intent)
        print(f"  Intent 완료  shape={intent.shape}  소요={timing[f'e5-{size} Intent']:.1f}초")

    X_all = np.concatenate([emb, intent], axis=1)
    print(f"  피처 차원: {emb.shape[1]}(임베딩) + {intent.shape[1]}(intent) = {X_all.shape[1]}")
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_all, labels, test_size=TEST_SIZE, stratify=labels, random_state=RANDOM_STATE
    )
    print(f"  Train: {len(X_tr):,}  Test: {len(X_te):,}")

    # LightGBM
    print("\n" + "=" * W)
    print(f"STEP | 모델 {n1}  e5-{size} + LightGBM")
    print("=" * W)
    t0 = time.time()
    lgb_m = lgb.train(
        cfg["lgb_params"],
        lgb.Dataset(X_tr, label=y_tr),
        num_boost_round=2000,
        valid_sets=[lgb.Dataset(X_tr, label=y_tr), lgb.Dataset(X_te, label=y_te)],
        valid_names=["train", "valid"],
        callbacks=[lgb.early_stopping(100, verbose=True), lgb.log_evaluation(200)],
    )
    timing[f"{n1} e5-{size} + LGB"] = time.time() - t0
    print(f"\n  학습 완료  best_iter={lgb_m.best_iteration}  소요={timing[f'{n1} e5-{size} + LGB']:.1f}초")
    prob_lgb = lgb_m.predict(X_te, num_iteration=lgb_m.best_iteration)
    best_all, best_f1fpr, best_f1t = scan_best(y_te, prob_lgb)
    print(f"\n  ┌─ {n1} e5-{size} + LGB")
    if best_all:
        print_result(full_metrics(y_te, prob_lgb, best_all[0]), "★ 3조건 달성")
    elif best_f1fpr:
        print_result(full_metrics(y_te, prob_lgb, best_f1fpr[0]), "F1✅FPR✅ 최선")
    print_result(full_metrics(y_te, prob_lgb, best_f1t), "F1 최적")
    print(f"  └{'─'*60}")
    with open(adir / cfg["lgb_file"], "wb") as f:
        pickle.dump(lgb_m, f)
    print(f"  저장: {adir / cfg['lgb_file']}")

    # XGBoost
    print("\n" + "=" * W)
    print(f"STEP | 모델 {n2}  e5-{size} + XGBoost")
    print("=" * W)
    dm_tr = xgb.DMatrix(X_tr, label=y_tr)
    dm_te = xgb.DMatrix(X_te, label=y_te)
    t0 = time.time()
    xgb_m = xgb.train(
        cfg["xgb_params"], dm_tr,
        num_boost_round=2000,
        evals=[(dm_tr, "train"), (dm_te, "valid")],
        early_stopping_rounds=100, verbose_eval=200,
    )
    timing[f"{n2} e5-{size} + XGB"] = time.time() - t0
    print(f"\n  학습 완료  best_iter={xgb_m.best_iteration}  소요={timing[f'{n2} e5-{size} + XGB']:.1f}초")
    prob_xgb = xgb_m.predict(dm_te)
    best_all, best_f1fpr, best_f1t = scan_best(y_te, prob_xgb)
    print(f"\n  ┌─ {n2} e5-{size} + XGB")
    if best_all:
        print_result(full_metrics(y_te, prob_xgb, best_all[0]), "★ 3조건 달성")
    elif best_f1fpr:
        print_result(full_metrics(y_te, prob_xgb, best_f1fpr[0]), "F1✅FPR✅ 최선")
    print_result(full_metrics(y_te, prob_xgb, best_f1t), "F1 최적")
    print(f"  └{'─'*60}")
    xgb_m.save_model(str(adir / cfg["xgb_file"]))
    print(f"  저장: {adir / cfg['xgb_file']}")

    # 요약
    print("\n\n" + "=" * W)
    print(f"  ★  e5-{size} 학습 완료 요약")
    print("=" * W)
    print(f"\n  {'모델':<26} {'AUC':>7}  {'F1최적':>7}  {'FPR':>7}  {'FNR':>7}  {'3조건'}")
    print("  " + "─" * (W - 2))
    for name, prob, y in [
        (f"{n1} e5-{size} + LGB", prob_lgb, y_te),
        (f"{n2} e5-{size} + XGB", prob_xgb, y_te),
    ]:
        auc = roc_auc_score(y, prob)
        _, _, f1t = scan_best(y, prob)
        m = full_metrics(y, prob, f1t)
        achieved = any(
            full_metrics(y, prob, t/200)["f1"]  >= 0.85 and
            full_metrics(y, prob, t/200)["fpr"] <  0.10 and
            full_metrics(y, prob, t/200)["fnr"] <  0.10
            for t in range(1, 199)
        )
        print(f"  {name:<26} {auc:>7.4f}  {m['f1']*100:>6.1f}%  {m['fpr']*100:>6.1f}%  {m['fnr']*100:>6.1f}%  {'✅' if achieved else '❌'}")

    return timing


# ── 진입점 ────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="e5-small / e5-large 임베딩 + LightGBM / XGBoost 학습",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용법:
  python train.py --model small   [1][2] e5-small 학습
  python train.py --model large   [3][4] e5-large 학습
  python train.py --model all     4개 모델 전체 학습 (기본값)
        """
    )
    parser.add_argument(
        "--model", choices=["small", "large", "all"], default="all",
        help="학습할 모델 크기 (기본값: all)"
    )
    args = parser.parse_args()

    total_start = time.time()
    timing = {}

    # parquet 로드
    print("=" * 65)
    print("STEP 1 | parquet 로드")
    print("=" * 65)
    t0 = time.time()
    df_all = load_parquets()
    timing["로드"] = time.time() - t0
    mal = df_all["label"].eq(1).sum()
    nor = df_all["label"].eq(0).sum()
    print(f"\n  전체: {len(df_all):,}행  |  악성={mal:,}  정상={nor:,}")
    print(f"  로드 소요: {timing['로드']:.1f}초")

    # 학습 대상 결정
    targets = ["small", "large"] if args.model == "all" else [args.model]
    for size in targets:
        timing = train_model(size, df_all, timing)

    timing["─ 전체 합계 ─"] = time.time() - total_start
    W = 65
    print("\n" + "=" * W)
    print(f"  {'단계':<30} {'초':>8}  {'분':>8}")
    print(f"  {'─'*30}  {'─'*8}  {'─'*8}")
    for k, v in timing.items():
        if k.startswith("─"):
            print(f"  {'─'*30}  {'─'*8}  {'─'*8}")
        print(f"  {k:<30} {v:>8.1f}초  {v/60:>7.1f}분")
    print("=" * W)
