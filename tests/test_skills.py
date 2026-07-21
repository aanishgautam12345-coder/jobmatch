"""Tests for skills extraction (Phase 2)."""

import pytest
from app.processing.skills import (
    extract_skills,
    extract_skills_detailed,
    SkillDictionary,
    SKILL_DICT,
    ALL_SKILLS,
)


class TestExtractSkills:
    def test_exact_match(self):
        result = extract_skills("Python, JavaScript, React")
        assert isinstance(result, list)
        assert "python" in result
        assert "javascript" in result
        assert "react" in result

    def test_case_insensitive(self):
        result = extract_skills("PYTHON and Javascript")
        assert "python" in result

    def test_no_skills(self):
        result = extract_skills("No relevant skills mentioned here")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_empty(self):
        result = extract_skills("")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_strings(self):
        result = extract_skills("Python")
        assert all(isinstance(s, str) for s in result)


class TestExtractSkillsDetailed:
    def test_returns_extracted_skill_objects(self):
        result = extract_skills_detailed("Python")
        assert len(result) > 0
        skill = result[0]
        assert hasattr(skill, "name")
        assert hasattr(skill, "confidence")
        assert hasattr(skill, "classification")
        assert hasattr(skill, "provenance")

    def test_essential_classification(self):
        result = extract_skills_detailed("Must have Python experience")
        for skill in result:
            if skill.name == "python":
                assert skill.classification in ("required", "preferred", "desirable", "mentioned")

    def test_confidence_scored(self):
        result = extract_skills_detailed("Python")
        for skill in result:
            assert 0 <= skill.confidence <= 1


class TestSkillDictionary:
    def test_all_skills_non_empty(self):
        assert len(ALL_SKILLS) > 0

    def test_all_skills_returns_set(self):
        assert isinstance(ALL_SKILLS, set)

    def test_python_in_all_skills(self):
        assert "python" in ALL_SKILLS

    def test_skill_dict_has_domains(self):
        assert isinstance(SKILL_DICT.domains, dict)
        assert len(SKILL_DICT.domains) > 0

    def test_all_skills_method(self):
        d = SkillDictionary()
        skills = d.all_skills()
        assert isinstance(skills, set)
        assert len(skills) > 0
