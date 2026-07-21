"""Category Normalisation Processor.

Maps raw job categories to a fixed taxonomy of ~20 categories.
This gives consistent filtering and makes evaluation cleaner.
"""

# The canonical taxonomy — every job maps to one of these
CATEGORIES = [
    "Software Engineering",
    "Data Science & Analytics",
    "Information Technology",
    "DevOps & Infrastructure",
    "Product Management",
    "Design & UX",
    "Marketing",
    "Sales & Business Development",
    "Finance & Accounting",
    "Human Resources",
    "Operations",
    "Customer Support",
    "Legal",
    "Healthcare",
    "Education & Training",
    "Engineering (Non-Software)",
    "Project Management",
    "Content & Writing",
    "Research & Science",
    "Other",
]

# Keyword-based mapping rules (checked in order, first match wins)
CATEGORY_RULES: list[tuple[list[str], str]] = [
    # Software / Dev
    (["software engineer", "software developer", "full stack", "fullstack",
      "frontend", "front-end", "backend", "back-end", "web developer",
      "mobile developer", "ios developer", "android developer", "java developer",
      "python developer", ".net developer", "react developer", "node.js",
      "programmer", "sde", "software development"], "Software Engineering"),

    # Data
    (["data scientist", "data analyst", "data engineer", "machine learning",
      "deep learning", "ai engineer", "artificial intelligence", "nlp",
      "business intelligence", "bi analyst", "analytics", "statistician",
      "data mining"], "Data Science & Analytics"),

    # IT
    (["information technology", "it support", "system administrator",
      "network engineer", "it manager", "helpdesk", "technical support",
      "cybersecurity", "security analyst", "it specialist", "sysadmin"],
     "Information Technology"),

    # DevOps
    (["devops", "site reliability", "sre", "cloud engineer", "platform engineer",
      "infrastructure", "kubernetes", "docker", "aws engineer", "azure engineer",
      "ci/cd"], "DevOps & Infrastructure"),

    # Product
    (["product manager", "product owner", "product lead", "product director",
      "product analyst"], "Product Management"),

    # Design
    (["ux designer", "ui designer", "product designer", "graphic designer",
      "visual designer", "interaction designer", "ux researcher", "design lead"],
     "Design & UX"),

    # Marketing
    (["marketing", "seo", "sem", "growth", "brand manager", "social media",
      "content marketing", "digital marketing", "email marketing",
      "performance marketing"], "Marketing"),

    # Sales
    (["sales", "business development", "account executive", "account manager",
      "bdr", "sdr", "revenue", "partnerships"], "Sales & Business Development"),

    # Finance
    (["finance", "accountant", "accounting", "financial analyst", "controller",
      "auditor", "bookkeeper", "tax", "treasury", "cfo", "investment"],
     "Finance & Accounting"),

    # HR
    (["human resources", "hr manager", "recruiter", "talent acquisition",
      "people operations", "hr business partner", "compensation",
      "employee relations"], "Human Resources"),

    # Operations
    (["operations", "supply chain", "logistics", "procurement", "warehouse",
      "inventory", "facilities"], "Operations"),

    # Support
    (["customer support", "customer service", "customer success",
      "client support", "help desk", "support engineer", "support specialist"],
     "Customer Support"),

    # Legal
    (["legal", "lawyer", "attorney", "counsel", "paralegal", "compliance",
      "regulatory"], "Legal"),

    # Healthcare
    (["healthcare", "medical", "nurse", "physician", "clinical",
      "pharmaceutical", "health"], "Healthcare"),

    # Education
    (["education", "teacher", "instructor", "trainer", "tutor",
      "learning", "curriculum", "professor", "academic"], "Education & Training"),

    # Non-software engineering
    (["mechanical engineer", "electrical engineer", "civil engineer",
      "chemical engineer", "hardware engineer", "structural engineer",
      "manufacturing engineer"], "Engineering (Non-Software)"),

    # PM
    (["project manager", "scrum master", "agile coach", "program manager",
      "delivery manager", "pmo"], "Project Management"),

    # Content
    (["writer", "editor", "copywriter", "content creator", "journalist",
      "technical writer", "content strategist", "blogger"], "Content & Writing"),

    # Research
    (["researcher", "scientist", "research engineer", "research analyst",
      "r&d", "laboratory"], "Research & Science"),
]


def normalise_category(raw_category: str | None, title: str | None = None) -> str:
    """Map a raw category and/or title to a canonical category.

    Args:
        raw_category: The category from the source (may be None or messy).
        title: The job title (used as fallback signal).

    Returns:
        One of the canonical category strings.
    """
    # Combine signals
    text = f"{raw_category or ''} {title or ''}".lower()

    if not text.strip():
        return "Other"

    # Check rules in order
    for keywords, category in CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return category

    # If the raw_category itself is close to a canonical one, use it
    if raw_category:
        raw_lower = raw_category.strip().lower()
        for cat in CATEGORIES:
            if raw_lower in cat.lower() or cat.lower() in raw_lower:
                return cat

    return "Other"
