from pathlib import Path
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]

DATA_PATH = (
    BASE_DIR
    / "data"
    / "synthetic_data"
    / "conversations.csv"
)


def load_conversations():
    return pd.read_csv(DATA_PATH)


if __name__ == "__main__":
    df = load_conversations()

    print(df.shape)

    print(df[["text","expected_memory_type","entity_value"]].head())