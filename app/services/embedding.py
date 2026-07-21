"""Embedding Service — generates vector embeddings using sentence-transformers.

Model: BAAI/bge-base-en-v1.5 (768 dimensions)
Upgraded from all-MiniLM-L6-v2 (384 dim) for significantly better
retrieval accuracy on job matching tasks.

Key improvements over the baseline:
    1. BGE model — built for retrieval, not just similarity
    2. Query prefix — BGE expects "Represent this sentence: " for queries
    3. Boilerplate stripping — removes legal/benefits noise from descriptions
    4. Title weighting — repeats the title so it dominates the embedding
"""

import re
import logging
from functools import lru_cache
from sentence_transformers import SentenceTransformer
from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the model once and cache it in memory."""
    settings = get_settings()
    logger.info(f"Loading embedding model: {settings.embedding_model}")
    model = SentenceTransformer(settings.embedding_model)
    logger.info("Embedding model loaded")
    return model


# ── Boilerplate patterns to strip from job descriptions ──
BOILERPLATE_PATTERNS = [
    # Equal opportunity / diversity statements
    r"(?i)equal\s+opportunity\s+employer.*",
    r"(?i)we\s+are\s+(an?\s+)?equal\s+opportunity.*",
    r"(?i)(?:we|the company)\s+(?:is|are)\s+committed\s+to\s+(?:diversity|equal).*",
    r"(?i)without\s+regard\s+to\s+race,?\s+color.*",
    r"(?i)all\s+qualified\s+applicants?\s+will\s+receive\s+consideration.*",
    # Benefits boilerplate
    r"(?i)(?:we|our company)\s+offer(?:s)?\s+(?:a\s+)?competitive\s+(?:salary|benefits|compensation).*",
    r"(?i)benefits?\s+(?:include|package).*?(?:dental|vision|401k|retirement|insurance).*",
    # Application instructions
    r"(?i)(?:how\s+to\s+)?apply\s+(?:now|today|here).*",
    r"(?i)please\s+(?:send|submit|forward)\s+your\s+(?:resume|cv).*",
    r"(?i)click\s+(?:here|apply)\s+to.*",
    # Legal / disclaimer
    r"(?i)this\s+(?:job|position)\s+(?:description|posting)\s+(?:is\s+not|does\s+not).*",
    r"(?i)disclaimer.*",
]

COMPILED_BOILERPLATE = [re.compile(p, re.MULTILINE | re.DOTALL) for p in BOILERPLATE_PATTERNS]


def _strip_boilerplate(text: str) -> str:
    """Remove common noise sections from job descriptions.

    These sections dilute the embedding — they contain no signal about
    what the job actually requires.
    """
    for pattern in COMPILED_BOILERPLATE:
        text = pattern.sub("", text)

    # Also strip the last 25% of very long descriptions — usually
    # benefits, disclaimers, and application instructions live at the end
    lines = text.strip().split("\n")
    if len(lines) > 20:
        cutoff = int(len(lines) * 0.75)
        text = "\n".join(lines[:cutoff])

    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def generate_embedding(text: str, is_query: bool = False) -> list[float]:
    """Generate a single embedding vector from text.

    Args:
        text: Any text — job description, user profile summary, search query.
        is_query: If True, adds the BGE query prefix for better retrieval.
                  Set True for: search queries, user profiles.
                  Set False for: job descriptions (they are the "documents").

    Returns:
        List of floats (768 dimensions with BGE).
    """
    if not text or not text.strip():
        return [0.0] * get_settings().embedding_dim

    # BGE models are trained with a specific prefix for queries
    # This significantly improves retrieval accuracy
    if is_query:
        text = "Represent this sentence: " + text

    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def generate_embeddings_batch(
    texts: list[str],
    batch_size: int = 32,
    is_query: bool = False,
) -> list[list[float]]:
    """Generate embeddings for multiple texts efficiently.

    Args:
        texts: List of texts to embed.
        batch_size: Batch size for encoding.
        is_query: If True, adds BGE query prefix to all texts.

    Returns:
        List of embedding vectors.
    """
    model = _get_model()

    clean_texts = []
    for t in texts:
        if not t or not t.strip():
            t = "empty"
        if is_query:
            t = "Represent this sentence: " + t
        clean_texts.append(t)

    embeddings = model.encode(
        clean_texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return embeddings.tolist()


def build_job_text(title: str, description: str, skills: list[str] | None = None) -> str:
    """Combine job fields into a single string for embedding.

    Key improvements over the baseline:
        1. Title repeated — ensures it dominates the embedding signal
        2. Skills listed explicitly — structured, unambiguous signal
        3. Description stripped of boilerplate — less noise
        4. Truncated to 1500 chars — longer text dilutes, shorter stays focused
    """
    parts = []

    # Repeat the title for emphasis — this is the strongest signal
    clean_title = title.strip() if title else ""
    if clean_title:
        parts.append(clean_title)
        parts.append(clean_title)  # Deliberate repetition

    # Skills as a clean, explicit list
    if skills:
        parts.append("Required skills: " + ", ".join(skills))

    # Description with boilerplate removed
    if description:
        cleaned = _strip_boilerplate(description)
        # Take only the first 1500 chars — the important stuff is at the top
        parts.append(cleaned[:1500])

    return " | ".join(parts)


def build_profile_text(
    headline: str | None,
    skills: list[str] | None,
    career_interests: str | None,
    experience_level: str | None,
) -> str:
    """Combine user profile fields into a single string for embedding.

    This turns the user into a 'query document' that can be compared
    against job embeddings via cosine similarity.

    Note: profile embeddings use is_query=True when calling generate_embedding,
    since the user profile acts as the "query" searching for matching "document" jobs.
    """
    parts = []

    # Headline is the strongest signal — repeat it
    if headline:
        parts.append(headline)
        parts.append(headline)

    if experience_level:
        parts.append(f"Experience level: {experience_level}")

    if skills:
        parts.append("Skills: " + ", ".join(skills))

    if career_interests:
        parts.append(career_interests)

    return " | ".join(parts) if parts else "general job seeker"
