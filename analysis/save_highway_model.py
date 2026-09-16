import os
import joblib

from train_highway_model import (
    build_dataset,
    create_random_forest_model,
    FEATURES,
    TARGET,
)


# ==================================================
# 경로 설정
# ==================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

MODEL_DIR = os.path.join(
    PROJECT_ROOT,
    "models"
)

MODEL_PATH = os.path.join(
    MODEL_DIR,
    "highway_speed_model.pkl"
)


# ==================================================
# 최종 모델 학습 + 저장
# ==================================================

def train_and_save_model():

    print("\n===== FINAL MODEL TRAINING =====")

    # 기존 코드에서 데이터셋 생성
    df = build_dataset()

    print(
        "Dataset:",
        len(df),
        "rows"
    )

    print(
        "Date:",
        df["date"].min().date(),
        "~",
        df["date"].max().date()
    )

    # ----------------------------------------------
    # 최종 Feature
    # ----------------------------------------------

    X = df[FEATURES]
    y = df[TARGET]

    # ----------------------------------------------
    # Random Forest Pipeline 생성
    # ----------------------------------------------

    model = create_random_forest_model()

    # ----------------------------------------------
    # 전체 데이터로 최종 학습
    # ----------------------------------------------

    model.fit(
        X,
        y
    )

    print(
        "Model training complete."
    )

    # ----------------------------------------------
    # models 폴더 생성
    # ----------------------------------------------

    os.makedirs(
        MODEL_DIR,
        exist_ok=True
    )

    # ----------------------------------------------
    # 모델 저장
    # ----------------------------------------------

    joblib.dump(
        model,
        MODEL_PATH
    )

    print(
        "\n===== MODEL SAVED ====="
    )

    print(
        MODEL_PATH
    )


# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":

    train_and_save_model()