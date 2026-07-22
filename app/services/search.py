"""Search Service — Evidence-backed retrieval with semantic fallback.

Provides three search modes:
    1. keyword_search(): PostgreSQL full-text search (baseline)
    2. semantic_search(): pure vector similarity search
    3. evidence_search(): lexical-first retrieval with match evidence and semantic fallback

The evidence_search is the primary mode for short technical queries (e.g. "Azure",
"Python", "Docker"). It requires verifiable lexical evidence before returning a
result, and only falls back to semantic similarity when insufficient evidence-backed
results are found.
"""

import re
from dataclasses import dataclass, field
from sqlalchemy import select, func, text, or_
from sqlalchemy.orm import Session

from app.models.job import Job, JobSkill
from app.services.embedding import generate_embedding


# ── Technical Query Aliases ──
# Maps short technical terms to their validated aliases for evidence matching.
TECH_ALIASES: dict[str, list[str]] = {
    "azure": [
        "azure", "microsoft azure", "azure devops", "azure functions",
        "azure sql", "azure data factory", "azure kubernetes service",
        "aks", "azure active directory", "microsoft entra",
        "azure devops server", "azure pipeline", "arm template",
        "azure blob", "azure cosmos", "azure synapse", "azure databricks",
    ],
    "aws": [
        "aws", "amazon web services", "ec2", "s3", "lambda", "sqs",
        "sns", "dynamodb", "rds", "cloudformation", "cloudwatch",
        "iam", "eks", "ecs", "fargate", "route 53", "cloudfront",
    ],
    "docker": [
        "docker", "dockerfile", "docker compose", "docker swarm",
        "containerisation", "containerization", "container",
    ],
    "kubernetes": [
        "kubernetes", "k8s", "kubectl", "helm", "istio",
        "kustomize", "kong", "ingress",
    ],
    "python": [
        "python", "django", "flask", "fastapi", "pandas", "numpy",
        "scipy", "scikit-learn", "pytorch", "tensorflow", "keras",
        "pydantic", "pytest", "pip", "conda", "jupyter", "ipython",
    ],
    "react": [
        "react", "reactjs", "react.js", "next.js", "nextjs",
        "redux", "react native", "react-router",
    ],
    "java": [
        "java", "spring", "spring boot", "hibernate", "maven",
        "gradle", "tomcat", "junit",
    ],
    ".net": [
        ".net", ".net core", "dotnet", "c#", "csharp",
        "asp.net", "blazor", "entity framework", "nuget",
    ],
    "terraform": [
        "terraform", "tf", "hashicorp", "infrastructure as code",
        "iac", "hcl",
    ],
    "power bi": [
        "power bi", "powerbi", "dax", "power query",
        "microsoft power bi",
    ],
    "node": [
        "node.js", "nodejs", "node", "express", "nestjs",
        "fastify", "koa",
    ],
    "golang": [
        "golang", "go",
    ],
    "rust": [
        "rust", "rustlang", "cargo",
    ],
    "cybersecurity": [
        "cybersecurity", "cyber security", "information security",
        "infosec", "soc", "siem", "penetration testing", "pen test",
        "vulnerability", "ciso",
    ],
}

# ── Skill Aliases for Azure ──
# Canonical form -> aliases that should count as evidence
SKILL_ALIASES: dict[str, set[str]] = {
    "azure": {"azure", "microsoft azure", "azure devops", "azure functions",
              "azure sql", "azure data factory", "aks", "microsoft entra"},
    "aws": {"aws", "amazon web services", "ec2", "s3", "lambda"},
    "docker": {"docker", "dockerfile", "docker compose", "containerisation"},
    "kubernetes": {"kubernetes", "k8s", "kubectl", "helm"},
    "python": {"python", "django", "flask", "fastapi"},
    "react": {"react", "reactjs", "next.js", "nextjs"},
    "java": {"java", "spring", "spring boot"},
    ".net": {".net", ".net core", "c#", "asp.net"},
    "terraform": {"terraform", "hashicorp", "hcl"},
}


@dataclass
class MatchEvidence:
    """A single piece of evidence that a job matches the query."""
    field: str          # title, skill, requirement, description
    text: str           # the matching text snippet


