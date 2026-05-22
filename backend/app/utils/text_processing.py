"""
PlaceUp Career — Text Processing Utilities
Text cleaning, keyword extraction, and NLP utilities for resume/job analysis.
"""

import re
from collections import Counter
from typing import Optional


# Common English stop words to exclude from keyword extraction
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "or", "she",
    "that", "the", "to", "was", "were", "will", "with", "you", "your",
    "this", "they", "but", "have", "had", "not", "what", "all", "can",
    "her", "who", "did", "do", "does", "done", "been", "being", "which",
    "their", "there", "than", "then", "them", "these", "those", "our",
    "we", "us", "would", "could", "should", "shall", "may", "might",
    "must", "about", "above", "after", "again", "also", "any", "because",
    "before", "between", "both", "each", "few", "how", "into", "just",
    "more", "most", "no", "nor", "only", "other", "own", "same", "so",
    "some", "such", "too", "very", "when", "where", "while", "why",
    # Job description filler words
    "experience", "work", "working", "team", "role", "position",
    "ability", "skills", "required", "requirements", "preferred",
    "including", "strong", "excellent", "responsible", "responsibilities",
    "opportunity", "looking", "join", "company", "within", "across",
    "etc", "using", "used", "well", "new", "help", "make", "ensure",
    "applicant", "candidate", "candidates", "employee", "employees",
    "employer", "employment", "apply", "application", "applications",
    "provide", "provides", "business", "customer", "customers",
    "client", "clients", "services", "solutions", "environment",
    "knowledge", "understanding", "preferred", "plus", "bonus",
    "benefits", "compensation", "salary", "range", "equal", "diversity",
    "inclusion", "accommodation", "reasonable", "protected", "status",
}

BOILERPLATE_PHRASES = {
    "equal opportunity", "reasonable accommodation", "protected status",
    "privacy policy", "terms conditions", "apply now", "job description",
    "job type", "salary range", "benefits package", "work environment",
    "background check", "drug screen", "authorized work", "without sponsorship",
}

# Technical skills dictionary for enhanced extraction
TECH_SKILLS = {
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "sql",
    "react", "angular", "vue", "svelte", "next.js", "nuxt", "fastapi",
    "django", "flask", "express", "spring", "node.js", "rails",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "mongodb", "postgresql", "mysql", "redis", "elasticsearch",
    "graphql", "rest", "grpc", "microservices", "ci/cd", "devops",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn",
    "agile", "scrum", "jira", "git", "linux", "bash",
    "html", "css", "tailwind", "sass", "webpack", "vite",
    "figma", "sketch", "adobe", "photoshop", "illustrator",
    "tableau", "power bi", "looker", "databricks", "spark",
    "kafka", "rabbitmq", "celery", "airflow",
    "oauth", "jwt", "ssl", "encryption", "cybersecurity",
    ".net", "firebase", "supabase", "prisma", "langchain",
    "openai", "llm", "rag", "vector database",
    "bigquery", "snowflake", "dbt", "mlflow",
    "active directory", "microsoft 365", "office 365", "intune", "sccm",
    "servicenow", "technical support", "desktop support", "help desk",
    "service desk", "ticketing", "troubleshooting", "vpn", "windows",
    "macos", "linux administration", "networking", "tcp/ip",
    "financial modeling", "forecasting", "budgeting", "audit", "gaap",
    "risk management", "aml", "kyc", "compliance", "regulatory affairs",
    "clinical research", "clinical trials", "gcp clinical", "biostatistics",
    "bioinformatics", "genomics", "laboratory", "research assistant",
    "solidworks", "autocad", "catia", "ansys", "fea", "gd&t",
    "manufacturing", "lean", "six sigma", "quality assurance",
    "project management", "program management", "supply chain",
    "procurement", "logistics", "market research", "seo",
    "google analytics", "content strategy", "social media",
    "ux research", "wireframing", "prototyping", "adobe creative suite",
}


