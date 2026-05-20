import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.cluster import HDBSCAN
from sklearn.metrics import silhouette_score
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.preprocessing import normalize
import warnings

# 한글 폰트 설정 (Windows 기준, 필요시 조정)
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False
except:
    pass

warnings.filterwarnings('ignore')

# 1. 경로 설정
BASE_DIR = Path(__file__).parent.parent
DATA_PATH = BASE_DIR / "scripts" / "data" / "nvidia_aegis_2.0.csv"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
SAVE_DIR = BASE_DIR / "analysis_results" / "DBSCAN"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

def perform_eda(df):
    print("--- Performing EDA on Malicious Prompts ---")
    
    # 카테고리 분포 시각화
    plt.figure(figsize=(12, 8))
    top_categories = df['violated_categories'].value_counts().head(15)
    sns.barplot(x=top_categories.values, y=top_categories.index, palette='magma')
    plt.title('Top 15 카테고리 분포 (HDBSCAN 대상)')
    plt.xlabel('Count')
    plt.ylabel('Category')
    plt.tight_layout()
    plt.savefig(SAVE_DIR / "hdbscan_category_distribution.png")
    print(f"Category distribution plot saved to {SAVE_DIR / 'hdbscan_category_distribution.png'}")

    # 프롬프트 길이 분포
    df['prompt_length'] = df['prompt'].str.len()
    plt.figure(figsize=(10, 6))
    sns.histplot(df['prompt_length'], bins=50, kde=True, color='teal')
    plt.title('프롬프트 길이 분포')
    plt.xlabel('Length (characters)')
    plt.ylabel('Frequency')
    plt.savefig(SAVE_DIR / "hdbscan_prompt_length_distribution.png")
    print(f"Prompt length distribution plot saved to {SAVE_DIR / 'hdbscan_prompt_length_distribution.png'}")