@dataclass
class SearchResult:
    """A single search result with relevance and match evidence."""
    id: str
    title: str
    company: str | None
    location_city: str | None
    location_country: str | None
    remote: bool
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    original_salary_text: str | None
    category: str | None
    job_type: str | None
    url: str | None
    source: str | None

    # Score components
    search_relevance_score: float = 0.0   # 0-100, how well it matches the query
    profile_match_score: float | None = None  # 0-100, how well it fits the profile (optional)
    ranking_score: float = 0.0            # 0-100, final ranking score

    # Match evidence
    match_type: str = "semantic_fallback"  # exact_title, exact_skill, etc.
    matched_terms: list[str] = field(default_factory=list)
    matched_fields: list[str] = field(default_factory=list)
    match_evidence: list[MatchEvidence] = field(default_factory=list)

    # Dedup
    duplicate_group: int | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API/frontend consumption."""
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location_city": self.location_city,
            "location_country": self.location_country,
            "remote": self.remote,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "salary_period": self.salary_period,
            "original_salary_text": self.original_salary_text,
            "category": self.category,
            "job_type": self.job_type,
            "url": self.url,
            "source": self.source,
            "search_relevance_score": round(self.search_relevance_score, 1),
            "profile_match_score": round(self.profile_match_score, 1) if self.profile_match_score is not None else None,
            "ranking_score": round(self.ranking_score, 1),
            "match_type": self.match_type,
            "matched_terms": self.matched_terms,
            "matched_fields": self.matched_fields,
            "match_evidence": [{"field": e.field, "text": e.text} for e in self.match_evidence],
            "duplicate_group": self.duplicate_group,
            # Legacy fields for backward compatibility
            "similarity": round(self.search_relevance_score / 100, 4),
            "match_percentage": round(self.search_relevance_score, 1),
        }


# ── Configurable thresholds ──
EVIDENCE_MIN_RESULTS = 5       # Minimum evidence-backed results before fallback
SEMANTIC_FALLBACK_LIMIT = 10   # Max semantic fallback results
TECH_QUERY_MIN_LENGTH = 1      # Queries with this many tokens or fewer are "short"
TECH_QUERY_MAX_LENGTH = 3      # Max tokens to be considered a technical query


def _normalise_query(query: str) -> str:
    """Normalise a search query for matching."""
    q = query.lower().strip()
    q = re.sub(r"[^\w\s#+.]", " ", q)   # keep # and . for C# and .NET
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _is_technical_query(query: str) -> bool:
    """Detect if a query is a short technical term (skill/platform/language)."""
    tokens = _normalise_query(query).split()
    if len(tokens) > TECH_QUERY_MAX_LENGTH:
        return False
    # Check if it matches any known technical alias
    q_lower = _normalise_query(query)
    for tech_term in TECH_ALIASES:
        if q_lower == tech_term or q_lower in TECH_ALIASES[tech_term]:
            return True
    # Also treat single multi-word terms as technical (e.g. "Power BI")
    if len(tokens) <= 2 and all(t.isalpha() or t in "#+." for t in tokens):
        return True
    return False


def _get_aliases(query: str) -> list[str]:
    """Get validated aliases for a technical query."""
    q_lower = _normalise_query(query)
    if q_lower in TECH_ALIASES:
        return TECH_ALIASES[q_lower]
    # Fallback: use the query itself
    return [q_lower]


def _get_skill_aliases(query: str) -> set[str]:
    """Get validated skill aliases for a query."""
    q_lower = _normalise_query(query)
    if q_lower in SKILL_ALIASES:
        return SKILL_ALIASES[q_lower]
    return {q_lower}


def _build_lexical_evidence_query(query: str):
    """Build a SQL query that searches for lexical evidence of the query."""
    aliases = _get_aliases(query)
    alias_conditions = []
    for alias in aliases:
        pattern = f"%{alias}%"
        alias_conditions.append(Job.title.ilike(pattern))
        alias_conditions.append(Job.description.ilike(pattern))
        alias_conditions.append(Job.description_clean.ilike(pattern))
        alias_conditions.append(Job.requirements.ilike(pattern))
        alias_conditions.append(Job.responsibilities.ilike(pattern))

    # Also search the job_skills table for skill matches
    skill_aliases = _get_skill_aliases(query)
    skill_conditions = []
    for skill_alias in skill_aliases:
        skill_conditions.append(func.lower(JobSkill.skill).like(f"%{skill_alias}%"))

    return alias_conditions, skill_conditions


def _extract_match_evidence(
    job, query: str, aliases: list[str], skill_aliases: set[str]
) -> tuple[list[MatchEvidence], list[str], list[str], str]:
    """Extract match evidence from a job record for the given query.

    Returns:
        (evidence_list, matched_terms, matched_fields, match_type)
    """
    evidence = []
    matched_terms = []
    matched_fields = []
    best_match_type = "semantic_fallback"

    title = (job.title or "").lower()
    desc = (job.description or "").lower()
    desc_clean = (job.description_clean or "").lower()
    reqs = (job.requirements or "").lower()
    resp = (job.responsibilities or "").lower()

    # Check title for exact match
    for alias in aliases:
        if alias in title:
            evidence.append(MatchEvidence(field="title", text=job.title))
            matched_terms.append(alias)
            matched_fields.append("title")
            best_match_type = "exact_title"
            break

    # Check skills (will be checked separately via job_skills table)

    # Check requirements
    for alias in aliases:
        if alias in reqs:
            # Extract a snippet around the match
            idx = reqs.index(alias)
            start = max(0, idx - 40)
            end = min(len(job.requirements or ""), idx + len(alias) + 40)
            snippet = (job.requirements or "")[start:end].strip()
            evidence.append(MatchEvidence(field="requirements", text=f"...{snippet}..."))
            matched_terms.append(alias)
            matched_fields.append("requirements")
            if best_match_type not in ("exact_title",):
                best_match_type = "exact_requirement"
            break

    # Check description
    for alias in aliases:
        if alias in desc or alias in desc_clean:
            source = job.description or job.description_clean or ""
            idx = (desc if alias in desc else desc_clean).index(alias)
            start = max(0, idx - 50)
            end = min(len(source), idx + len(alias) + 50)
            snippet = source[start:end].strip()
            evidence.append(MatchEvidence(field="description", text=f"...{snippet}..."))
            matched_terms.append(alias)
            matched_fields.append("description")
            if best_match_type not in ("exact_title", "exact_requirement"):
                best_match_type = "exact_description"
            break

    return evidence, matched_terms, matched_fields, best_match_type


def _check_skill_match(job_id, db: Session, skill_aliases: set[str]) -> list[MatchEvidence]:
    """Check if a job has matching skills in the job_skills table."""
    evidence = []
    skills = db.query(JobSkill).filter(JobSkill.job_id == job_id).all()
    for s in skills:
        skill_lower = (s.skill or "").lower()
        for alias in skill_aliases:
            if alias in skill_lower or skill_lower in alias:
                evidence.append(MatchEvidence(field="skill", text=s.skill))
                break
    return evidence


def _compute_lexical_score(
    match_type: str, num_evidence: int, matched_fields: list[str]
) -> float:
    """Compute a search relevance score based on lexical evidence quality."""
    base_scores = {
        "exact_title": 95.0,
        "exact_skill": 85.0,
        "exact_requirement": 80.0,
        "exact_description": 70.0,
        "semantic_fallback": 40.0,
    }
    score = base_scores.get(match_type, 40.0)

    # Bonus for multiple evidence fields
    unique_fields = len(set(matched_fields))
    if unique_fields >= 3:
        score = min(score + 5, 100.0)
    elif unique_fields >= 2:
        score = min(score + 2, 100.0)

    return score


def _normalise_company(name: str | None) -> str:
    """Normalise a company name for deduplication."""
    if not name:
        return ""
    n = name.lower().strip()
    # Remove common suffixes
    for suffix in [" ltd", " limited", " inc", " inc.", " llc", " corp",
                    " corporation", " plc", " gmbh", " ag", " s.a.", " s.a.s"]:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
    # Remove punctuation
    n = re.sub(r"[^\w\s]", "", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _normalise_title(title: str | None) -> str:
    """Normalise a job title for deduplication."""
    if not title:
        return ""
    t = title.lower().strip()
    # Remove common prefixes/suffixes
    for prefix in ["senior ", "sr. ", "sr ", "junior ", "jr. ", "jr ", "lead ", "principal "]:
        t = t.replace(prefix, "")
    # Remove punctuation except spaces
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _group_duplicates(results: list[SearchResult]) -> list[SearchResult]:
    """Group near-duplicate results by normalised company+title.

    Assigns a duplicate_group integer to each result. Results in the same
    group are near-duplicates. The first result in each group is the
    "primary" (highest scoring).
    """
    from rapidfuzz import fuzz

    groups: list[list[int]] = []  # Each group is a list of indices into results
    assigned = set()

    for i, r_i in enumerate(results):
        if i in assigned:
            continue
        group = [i]
        norm_comp_i = _normalise_company(r_i.company)
        norm_title_i = _normalise_title(r_i.title)

        for j in range(i + 1, len(results)):
            if j in assigned:
                continue
            r_j = results[j]
            norm_comp_j = _normalise_company(r_j.company)
            norm_title_j = _normalise_title(r_j.title)

            # Company must be very similar
            comp_sim = fuzz.token_set_ratio(norm_comp_i, norm_comp_j) / 100.0
            if comp_sim < 0.80:
                continue

            # Title must be reasonably similar
            title_sim = fuzz.token_set_ratio(norm_title_i, norm_title_j) / 100.0
            if title_sim < 0.60:
                continue

            group.append(j)
            assigned.add(j)

        if len(group) > 1:
            groups.append(group)
        assigned.add(i)

    # Assign group IDs
    for group_idx, group in enumerate(groups):
        for idx in group:
            results[idx].duplicate_group = group_idx

    return results


def format_salary_display(
    salary_min: float | None,
    salary_max: float | None,
    salary_currency: str | None,
    salary_period: str | None = None,
) -> str:
    """Format salary for display, handling all missing-value combinations.

    Rules:
    - Never default unknown currency to USD
    - Never display $ unless currency is confirmed USD
    - Missing salary_min -> "Up to £X"
    - Missing salary_max -> "From £X"
    - Both missing -> "Salary not disclosed"
    - Preserve original currency
    """
    if salary_min is None and salary_max is None:
        return "Salary not disclosed"

    # Currency symbol mapping
    symbols = {
        "GBP": "£", "USD": "$", "EUR": "€", "INR": "₹",
        "CAD": "C$", "AUD": "A$", "CHF": "CHF", "SGD": "S$",
    }
    symbol = symbols.get((salary_currency or "").upper(), "")

    period_text = ""
    if salary_period:
        period_map = {
            "annual": "per year", "monthly": "per month",
            "weekly": "per week", "daily": "per day", "hourly": "per hour",
        }
        period_text = f" {period_map.get(salary_period, salary_period)}"

    def fmt(val):
        if val is None:
            return None
        if val == int(val):
            return f"{symbol}{int(val):,}"
        return f"{symbol}{val:,.0f}"

    min_fmt = fmt(salary_min)
    max_fmt = fmt(salary_max)

    if min_fmt and max_fmt:
        if salary_min == salary_max:
            return f"{min_fmt}{period_text}"
        return f"{min_fmt}–{max_fmt}{period_text}"
    elif max_fmt:
        return f"Up to {max_fmt}{period_text}"
    elif min_fmt:
        return f"From {min_fmt}{period_text}"

    return "Salary not disclosed"


def evidence_search(
    db: Session,
    query: str,
    limit: int = 20,
    min_semantic_results: int = EVIDENCE_MIN_RESULTS,
    enable_semantic_fallback: bool = True,
) -> list[dict]:
    """Evidence-backed search with controlled semantic fallback.

    For short technical queries (e.g. "Azure", "Python", "Docker"):
    1. First require verifiable lexical evidence (title, skills, requirements, description)
    2. Only fall back to semantic similarity if insufficient evidence-backed results
    3. All fallback results are clearly labelled as semantic_fallback

    For longer natural-language queries, falls back to semantic search directly.

    Args:
        db: Database session.
        query: Search query.
        limit: Max results to return.
        min_semantic_results: Min evidence results before enabling fallback.
        enable_semantic_fallback: Whether to use semantic fallback at all.

    Returns:
        List of dicts with search results, scores, and match evidence.
    """
    query_clean = _normalise_query(query)
    if not query_clean:
        return []

    is_tech = _is_technical_query(query)

    if not is_tech:
        # Long natural-language query: use semantic search directly
        return _semantic_search_with_evidence(db, query, limit)

    # ── Stage 1: Lexical evidence retrieval ──
    aliases = _get_aliases(query)
    skill_aliases = _get_skill_aliases(query)

    alias_conditions, skill_conditions = _build_lexical_evidence_query(query)

    # Search jobs that have lexical evidence
    if alias_conditions:
        job_stmt = (
            select(Job)
            .where(Job.is_active.is_(True), or_(*alias_conditions))
            .limit(limit * 3)  # Over-fetch for dedup
        )
        candidate_jobs = db.execute(job_stmt).scalars().all()
    else:
        candidate_jobs = []

    # Search job_skills for skill matches
    if skill_conditions:
        skill_job_ids_stmt = (
            select(JobSkill.job_id)
            .where(or_(*skill_conditions))
            .group_by(JobSkill.job_id)
        )
        skill_job_ids = [row[0] for row in db.execute(skill_job_ids_stmt).all()]

        # Fetch the actual jobs
        if skill_job_ids:
            extra_jobs = (
                db.query(Job)
                .filter(Job.is_active.is_(True), Job.id.in_(skill_job_ids), ~Job.id.in_([j.id for j in candidate_jobs]))
                .limit(limit * 3)
                .all()
            )
            candidate_jobs.extend(extra_jobs)
    else:
        extra_jobs = []

    # ── Build search results with evidence ──
    results: list[SearchResult] = []
    seen_ids = set()

    for job in candidate_jobs:
        if job.id in seen_ids:
            continue
        seen_ids.add(job.id)

        evidence, matched_terms, matched_fields, match_type = _extract_match_evidence(
            job, query, aliases, skill_aliases
        )

        # Check skill table evidence
        skill_evidence = _check_skill_match(job.id, db, skill_aliases)
        if skill_evidence:
            evidence.extend(skill_evidence)
            matched_fields.append("skill")
            matched_terms.extend([e.text.lower() for e in skill_evidence])
            if match_type not in ("exact_title",):
                match_type = "exact_skill"

        if not evidence:
            continue

        # Compute relevance score
        relevance = _compute_lexical_score(match_type, len(evidence), matched_fields)

        sr = SearchResult(
            id=str(job.id),
            title=job.title_clean or job.title,
            company=job.company,
            location_city=job.location_city,
            location_country=job.location_country,
            remote=job.remote,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
            original_salary_text=job.original_salary_text,
            category=job.category,
            job_type=job.job_type,
            url=job.url,
            source=job.source,
            search_relevance_score=relevance,
            ranking_score=relevance,
            match_type=match_type,
            matched_terms=list(set(matched_terms)),
            matched_fields=list(set(matched_fields)),
            match_evidence=evidence,
        )
        results.append(sr)

    # Sort by relevance
    results.sort(key=lambda r: r.ranking_score, reverse=True)

    # ── Stage 2: Semantic fallback (if insufficient evidence results) ──
    if enable_semantic_fallback and len(results) < min_semantic_results:
        remaining = limit - len(results)
        existing_ids = {r.id for r in results}

        semantic_results = _semantic_search_with_evidence(
            db, query, remaining + 5  # fetch a few extra for dedup
        )

        for sr_dict in semantic_results:
            if sr_dict["id"] in existing_ids:
                continue
            # Mark as semantic fallback
            sr_dict["match_type"] = "semantic_fallback"
            sr_dict["matched_terms"] = []
            sr_dict["matched_fields"] = []
            sr_dict["match_evidence"] = [
                {"field": "note", "text": "No direct lexical evidence found for this query — matched by semantic similarity."}
            ]
            sr_dict["search_relevance_score"] = max(sr_dict["search_relevance_score"] * 0.5, 20.0)
            sr_dict["ranking_score"] = sr_dict["search_relevance_score"]

            sr = SearchResult(
                id=sr_dict["id"],
                title=sr_dict["title"],
                company=sr_dict.get("company"),
                location_city=sr_dict.get("location_city"),
                location_country=sr_dict.get("location_country"),
                remote=sr_dict.get("remote", False),
                salary_min=sr_dict.get("salary_min"),
                salary_max=sr_dict.get("salary_max"),
                salary_currency=sr_dict.get("salary_currency"),
                salary_period=sr_dict.get("salary_period"),
                original_salary_text=sr_dict.get("original_salary_text"),
                category=sr_dict.get("category"),
                job_type=sr_dict.get("job_type"),
                url=sr_dict.get("url"),
                source=sr_dict.get("source"),
                search_relevance_score=sr_dict["search_relevance_score"],
                ranking_score=sr_dict["ranking_score"],
                match_type="semantic_fallback",
                matched_terms=[],
                matched_fields=[],
                match_evidence=[MatchEvidence(field="note", text="No direct lexical evidence found for this query — matched by semantic similarity.")],
            )
            results.append(sr)
            existing_ids.add(sr.id)

    # Deduplicate at result level
    results = _group_duplicates(results[:limit])

    return [r.to_dict() for r in results]


def _semantic_search_with_evidence(
    db: Session, query: str, limit: int
) -> list[dict]:
    """Semantic search that returns results in SearchResult-compatible dict format."""
    query_embedding = generate_embedding(query, is_query=True)
    distance = Job.embedding.cosine_distance(query_embedding)

    stmt = (
        select(
            Job.id, Job.title, Job.title_clean, Job.company,
            Job.location_city, Job.location_country, Job.remote,
            Job.salary_min, Job.salary_max, Job.salary_currency,
            Job.salary_period, Job.original_salary_text,
            Job.category, Job.job_type, Job.url, Job.source,
            (1 - distance).label("similarity"),
        )
        .where(Job.embedding.isnot(None), Job.is_active.is_(True))
        .order_by(distance)
        .limit(limit)
    )

    results = db.execute(stmt).all()

    return [
        {
            "id": str(row.id),
            "title": row.title_clean or row.title,
            "company": row.company,
            "location_city": row.location_city,
            "location_country": row.location_country,
            "remote": row.remote,
            "salary_min": row.salary_min,
            "salary_max": row.salary_max,
            "salary_currency": row.salary_currency,
            "salary_period": getattr(row, "salary_period", None),
            "original_salary_text": getattr(row, "original_salary_text", None),
            "category": row.category,
            "job_type": row.job_type,
            "url": row.url,
            "source": row.source,
            "search_relevance_score": round(float(row.similarity) * 100, 1),
            "ranking_score": round(float(row.similarity) * 100, 1),
            "match_type": "semantic_fallback",
            "matched_terms": [],
            "matched_fields": [],
            "match_evidence": [],
        }
        for row in results
    ]


# ── Legacy functions (preserved for backward compatibility) ──

def keyword_search(db: Session, query: str, limit: int = 10) -> list[dict]:
    """PostgreSQL full-text search — the KEYWORD BASELINE for comparison."""
    words = [w.strip() for w in query.split() if w.strip()]
    if not words:
        return []

    tsquery_expr = func.plainto_tsquery("english", query)
    rank = func.ts_rank(Job.search_vector, tsquery_expr)

    stmt = (
        select(
            Job.id, Job.title, Job.title_clean, Job.company,
            Job.location_city, Job.location_country, Job.remote,
            Job.salary_min, Job.salary_max, Job.salary_currency,
            Job.category, Job.url, Job.source,
            rank.label("fts_rank"),
        )
        .where(Job.is_active.is_(True), Job.search_vector.op("@@")(tsquery_expr))
        .order_by(rank.desc())
        .limit(limit)
    )

    results = db.execute(stmt).all()

    return [
        {
            "id": str(row.id),
            "title": row.title_clean or row.title,
            "company": row.company,
            "location_city": row.location_city,
            "location_country": row.location_country,
            "remote": row.remote,
            "salary_min": row.salary_min,
            "salary_max": row.salary_max,
            "salary_currency": row.salary_currency,
            "category": row.category,
            "url": row.url,
            "source": row.source,
            "fts_rank": round(float(row.fts_rank), 6),
            "search_relevance_score": round(float(row.fts_rank) * 100, 1),
            "ranking_score": round(float(row.fts_rank) * 100, 1),
            "match_type": "keyword",
            "matched_terms": [],
            "matched_fields": [],
            "match_evidence": [],
        }
        for row in results
    ]


def semantic_search(
    db: Session,
    query: str,
    limit: int = 10,
    min_similarity: float = 0.0,
) -> list[dict]:
    """Search jobs by semantic similarity to a natural language query."""
    query_embedding = generate_embedding(query, is_query=True)
    distance = Job.embedding.cosine_distance(query_embedding)

    stmt = (
        select(
            Job.id, Job.title, Job.title_clean, Job.company,
            Job.location_city, Job.location_country, Job.remote,
            Job.salary_min, Job.salary_max, Job.salary_currency,
            Job.salary_period, Job.original_salary_text,
            Job.category, Job.job_type, Job.url, Job.source,
            (1 - distance).label("similarity"),
        )
        .where(Job.embedding.isnot(None), Job.is_active.is_(True))
        .order_by(distance)
        .limit(limit)
    )

    results = db.execute(stmt).all()

    jobs = []
    for row in results:
        similarity = float(row.similarity)
        if similarity < min_similarity:
            continue
        jobs.append({
            "id": str(row.id),
            "title": row.title_clean or row.title,
            "company": row.company,
            "location_city": row.location_city,
            "location_country": row.location_country,
            "remote": row.remote,
            "salary_min": row.salary_min,
            "salary_max": row.salary_max,
            "salary_currency": row.salary_currency,
            "salary_period": getattr(row, "salary_period", None),
            "original_salary_text": getattr(row, "original_salary_text", None),
            "category": row.category,
            "job_type": row.job_type,
            "url": row.url,
            "source": row.source,
            "similarity": round(similarity, 4),
            "search_relevance_score": round(similarity * 100, 1),
            "ranking_score": round(similarity * 100, 1),
            "match_type": "semantic",
            "matched_terms": [],
            "matched_fields": [],
            "match_evidence": [],
        })

    return jobs


def hybrid_search(
    db: Session,
    query: str,
    location_country: str | None = None,
    remote_only: bool = False,
    category: str | None = None,
    min_salary: float | None = None,
    limit: int = 10,
    rerank: bool = False,
) -> list[dict]:
    """Semantic search combined with structured SQL filters and optional reranking."""
    query_embedding = generate_embedding(query, is_query=True)
    distance = Job.embedding.cosine_distance(query_embedding)

    stmt = select(
        Job.id, Job.title, Job.title_clean, Job.company,
        Job.location_city, Job.location_country, Job.remote,
        Job.salary_min, Job.salary_max, Job.salary_currency,
        Job.salary_period, Job.original_salary_text,
        Job.category, Job.job_type, Job.url, Job.source,
        Job.description,
        (1 - distance).label("similarity"),
    ).where(Job.embedding.isnot(None), Job.is_active.is_(True))

    if location_country:
        stmt = stmt.where(Job.location_country.ilike(f"%{location_country}%"))
    if remote_only:
        stmt = stmt.where(Job.remote.is_(True))
    if category:
        stmt = stmt.where(Job.category == category)
    if min_salary:
        stmt = stmt.where(Job.salary_max >= min_salary)

    fetch_limit = limit * 3 if rerank else limit
    stmt = stmt.order_by(distance).limit(fetch_limit)

    results = db.execute(stmt).all()

    jobs = [
        {
            "id": str(row.id),
            "title": row.title_clean or row.title,
            "company": row.company,
            "location_city": row.location_city,
            "location_country": row.location_country,
            "remote": row.remote,
            "salary_min": row.salary_min,
            "salary_max": row.salary_max,
            "salary_currency": row.salary_currency,
            "salary_period": getattr(row, "salary_period", None),
            "original_salary_text": getattr(row, "original_salary_text", None),
            "category": row.category,
            "job_type": row.job_type,
            "url": row.url,
            "source": row.source,
            "description": row.description or "",
            "similarity": round(float(row.similarity), 4),
            "search_relevance_score": round(float(row.similarity) * 100, 1),
            "ranking_score": round(float(row.similarity) * 100, 1),
            "match_type": "semantic",
            "matched_terms": [],
            "matched_fields": [],
            "match_evidence": [],
        }
        for row in results
    ]

    if rerank and jobs:
        # Enrich candidates with skills for better reranking
        job_ids = [j["id"] for j in jobs]
        skill_rows = (
            db.query(JobSkill.job_id, JobSkill.skill)
            .filter(JobSkill.job_id.in_(job_ids))
            .all()
        )
        skills_by_job: dict[str, list[str]] = {}
        for row in skill_rows:
            skills_by_job.setdefault(str(row.job_id), []).append(row.skill)
        for job in jobs:
            job["skills"] = skills_by_job.get(job["id"], [])

        from app.services.reranker import rerank_candidates
        jobs = rerank_candidates(query, jobs, top_n=limit)
        for job in jobs:
            if "rerank_score" in job:
                normalized = max(0, min(1, (job["rerank_score"] + 10) / 20))
                job["rerank_percentage"] = round(normalized * 100, 1)

    return jobs


def find_similar_jobs(db: Session, job_id: str, limit: int = 5) -> list[dict]:
    """Find jobs similar to a given job (e.g. 'More like this')."""
    reference = db.query(Job).filter(Job.id == job_id, Job.is_active.is_(True)).first()
    if not reference or reference.embedding is None:
        return []

    distance = Job.embedding.cosine_distance(reference.embedding)

    stmt = (
        select(
            Job.id, Job.title, Job.title_clean, Job.company,
            Job.location_city, Job.remote, Job.category, Job.url,
            (1 - distance).label("similarity"),
        )
        .where(Job.embedding.isnot(None), Job.is_active.is_(True))
        .where(Job.id != job_id)
        .order_by(distance)
        .limit(limit)
    )

    results = db.execute(stmt).all()

    return [
        {
            "id": str(row.id),
            "title": row.title_clean or row.title,
            "company": row.company,
            "location_city": row.location_city,
            "remote": row.remote,
            "category": row.category,
            "url": row.url,
            "similarity": round(float(row.similarity), 4),
        }
        for row in results
    ]


def personalized_search(
    db: Session, query: str, profile, *, location_country: str | None = None,
    remote_only: bool = False, category: str | None = None,
    min_salary: float | None = None, threshold: float = 0.35,
    limit: int = 20, offset: int = 0,
) -> list[dict]:
    """Blend manual-query evidence with existing profile recommendation scores."""
    from app.services.recommendation import compute_match_score

    candidates = hybrid_search(
        db, query=query, location_country=location_country,
        remote_only=remote_only, category=category, min_salary=min_salary,
        limit=min(100, offset + limit * 3),
    )
    ranked = []
    query_lower = query.strip().lower()
    for result in candidates:
        job = db.query(Job).filter(Job.id == result["id"], Job.is_active.is_(True)).first()
        if not job:
            continue
        skills = [row.skill for row in db.query(JobSkill).filter(JobSkill.job_id == job.id).all()]
        breakdown = compute_match_score(
            profile, job, skills, result["similarity"], profile.preferred_job_types,
        )
        if breakdown.overall_score < threshold:
            continue
        query_score = max(0.0, min(1.0, result["similarity"]))
        result["profile_match_score"] = round(breakdown.overall_score * 100, 1)
        result["match_percentage"] = result["profile_match_score"]
        result["ranking_score"] = round((breakdown.overall_score * 0.7 + query_score * 0.3) * 100, 1)
        title = (job.title_clean or job.title or "").lower()
        description = (job.description or "").lower()
        if query_lower and query_lower in title:
            result["match_type"] = "exact_title"
        elif query_lower and query_lower in description:
            result["match_type"] = "exact_description"
        else:
            result["match_type"] = "semantic_fallback"
        ranked.append(result)
    ranked.sort(key=lambda row: (-row["ranking_score"], row["id"]))
    return ranked[offset:offset + limit]
