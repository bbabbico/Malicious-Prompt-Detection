import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
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
SAVE_DIR = BASE_DIR / "analysis_results"
SAVE_DIR.mkdir(exist_ok=True)

def perform_eda(df):
    print("--- Performing EDA on Malicious Prompts ---")
    
    # 카테고리 분포 시각화
    plt.figure(figsize=(12, 8))
    top_categories = df['violated_categories'].value_counts().head(15)
    sns.barplot(x=top_categories.values, y=top_categories.index, palette='magma')
    plt.title('Top 15 카테고리 분포')
    plt.xlabel('Count')
    plt.ylabel('Category')
    plt.tight_layout()
    plt.savefig(SAVE_DIR / "category_distribution.png")
    print(f"Category distribution plot saved to {SAVE_DIR / 'category_distribution.png'}")

    # 프롬프트 길이 분포
    df['prompt_length'] = df['prompt'].str.len()
    plt.figure(figsize=(10, 6))
    sns.histplot(df['prompt_length'], bins=50, kde=True, color='teal')
    plt.title('프롬프트 길이 분포')
    plt.xlabel('Length (characters)')
    plt.ylabel('Frequency')
    plt.savefig(SAVE_DIR / "prompt_length_distribution.png")
    print(f"Prompt length distribution plot saved to {SAVE_DIR / 'prompt_length_distribution.png'}")

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
    # 기존 detector.py에서 사용하는 모델과 동일하게 설정
    MODEL_NAME = "intfloat/multilingual-e5-small"
    print(f"\nLoading embedding model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)

    # e5 모델은 'query: ' 접두사가 권장됨
    print("Formatting prompts for E5 model...")
    formatted_prompts = [f"query: {str(p)}" for p in prompts]

    print(f"Generating embeddings for {len(prompts)} prompts (this may take a few minutes)...")
    # 메모리 효율을 위해 배치 사이즈 조정 가능
    embeddings = model.encode(formatted_prompts, batch_size=64, show_progress_bar=True)
    embeddings = np.array(embeddings)

    # 4. 클러스터 개수 결정 (Elbow Method & Silhouette Score)
    print("\nFinding optimal number of clusters (2 to 10)...")
    k_range = range(2, 11)
    inertias = []
    silhouette_avg = []

    # 계산량 조절을 위한 샘플링 (실루엣 점수 계산용)
    sample_size = min(3000, len(embeddings))
    indices = np.random.choice(len(embeddings), sample_size, replace=False)
    sampled_embeddings = embeddings[indices]

    for k in k_range:
        print(f"Testing k={k}...", end='\r')
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        kmeans.fit(embeddings)
        inertias.append(kmeans.inertia_)
        
        score = silhouette_score(sampled_embeddings, kmeans.predict(sampled_embeddings))
        silhouette_avg.append(score)
    print("\nClustering metric calculation complete.")

    # 결과 시각화
    plt.figure(figsize=(14, 6))

    plt.subplot(1, 2, 1)
    plt.plot(k_range, inertias, 'bo-', markersize=8)
    plt.xlabel('Number of clusters (k)')
    plt.ylabel('Inertia (Sum of squared distances)')
    plt.title('악성프롬프트만 포함하여 Elbow Method for Optimal k')
    plt.grid(True)

    plt.subplot(1, 2, 2)
    plt.plot(k_range, silhouette_avg, 'ro-', markersize=8)
    plt.xlabel('Number of clusters (k)')
    plt.ylabel('Silhouette Score')
    plt.title('악성프롬프트만 포함하여 Silhouette Analysis for Optimal k')
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(SAVE_DIR / "clustering_metrics.png")
    print(f"Clustering metrics plot saved to {SAVE_DIR / 'clustering_metrics.png'}")

    # 5. 최적의 K 선택
    # Silhouette Score가 가장 높은 지점을 선택
    optimal_k = k_range[np.argmax(silhouette_avg)]
    print(f"Suggested optimal K by Silhouette Score: {optimal_k}")
    
    # 사용자 편의를 위해 만약 Elbow가 뚜렷하다면 다른 선택을 할 수도 있지만 자동화 우선
    # 여기서는 k=5 정도로 고정해서 보고 싶을 수도 있으므로, 상수로 설정하거나 유연하게 대응

    # 6. 최종 클러스터링 수행
    print(f"Performing final K-Means clustering with k={optimal_k}...")
    final_kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
    malicious_df['cluster'] = final_kmeans.fit_predict(embeddings)

    # 7. 시각화 (t-SNE)
    print("Preparing 2D visualization with t-SNE...")
    # PCA로 차원 축소 후 t-SNE 적용 (속도 및 품질 향상)
    pca_50 = PCA(n_components=min(50, embeddings.shape[1]), random_state=42)
    embeddings_pca = pca_50.fit_transform(embeddings)

    # t-SNE는 데이터가 많으면 오래 걸리므로 일부 샘플만 시각화하거나 속도 최적화
    # 여기서는 5000개 샘플링하여 시각화 (전체는 너무 밀집됨)
    viz_sample_size = min(5000, len(embeddings))
    viz_indices = np.random.choice(len(embeddings), viz_sample_size, replace=False)
    
    tsne = TSNE(n_components=2, random_state=42, init='pca', learning_rate='auto')
    embeddings_tsne = tsne.fit_transform(embeddings_pca[viz_indices])

    # 시각화 데이터프레임
    viz_df = pd.DataFrame(embeddings_tsne, columns=['tsne_1', 'tsne_2'])
    viz_df['cluster'] = malicious_df.iloc[viz_indices]['cluster'].values

    plt.figure(figsize=(12, 10))
    sns.scatterplot(data=viz_df, x='tsne_1', y='tsne_2', hue='cluster', 
                    palette='tab10', alpha=0.7, s=60, edgecolor='w')
    plt.title(f'Visualizing Malicious Prompt Clusters (t-SNE, k={optimal_k})')
    plt.legend(title='Cluster', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(SAVE_DIR / "tsne_clusters_visualization.png")
    print(f"t-SNE cluster visualization saved to {SAVE_DIR / 'tsne_clusters_visualization.png'}")

    # 8. 클러스터별 요약 분석
    print("\n" + "="*50)
    print("            CLUSTER CHARACTERISTICS SUMMARY")
    print("="*50)
    
    summary_report = []
    
    for i in range(optimal_k):
        cluster_data = malicious_df[malicious_df['cluster'] == i]
        size = len(cluster_data)
        percentage = (size / len(malicious_df)) * 100
        
        print(f"\n[Cluster {i}] - {size} prompts ({percentage:.1f}%)")
        
        # 상위 카테고리
        top_cats = cluster_data['violated_categories'].value_counts().head(3)
        cat_str = ", ".join([f"{c} ({v})" for c, v in top_cats.items()])
        print(f"Main Categories: {cat_str}")
        
        # 랜덤 예시 3개
        samples = cluster_data['prompt'].sample(min(3, len(cluster_data))).tolist()
        print("Example Prompts:")
        for s in samples:
            clean_s = str(s).replace('\n', ' ')[:120] + "..."
            print(f"  - {clean_s}")
            
        summary_report.append({
            'cluster': i,
            'size': size,
            'top_categories': cat_str,
            'examples': samples
        })

    # 9. 결과 저장
    output_csv = SAVE_DIR / "clustered_malicious_results.csv"
    malicious_df.to_csv(output_csv, index=False)
    print(f"\nFinal clustered data saved to {output_csv}")
    print(f"All analysis artifacts are available in: {SAVE_DIR}")

if __name__ == "__main__":
    main()