def main():
    # 2. 데이터 로드 및 필터링
    print(f"Loading data from {DATA_PATH}...")
    if not DATA_PATH.exists():
        print(f"Error: Data file not found at {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH)

    # 'unsafe' (악성) 프롬프트만 추출
    malicious_df = df[df['prompt_label'] == 'unsafe'].copy()
    print(f"Total malicious prompts found: {len(malicious_df)}")

    # 결측치 제거
    malicious_df = malicious_df.dropna(subset=['prompt'])
    
    # EDA 수행
    perform_eda(malicious_df)

    prompts = malicious_df['prompt'].tolist()

    # 3. 임베딩 생성 (e5-small 모델 사용)
    MODEL_NAME = "intfloat/multilingual-e5-small"
    print(f"\nLoading embedding model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)

    # e5 모델은 'query: ' 접두사가 권장됨
    print("Formatting prompts for E5 model...")
    formatted_prompts = [f"query: {str(p)}" for p in prompts]

    print(f"Generating embeddings for {len(prompts)} prompts (this may take a few minutes)...")
    embeddings = model.encode(formatted_prompts, batch_size=64, show_progress_bar=True)
    embeddings = np.array(embeddings)
    print(f"Embedding shape: {embeddings.shape}")

    # ============================================================
    # 핵심 변경: 고차원 임베딩에서 직접 HDBSCAN 하지 않고,
    # PCA → UMAP 으로 저차원 축소 후 HDBSCAN 수행
    # (차원의 저주 문제 해결)
    # ============================================================

    # 4-1. PCA로 1차 차원 축소 (384 → 50)
    print("\n[Step 1] PCA dimensionality reduction (384 → 50)...")
    pca = PCA(n_components=min(50, embeddings.shape[1]), random_state=42)
    embeddings_pca = pca.fit_transform(embeddings)
    explained_var = np.sum(pca.explained_variance_ratio_) * 100
    print(f"PCA explained variance: {explained_var:.1f}%")

    # 4-2. UMAP으로 2차 차원 축소 (50 → 15~20) - 밀도 구조 보존
    try:
        import umap
        UMAP_AVAILABLE = True
    except ImportError:
        print("\n[WARNING] UMAP not installed. Falling back to PCA-only approach.")
        print("For better results, install UMAP: pip install umap-learn")
        UMAP_AVAILABLE = False

    if UMAP_AVAILABLE:
        UMAP_DIM = 10
        print(f"[Step 2] UMAP dimensionality reduction (50 → {UMAP_DIM})...")
        reducer = umap.UMAP(
            n_components=UMAP_DIM,
            n_neighbors=15,       # 지역 구조를 더 세밀하게 캡처 (작을수록 세밀)
            min_dist=0.0,         # 클러스터링용이므로 0으로 설정 (밀집 허용)
            metric='cosine',      # 텍스트 임베딩에 적합한 코사인 거리
            random_state=42
        )
        embeddings_reduced = reducer.fit_transform(embeddings_pca)
        print(f"UMAP reduced shape: {embeddings_reduced.shape}")
    else:
        # UMAP 없으면 PCA 결과 사용 (차원을 더 줄임)
        pca_fallback = PCA(n_components=20, random_state=42)
        embeddings_reduced = pca_fallback.fit_transform(embeddings_pca)
        print(f"PCA fallback reduced shape: {embeddings_reduced.shape}")

    # L2 정규화 (코사인 유사도 기반 클러스터링 효과)
    embeddings_reduced = normalize(embeddings_reduced, norm='l2')

    # 5. HDBSCAN 클러스터링 수행 (저차원 데이터에서)
    print("\n[Step 3] Performing HDBSCAN clustering on reduced embeddings...")
    # min_cluster_size: 작을수록 세밀한 클러스터 분리 (너무 작으면 과분리)
    # min_samples: 낮을수록 더 많은 포인트가 클러스터에 포함됨
    # cluster_selection_method='leaf': 계층 트리의 리프 노드를 선택 → 세밀한 클러스터
    MIN_CLUSTER_SIZE = 200
    MIN_SAMPLES = 10
    
    print(f"Parameters: min_cluster_size={MIN_CLUSTER_SIZE}, min_samples={MIN_SAMPLES}, method=leaf")
    
    clusterer = HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        cluster_selection_method='leaf',  # leaf: 가장 세밀한 클러스터 선택 (eom은 과도한 병합 경향)
    )
    cluster_labels = clusterer.fit_predict(embeddings_reduced)
    
    malicious_df['cluster'] = cluster_labels
    
    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    n_noise = list(cluster_labels).count(-1)
    
    print(f"\nEstimated number of clusters: {n_clusters}")
    print(f"Estimated number of noise points: {n_noise} ({100 * n_noise / len(embeddings):.1f}%)")

    # 6. 새로운 데이터 매핑을 위한 모델 준비 (KNN 활용)
    # HDBSCAN은 predict()가 없으므로, 학습된 클러스터 레이블을 바탕으로 KNN을 학습시켜 새로운 데이터를 매핑할 수 있게 합니다.
    from sklearn.neighbors import KNeighborsClassifier
    print("\nTraining KNN classifier for new data mapping...")
    # 노이즈(-1)도 하나의 클래스로 학습하거나, 필요에 따라 제외할 수 있습니다. 여기서는 포함합니다.
    knn_mapper = KNeighborsClassifier(n_neighbors=5)
    knn_mapper.fit(embeddings_reduced, cluster_labels)

    # 7. 종합 성능 평가 지표 계산
    from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score
    
    print("\n" + "="*50)
    print("         CLUSTERING EVALUATION METRICS")
    print("="*50)
    
    metrics_lines = []
    metrics_lines.append("="*50)
    metrics_lines.append("   HDBSCAN CLUSTERING EVALUATION METRICS")
    metrics_lines.append("="*50)
    metrics_lines.append(f"\nParameters:")
    metrics_lines.append(f"  - min_cluster_size: {MIN_CLUSTER_SIZE}")
    metrics_lines.append(f"  - min_samples: {MIN_SAMPLES}")
    metrics_lines.append(f"  - cluster_selection_method: leaf")
    metrics_lines.append(f"  - UMAP n_components: {UMAP_DIM if UMAP_AVAILABLE else 'N/A (PCA fallback)'}")
    metrics_lines.append(f"\nBasic Statistics:")
    metrics_lines.append(f"  - Total data points: {len(cluster_labels)}")
    metrics_lines.append(f"  - Number of clusters: {n_clusters}")
    metrics_lines.append(f"  - Noise points: {n_noise} ({100 * n_noise / len(cluster_labels):.1f}%)")
    metrics_lines.append(f"  - Clustered points: {len(cluster_labels) - n_noise} ({100 * (len(cluster_labels) - n_noise) / len(cluster_labels):.1f}%)")
    
    # 클러스터 크기 통계
    cluster_sizes = [np.sum(cluster_labels == c) for c in range(n_clusters)]
    if cluster_sizes:
        metrics_lines.append(f"\nCluster Size Statistics:")
        metrics_lines.append(f"  - Mean cluster size: {np.mean(cluster_sizes):.1f}")
        metrics_lines.append(f"  - Median cluster size: {np.median(cluster_sizes):.1f}")
        metrics_lines.append(f"  - Min cluster size: {np.min(cluster_sizes)}")
        metrics_lines.append(f"  - Max cluster size: {np.max(cluster_sizes)}")
        metrics_lines.append(f"  - Std cluster size: {np.std(cluster_sizes):.1f}")
    
    metrics_lines.append(f"\nEvaluation Metrics (noise excluded):")
    
    if n_clusters > 1:
        mask = cluster_labels != -1
        if np.any(mask):
            X_clustered = embeddings_reduced[mask]
            labels_clustered = cluster_labels[mask]
            
            # 1) Silhouette Score: [-1, 1], 높을수록 좋음. 클러스터 내 응집도와 클러스터 간 분리도 측정
            sil_score = silhouette_score(X_clustered, labels_clustered)
            metrics_lines.append(f"  - Silhouette Score: {sil_score:.4f}  (range: [-1, 1], higher = better)")
            print(f"  Silhouette Score: {sil_score:.4f}")
            
            # 2) Calinski-Harabasz Index: 높을수록 좋음. 클러스터 간 분산 / 클러스터 내 분산 비율
            ch_score = calinski_harabasz_score(X_clustered, labels_clustered)
            metrics_lines.append(f"  - Calinski-Harabasz Index: {ch_score:.2f}  (higher = better)")
            print(f"  Calinski-Harabasz Index: {ch_score:.2f}")
            
            # 3) Davies-Bouldin Index: 낮을수록 좋음. 클러스터 간 유사도의 평균
            db_score = davies_bouldin_score(X_clustered, labels_clustered)
            metrics_lines.append(f"  - Davies-Bouldin Index: {db_score:.4f}  (lower = better)")
            print(f"  Davies-Bouldin Index: {db_score:.4f}")
            
            # 4) 클러스터별 실루엣 점수
            from sklearn.metrics import silhouette_samples
            sample_silhouette_values = silhouette_samples(X_clustered, labels_clustered)
            
            metrics_lines.append(f"\nPer-Cluster Silhouette Scores:")
            per_cluster_sil = []
            for i in range(n_clusters):
                cluster_sil = sample_silhouette_values[labels_clustered == i]
                avg_sil = np.mean(cluster_sil)
                per_cluster_sil.append(avg_sil)
                cluster_size = np.sum(labels_clustered == i)
                metrics_lines.append(f"  Cluster {i:3d}: silhouette={avg_sil:.4f}, size={cluster_size}")
            
            metrics_lines.append(f"\n  Mean per-cluster silhouette: {np.mean(per_cluster_sil):.4f}")
            metrics_lines.append(f"  Std  per-cluster silhouette: {np.std(per_cluster_sil):.4f}")
    else:
        metrics_lines.append("  - Cannot compute metrics: need at least 2 clusters")
        print("  Cannot compute metrics: need at least 2 clusters")
    
    # 평가 결과 파일 저장
    metrics_text = "\n".join(metrics_lines)
    print(metrics_text)
    
    metrics_file = SAVE_DIR / "evaluation_metrics.txt"
    with open(metrics_file, 'w', encoding='utf-8') as f:
        f.write(metrics_text)
    print(f"\nEvaluation metrics saved to {metrics_file}")

    # 8. 시각화 (t-SNE on reduced embeddings)
    print("\nPreparing 2D visualization with t-SNE...")
    viz_sample_size = min(5000, len(embeddings_reduced))
    np.random.seed(42)
    viz_indices = np.random.choice(len(embeddings_reduced), viz_sample_size, replace=False)
    
    tsne = TSNE(
        n_components=2,
        random_state=42,
        perplexity=min(30, viz_sample_size - 1),
        init='pca',
        learning_rate='auto'
    )
    embeddings_tsne = tsne.fit_transform(embeddings_reduced[viz_indices])

    # 시각화 데이터프레임
    viz_df = pd.DataFrame(embeddings_tsne, columns=['tsne_1', 'tsne_2'])
    viz_df['cluster'] = malicious_df.iloc[viz_indices]['cluster'].values
    # 노이즈(-1)는 'Noise'로 표시
    viz_df['cluster_label'] = viz_df['cluster'].apply(lambda x: f'Cluster {x}' if x != -1 else 'Noise')

    plt.figure(figsize=(14, 10))
    
    # 노이즈는 회색으로, 클러스터는 색상으로 구분
    noise_mask = viz_df['cluster'] == -1
    cluster_mask = ~noise_mask
    
    # 노이즈 포인트 먼저 그리기 (배경)
    if noise_mask.any():
        plt.scatter(
            viz_df.loc[noise_mask, 'tsne_1'],
            viz_df.loc[noise_mask, 'tsne_2'],
            c='lightgray', alpha=0.3, s=15, label='Noise', zorder=1
        )
    
    # 클러스터 포인트 그리기 (전경)
    unique_clusters = sorted(viz_df.loc[cluster_mask, 'cluster'].unique())
    colors = plt.cm.tab20(np.linspace(0, 1, max(len(unique_clusters), 1)))
    
    for i, cluster_id in enumerate(unique_clusters):
        c_mask = viz_df['cluster'] == cluster_id
        plt.scatter(
            viz_df.loc[c_mask, 'tsne_1'],
            viz_df.loc[c_mask, 'tsne_2'],
            c=[colors[i % 20]], alpha=0.7, s=40,
            label=f'Cluster {cluster_id}', edgecolors='w', linewidth=0.3, zorder=2
        )
    
    plt.title(f'Visualizing Malicious Prompt Clusters (HDBSCAN, clusters={n_clusters}, noise={n_noise})')
    plt.legend(title='Cluster', bbox_to_anchor=(1.05, 1), loc='upper left', markerscale=1.5)
    plt.xlabel('t-SNE 1')
    plt.ylabel('t-SNE 2')
    plt.tight_layout()
    plt.savefig(SAVE_DIR / "hdbscan_tsne_clusters_visualization.png", dpi=150, bbox_inches='tight')
    print(f"t-SNE cluster visualization saved to {SAVE_DIR / 'hdbscan_tsne_clusters_visualization.png'}")

    # 9. 클러스터별 요약 분석
    print("\n" + "="*50)
    print("            HDBSCAN CLUSTER CHARACTERISTICS SUMMARY")
    print("="*50)
    
    unique_labels = sorted(set(cluster_labels))
    
    for i in unique_labels:
        cluster_data = malicious_df[malicious_df['cluster'] == i]
        size = len(cluster_data)
        percentage = (size / len(malicious_df)) * 100
        
        label_text = f"Cluster {i}" if i != -1 else "Noise (-1)"
        print(f"\n[{label_text}] - {size} prompts ({percentage:.1f}%)")
        
        # 상위 카테고리
        top_cats = cluster_data['violated_categories'].value_counts().head(3)
        cat_str = ", ".join([f"{c} ({v})" for c, v in top_cats.items()])
        print(f"Main Categories: {cat_str}")
        
        # 랜덤 예시 3개
        samples = cluster_data['prompt'].sample(min(3, len(cluster_data)), random_state=42).tolist()
        print("Example Prompts:")
        for s in samples:
            clean_s = str(s).replace('\n', ' ')[:120] + "..."
            print(f"  - {clean_s}")

    # 10. 결과 저장
    output_csv = SAVE_DIR / "hdbscan_clustered_malicious_results.csv"
    malicious_df.to_csv(output_csv, index=False)
    print(f"\nFinal clustered data saved to {output_csv}")
    
    # 11. 새로운 프롬프트 실시간 분류 및 이상치 탐지를 위한 핵심 아티팩트 저장
    import joblib
    
    # (1) 클러스터별 대표 카테고리 매핑 딕셔너리 구축
    cluster_to_category = {}
    cluster_to_category[-1] = "Noise / New Type Anomaly"
    
    for c in unique_clusters:
        cluster_data = malicious_df[malicious_df['cluster'] == c]
        if len(cluster_data) > 0:
            # 결측치를 제거하고 가장 빈번하게 발생하는 카테고리를 대표 카테고리로 지정
            cats = cluster_data['violated_categories'].dropna()
            if not cats.empty:
                top_cat = cats.value_counts().index[0]
            else:
                top_cat = "Unknown Malicious Type"
            cluster_to_category[int(c)] = str(top_cat)
    
    # (2) KNN 최근접 거리 분포 기반으로 이상치(Anomaly) 탐지용 임계값 계산
    # 각 학습 데이터 임베딩에 대하여 KNN 5개 이웃의 거리를 구함
    distances, _ = knn_mapper.kneighbors(embeddings_reduced)
    # 각 포인트별로 5개 이웃 거리의 평균값 계산
    mean_distances = distances.mean(axis=1)
    # 상위 95% 거리 기준값을 이상치 탐지 임계값(Threshold)으로 설정
    anomaly_threshold = float(np.percentile(mean_distances, 95))
    
    print(f"\n--- Saving Serving Artifacts ---")
    print(f"Calculated Anomaly Distance Threshold (95th percentile): {anomaly_threshold:.4f}")
    
    # 저장 폴더 구성
    SERVED_MODEL_DIR = ARTIFACTS_DIR / "small"
    SERVED_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    # 객체 파일들 저장
    joblib.dump(pca, SERVED_MODEL_DIR / "cluster_pca.pkl")
    if UMAP_AVAILABLE:
        joblib.dump(reducer, SERVED_MODEL_DIR / "cluster_umap.pkl")
    joblib.dump(knn_mapper, SERVED_MODEL_DIR / "cluster_knn.pkl")
    joblib.dump(cluster_to_category, SERVED_MODEL_DIR / "cluster_to_category.pkl")
    np.save(SERVED_MODEL_DIR / "anomaly_threshold.npy", np.array([anomaly_threshold]))
    
    print(f"Successfully saved all serving artifacts (PCA, UMAP, KNN, Category Map, Threshold) to: {SERVED_MODEL_DIR}")
    print(f"All analysis artifacts are available in: {SAVE_DIR}")

if __name__ == "__main__":
    main()
