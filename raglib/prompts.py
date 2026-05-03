from raglib.config import PROMPTS
from raglib.io_utils import read_text


def load_prompt(name: str) -> str:
    """
    Loads prompt file from /prompts.

    Example:
      load_prompt("extract_events")
      -> /Volumes/T7_WORK/AI_RAG/prompts/extract_events.txt
    """
    path = PROMPTS / f"{name}.txt"
    return read_text(path)


def build_prompt(*parts: str) -> str:
    """
    Combines prompt sections cleanly.
    """
    return "\n\n".join(part.strip() for part in parts if part and part.strip())
