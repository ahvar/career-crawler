import os
from pathlib import Path
from dotenv import load_dotenv

basedir = Path(__file__).resolve().parent
DATA_DIR = basedir / "derived_profile"
envfile = basedir / ".env"
load_dotenv(str(envfile))


class Config:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_FINETUNED_MODEL = os.getenv("OPENAI_FINETUNED_MODEL")
    BASE_MODEL = os.getenv("BASE_MODEL", "gpt-4o-mini-2024-07-18")
    DEFAULT_JSONL_PATH = os.getenv(
        "DEFAULT_JSONL_PATH", str(basedir / "training_data" / "application_writing_training.jsonl")
    )
    USER_AGENT = os.getenv("USER_AGENT")
