import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _get_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY") or "sk-placeholder-for-initialization"


def get_supervisor_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL_SUPERVISOR", "gpt-4o-mini"),
        temperature=temperature,
        api_key=_get_api_key(),
    )


def get_specialist_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL_SUPERVISOR", "gpt-4o-mini"),
        temperature=temperature,
        api_key=_get_api_key(),
    )


def get_rca_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL_RCA", "gpt-4o"),
        temperature=temperature,
        api_key=_get_api_key(),
    )
