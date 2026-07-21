"""Quick live test of the OpenAI integration."""
import sys
sys.path.insert(0, '.')
from unittest.mock import MagicMock
from uuid import uuid4
from app.config import get_settings
from app.services.rag import generate_explanation, _explanation_cache
from app.services.recommendation import MatchBreakdown

_explanation_cache.clear()

profile = MagicMock()
profile.user_id = uuid4()
profile.headline = 'Senior Python Developer'
profile.skills = ['python', 'fastapi', 'postgresql']
profile.experience_level = 'senior'
profile.experience_years = 6
profile.preferred_locations = ['London', 'Remote']
profile.min_salary = 60000
profile.salary_currency = 'GBP'

job = MagicMock()
job.id = uuid4()
job.title = 'Senior Backend Engineer'
job.title_clean = 'senior backend engineer'
job.company = 'Test Corp'
job.location_city = 'London'
job.location_country = 'UK'
job.remote = False
job.salary_min = 70000
job.salary_max = 90000
job.salary_currency = 'GBP'
job.category = 'Engineering'

bd = MatchBreakdown(match_percentage=85, semantic_similarity=0.82, skill_overlap=0.75,
    matching_skills=['python', 'fastapi'], missing_skills=['aws'],
    location_fit=1.0, salary_fit=1.0, experience_fit=1.0)

s = get_settings()
print(f'Model: {s.openai_model}')
print(f'Key set: {"***" if s.openai_api_key else "NO"}')

result = generate_explanation(profile, job, bd, validate=False)
print(f'\nExplanation: {result}\n')
print('LIVE API TEST: PASSED')
