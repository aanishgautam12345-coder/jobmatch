"""Skill Extraction Processor.

Extracts skills from job descriptions using dictionary matching with:
- Confidence scoring (0.0-1.0)
- Essential vs desirable classification via context keywords
- Alias mapping for variant spellings
- Provenance tracking (dictionary match vs text match)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedSkill:
    """A single skill extracted from job text."""
    name: str
    confidence: float = 0.0
    classification: str = "required"  # required/preferred/desirable/mentioned
    provenance: str = "dictionary"    # dictionary/context/source
    is_essential: bool = True


# ── Alias Mapping ──
# Canonical name → set of aliases that should resolve to it
SKILL_ALIASES: dict[str, set[str]] = {
    "python": {"python3", "python 3", "py"},
    "javascript": {"js", "ecmascript", "es6", "es2015", "ecma script"},
    "typescript": {"ts"},
    "react": {"reactjs", "react.js", "react js"},
    "angular": {"angularjs", "angular.js", "angular 2+", "angular2"},
    "vue": {"vuejs", "vue.js", "vue js", "vue3", "vue 3"},
    "node.js": {"nodejs", "node", "node js"},
    "c#": {"csharp", "c sharp", ".net", "dotnet", "asp.net", "aspnet"},
    "c++": {"cpp", "c plus plus"},
    "golang": {"go"},
    "machine learning": {"ml"},
    "deep learning": {"dl"},
    "natural language processing": {"nlp"},
    "computer vision": {"cv"},
    "amazon web services": {"aws"},
    "google cloud": {"gcp", "google cloud platform"},
    "kubernetes": {"k8s"},
    "continuous integration": {"ci", "ci/cd"},
    "continuous delivery": {"cd", "ci/cd"},
    "ruby on rails": {"rails"},
    "react native": {"react-native"},
    "swiftui": {"swift ui"},
    "jetpack compose": {"compose"},
}

# Build reverse lookup: alias → canonical
_ALIAS_LOOKUP: dict[str, str] = {}
for canonical, aliases in SKILL_ALIASES.items():
    for alias in aliases:
        _ALIAS_LOOKUP[alias.lower()] = canonical.lower()
    _ALIAS_LOOKUP[canonical.lower()] = canonical.lower()


@dataclass
class SkillDictionary:
    """Skill dictionary with domain organisation."""
    domains: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self):
        self.domains = {
            "programming": {
                "python", "java", "javascript", "typescript", "c++", "c#", "ruby",
                "go", "golang", "rust", "swift", "kotlin", "scala", "php", "r",
                "perl", "matlab", "lua", "dart", "elixir", "haskell", "clojure",
                "shell", "bash", "powershell", "sql",
            },
            "web_frontend": {
                "html", "css", "react", "angular", "vue", "svelte", "next.js",
                "nuxt", "webpack", "vite", "tailwind", "bootstrap", "sass",
                "jquery", "redux", "graphql", "rest", "restful",
            },
            "web_backend": {
                "node.js", "express", "django", "flask", "fastapi", "spring",
                "spring boot", "rails", "ruby on rails", "laravel", "asp.net",
                ".net", ".net core",
            },
            "databases": {
                "sql", "mysql", "postgresql", "postgres", "mongodb", "redis",
                "elasticsearch", "cassandra", "dynamodb", "sqlite", "oracle",
                "sql server", "mariadb", "neo4j", "firebase", "supabase",
                "prisma", "sequelize", "sqlalchemy",
            },
            "cloud_devops": {
                "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
                "ansible", "jenkins", "ci/cd", "github actions", "gitlab ci",
                "nginx", "linux", "unix", "serverless", "lambda", "helm",
                "prometheus", "grafana", "datadog",
            },
            "data_ai": {
                "machine learning", "deep learning", "nlp", "natural language processing",
                "computer vision", "tensorflow", "pytorch", "keras", "scikit-learn",
                "pandas", "numpy", "scipy", "spark", "pyspark", "hadoop", "airflow",
                "dbt", "tableau", "power bi", "data visualization", "data modeling",
                "etl", "data pipeline", "data warehouse", "snowflake", "bigquery",
                "redshift", "databricks", "neural networks", "generative ai", "llm",
                "large language models", "transformers", "langchain", "vector database",
                "embeddings",
            },
            "mobile": {
                "android", "ios", "react native", "flutter", "xamarin",
                "swiftui", "jetpack compose", "mobile development",
            },
            "testing": {
                "unit testing", "integration testing", "selenium", "cypress",
                "jest", "pytest", "junit", "testng", "qa", "quality assurance",
                "test automation", "load testing", "performance testing",
            },
            "tools_practices": {
                "git", "github", "gitlab", "jira", "confluence", "agile",
                "scrum", "kanban", "microservices", "api design", "system design",
                "design patterns", "solid", "code review", "tdd", "bdd",
            },
            "soft_skills": {
                "communication", "leadership", "teamwork", "problem solving",
                "critical thinking", "time management", "stakeholder management",
                "project management", "mentoring",
            },
            "business_tools": {
                "excel", "powerpoint", "word", "google sheets", "google analytics",
                "salesforce", "hubspot", "sap", "erp", "crm",
            },
            "security": {
                "cybersecurity", "penetration testing", "encryption", "oauth",
                "sso", "siem", "firewall", "gdpr", "hipaa", "soc2", "iso 27001",
            },
        }

    def all_skills(self) -> set[str]:
        """Return all skills across all domains."""
        result: set[str] = set()
        for skills in self.domains.values():
            result.update(skills)
        return result


SKILL_DICT = SkillDictionary()
ALL_SKILLS = SKILL_DICT.all_skills()

# Multi-word skills sorted longest first for greedy matching
MULTI_WORD_SKILLS = sorted(
    [s for s in ALL_SKILLS if " " in s or "." in s],
    key=len, reverse=True,
)

# Context keywords for classification
ESSENTIAL_KEYWORDS = [
    "required", "essential", "must have", "mandatory", "minimum",
    "looking for", "need", "seeking", "require",
]
PREFERRED_KEYWORDS = [
    "preferred", "desirable", "nice to have", "advantageous", "bonus",
    "ideally", "plus", "beneficial",
]
MENTIONED_KEYWORDS = [
    "familiar", "exposure", "understanding", "awareness", "knowledge",
    "experience with", "background in",
]


def _resolve_alias(skill: str) -> str:
    """Resolve a skill alias to its canonical form."""
    return _ALIAS_LOOKUP.get(skill.lower(), skill.lower())


def normalize_user_skills(skills: list[str]) -> list[str]:
    """Normalize a list of user-entered skills to canonical forms.

    Applies alias resolution so that e.g. "ReactJS" -> "react", "ML" -> "machine learning".
    Deduplicates and sorts alphabetically.
    """
    seen: set[str] = set()
    result: list[str] = []
    for skill in skills:
        canonical = _resolve_alias(skill)
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return sorted(result)


def _classify_context(text: str, skill: str) -> tuple[str, bool]:
    """Classify skill as essential/preferred/desirable based on surrounding text context.

    Returns (classification, is_essential).
    """
    text_lower = text.lower()

    # Find the sentence(s) containing this skill
    sentences = re.split(r"[.!?\n]+", text_lower)
    skill_lower = skill.lower()
    relevant = [s for s in sentences if skill_lower in s]

    if not relevant:
        return ("required", True)

    context = " ".join(relevant)

    for kw in PREFERRED_KEYWORDS:
        if kw in context:
            return ("preferred", False)

    for kw in ESSENTIAL_KEYWORDS:
        if kw in context:
            return ("required", True)

    for kw in MENTIONED_KEYWORDS:
        if kw in context:
            return ("mentioned", False)

    return ("required", True)


def _extract_confidence(skill: str, text: str, source: str) -> float:
    """Calculate extraction confidence for a skill."""
    score = 0.0

    if source == "source":
        score += 0.5  # Pre-extracted from dataset
    elif source == "dictionary":
        score += 0.3  # Matched in dictionary
    else:
        score += 0.1  # Pattern match only

    # Boost if skill appears in title-like context (job title area)
    if len(skill) > 2:
        score += 0.1

    # Boost for exact matches vs partial
    text_lower = text.lower()
    if re.search(r"\b" + re.escape(skill) + r"\b", text_lower):
        score += 0.2

    return min(score, 1.0)


def extract_skills(
    description: str | None,
    existing_skills: str | None = None,
) -> list[str]:
    """Extract skills from text. Returns list of skill name strings.

    Args:
        description: Job description text.
        existing_skills: Pre-extracted skills string (from CSV dataset).

    Returns:
        Deduplicated list of normalised skill strings.
    """
    results = extract_skills_detailed(description, existing_skills)
    return [s.name for s in results]


def extract_skills_detailed(
    description: str | None,
    existing_skills: str | None = None,
) -> list[ExtractedSkill]:
    """Extract skills with full detail (confidence, classification, provenance).

    Args:
        description: Job description text.
        existing_skills: Pre-extracted skills string (from CSV dataset).

    Returns:
        List of ExtractedSkill with metadata.
    """
    seen: dict[str, ExtractedSkill] = {}

    # Parse pre-extracted skills from dataset
    if existing_skills:
        for name in _parse_skill_string(existing_skills):
            canonical = _resolve_alias(name)
            if canonical not in seen:
                classification, is_essential = _classify_context(
                    description or "", name
                )
                seen[canonical] = ExtractedSkill(
                    name=canonical,
                    confidence=0.8,
                    classification=classification,
                    provenance="source",
                    is_essential=is_essential,
                )

    # Extract from description text
    if description:
        for name in _extract_from_text(description):
            canonical = _resolve_alias(name)
            if canonical not in seen:
                classification, is_essential = _classify_context(description, name)
                conf = _extract_confidence(name, description, "dictionary")
                seen[canonical] = ExtractedSkill(
                    name=canonical,
                    confidence=conf,
                    classification=classification,
                    provenance="dictionary",
                    is_essential=is_essential,
                )

    # Sort by confidence descending, then name
    return sorted(seen.values(), key=lambda s: (-s.confidence, s.name))


def _parse_skill_string(skills_str: str) -> set[str]:
    """Parse a skills string from CSV datasets."""
    cleaned = skills_str.strip("[](){}")
    cleaned = cleaned.replace("'", "").replace('"', "")

    skills: set[str] = set()

    comma_parts = [p.strip() for p in re.split(r"[,;|]+", cleaned) if p.strip()]
    if len(comma_parts) >= 2:
        for part in comma_parts:
            skill = part.strip().lower()
            if skill and len(skill) > 1:
                skills.add(skill)
        return skills

    # Fallback: split by capitalisation pattern for space-separated phrases
    phrases = re.split(r"(?=[A-Z][a-z])", cleaned)
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        phrase_lower = phrase.lower()
        skills.add(phrase_lower)

    found_in_text = _extract_from_text(cleaned)
    skills.update(found_in_text)

    return skills


def _extract_from_text(text: str) -> set[str]:
    """Extract skills from free text using dictionary matching."""
    text_lower = text.lower()
    found: set[str] = set()

    # Multi-word skills (greedy, longest first)
    for skill in MULTI_WORD_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text_lower):
            found.add(skill)

    # Single-word skills
    words = set(re.findall(r"\b[a-z#+.]+\b", text_lower))
    single_word_skills = {s for s in ALL_SKILLS if " " not in s and "." not in s}
    found.update(words & single_word_skills)

    return found
