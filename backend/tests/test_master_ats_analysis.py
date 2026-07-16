from ats_model_service.service import _json_object, _normalize
from app.workers.master_ats_analysis import _description_hash


def test_model_output_is_bounded_and_normalized():
    result = _normalize({
        "summary": "  Build secure systems.  ",
        "required_skills": ["Python", "python", "AWS"],
        "preferred_skills": "not-a-list",
        "keywords": ["Cloud Security"],
        "responsibilities": ["Investigate alerts"],
        "min_experience_years": "8",
        "seniority": "SENIOR",
        "education": [],
        "certifications": ["CISSP"],
        "work_authorization": ["Must be authorized to work in the US"],
    })
    assert result["summary"] == "Build secure systems."
    assert result["required_skills"] == ["Python", "AWS"]
    assert result["preferred_skills"] == []
    assert result["min_experience_years"] == 8
    assert result["seniority"] == "senior"


def test_json_object_accepts_fenced_model_output():
    assert _json_object('```json\n{"summary":"ok"}\n```')["summary"] == "ok"


def test_description_hash_is_stable_change_detector():
    assert _description_hash("same") == _description_hash("same")
    assert _description_hash("same") != _description_hash("changed")