def clean_text(text: str) -> str:
    """Clean and normalize text for processing.

    Removes HTML tags, excess whitespace, special characters,
    and normalizes unicode. Preserves meaningful punctuation.

    Args:
        text: Raw text string (potentially from PDF/HTML)

    Returns:
        Cleaned text string
    """
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove URLs
    text = re.sub(r"https?://\S+", " ", text)

    # Remove email addresses
    text = re.sub(r"\S+@\S+\.\S+", " ", text)

    # Replace multiple whitespace with single space
    text = re.sub(r"\s+", " ", text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def extract_keywords(
    text: str,
    top_n: int = 30,
    min_word_length: int = 2,
    include_tech: bool = True,
) -> list[str]:
    """Extract top keywords from text, excluding stop words.

    Uses frequency counting with optional technical skill boosting.
    Returns keywords ordered by relevance (frequency * boost).

    Args:
        text: Input text to extract keywords from
        top_n: Maximum number of keywords to return
        min_word_length: Minimum word length to consider
        include_tech: Whether to boost known technical skills

    Returns:
        List of keywords ordered by relevance
    """
    # Normalize and remove job-board/EEO boilerplate before keyword counting.
    text_lower = clean_text(text).lower()
    text_lower = re.sub(
        r"\b(equal opportunity employer|reasonable accommodation|protected veteran|"
        r"privacy policy|terms and conditions|background check|drug screen|"
        r"applicants will receive consideration|we are committed to diversity)\b",
        " ",
        text_lower,
    )
    words = re.findall(r"\b[a-z][a-z0-9+#./-]*\b", text_lower)

    # Filter stop words and short words
    filtered = [
        w for w in words
        if w not in STOP_WORDS
        and len(w) >= min_word_length
        and not w.isdigit()
        and not re.fullmatch(r"\d+[a-z]*", w)
    ]

    # Count frequencies
    counter = Counter(filtered)

    # Add meaningful two-word phrases. This keeps ATS keywords closer to the
    # JD language ("data pipeline", "active directory") instead of noisy
    # single words like "data" or "active".
    for a, b in zip(filtered, filtered[1:]):
        phrase = f"{a} {b}"
        if phrase not in BOILERPLATE_PHRASES and a != b:
            counter[phrase] += 2

    # Boost technical skills
    if include_tech:
        # Check for multi-word tech terms
        for skill in TECH_SKILLS:
            if " " in skill and skill in text_lower:
                counter[skill] = counter.get(skill, 0) + 8
            elif skill in counter:
                counter[skill] = counter[skill] * 3

    out: list[str] = []
    for kw, _ in counter.most_common(top_n * 2):
        if kw in BOILERPLATE_PHRASES:
            continue
        if " " not in kw and kw in STOP_WORDS:
            continue
        if len(kw) < min_word_length:
            continue
        out.append(kw)
        if len(out) >= top_n:
            break
    return out


def _skill_pattern(skill: str) -> str:
    """Build a regex pattern for a skill that handles non-word-char boundaries.

    Standard \b fails for skills like c#, c++, .net because \b only works
    at word/non-word transitions, but # and + are already non-word chars.
    Use lookahead/lookbehind for such skills instead.
    """
    escaped = re.escape(skill)
    prefix = r"\b" if skill[0].isalnum() or skill[0] == "_" else r"(?<!\w)"
    suffix = r"\b" if skill[-1].isalnum() or skill[-1] == "_" else r"(?!\w)"
    return prefix + escaped + suffix


def extract_skills_from_text(text: str) -> list[str]:
    """Extract recognized technical skills from text.

    Matches against the TECH_SKILLS dictionary using exact
    and fuzzy matching. Handles multi-word skills.

    Args:
        text: Input text to scan for skills

    Returns:
        List of matched technical skills
    """
    text_lower = text.lower()
    found_skills = []

    for skill in TECH_SKILLS:
        if " " in skill:
            if skill in text_lower:
                found_skills.append(skill)
        else:
            if re.search(_skill_pattern(skill), text_lower):
                found_skills.append(skill)

    return sorted(set(found_skills))


def compute_keyword_overlap(
    keywords1: list[str],
    keywords2: list[str],
) -> tuple[list[str], list[str], float]:
    """Compute keyword overlap between two keyword lists.

    Args:
        keywords1: Keywords from document 1 (e.g., resume)
        keywords2: Keywords from document 2 (e.g., job description)

    Returns:
        Tuple of (matched_keywords, missing_keywords, overlap_percentage)
    """
    def norm(value: str) -> str:
        text = value.lower().strip()
        aliases = {
            "js": "javascript",
            "node": "node.js",
            "nodejs": "node.js",
            "postgres": "postgresql",
            "k8s": "kubernetes",
            "g suite": "google workspace",
            "m365": "microsoft 365",
            "o365": "office 365",
            "ad": "active directory",
            "powerbi": "power bi",
            "ci cd": "ci/cd",
        }
        text = re.sub(r"[^a-z0-9+#./]+", " ", text).strip()
        return aliases.get(text, text)

    set1 = {norm(k) for k in keywords1 if str(k).strip()}
    set2 = {norm(k) for k in keywords2 if str(k).strip()}

    matched = sorted(set1 & set2)
    missing = sorted(set2 - set1)

    overlap_pct = (len(matched) / len(set2) * 100) if set2 else 0.0

    return matched, missing, round(overlap_pct, 1)


def truncate_text(text: str, max_chars: int = 4000) -> str:
    """Truncate text to fit within LLM context window limits.

    Preserves complete sentences where possible.

    Args:
        text: Text to truncate
        max_chars: Maximum character count

    Returns:
        Truncated text
    """
    if len(text) <= max_chars:
        return text

    # Try to break at last sentence boundary before limit
    truncated = text[:max_chars]
    last_period = truncated.rfind(".")
    if last_period > max_chars * 0.7:
        return truncated[:last_period + 1]

    return truncated + "..."
