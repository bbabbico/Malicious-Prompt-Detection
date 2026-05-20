# from datasets import load_dataset
#
# ds = load_dataset("Necent/llm-jailbreak-prompt-injection-dataset")
# import os
# import pandas as pd
# from datasets import load_dataset
#
# # 1. 윈도우 환경에서 뜰 수 있는 HuggingFace Symlink 경고창 원천 차단
# os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
#
# print("🚀 NVIDIA Aegis 2.0 데이터셋 다운로드를 시작합니다...")
#
# try:
#     # 2. 데이터셋 로드 (인증/로그인 필요 없음)
#     # Aegis 데이터셋은 대화(default) 구성으로 되어 있습니다.
#     ds = load_dataset("nvidia/Aegis-AI-Content-Safety-Dataset-2.0", split="train")
#
#     # 3. 데이터 조작 및 분석이 편하도록 Pandas DataFrame으로 변환
#     df = pd.DataFrame(ds)
#
#     # 4. 저장할 폴더 생성 (프로젝트 폴더 내 data/ 디렉토리)
#     output_dir = "./data"
#     os.makedirs(output_dir, exist_ok=True)
#
#     # 5. CSV 파일로 최종 저장 (인코딩은 한글 및 특수문자 깨짐 방지를 위해 utf-8-sig 사용)
#     output_path = os.path.join(output_dir, "nvidia_aegis_2.0.csv")
#     df.to_csv(output_path, index=False, encoding="utf-8-sig")
#
#     print("\n🎉 파일 다운로드 및 저장 성공!")
#     print(f"   - 저장 경로: {os.path.abspath(output_path)}")
#     print(f"   - 데이터 개수: {len(df)}개")
#     print(f"   - 포함된 컬럼: {df.columns.tolist()}")
#
#     # 데이터 구조 살짝 엿보기
#     print("\n🔍 데이터 샘플 (상위 2개):")
#     print(df.head(2))
#
# except Exception as e:
#     print(f"\n❌ 에러가 발생했습니다: {e}")
