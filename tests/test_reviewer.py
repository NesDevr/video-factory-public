"""Tests for shared AI review gate behavior."""

import asyncio

import pytest

from core import reviewer


def test_review_gate_returns_approved_result(monkeypatch):
    async def approve(*args, **kwargs):
        return {"approved": True, "scores": {"overall": 9}}

    monkeypatch.setattr(reviewer.clients, "generate_json", approve)

    result = asyncio.run(
        reviewer.review_gate(
            content={"draft": "ok"},
            review_prompt_fn=lambda content: f"review {content['draft']}",
            system_instruction="system",
            max_attempts=1,
            gate_name="script_review",
        )
    )

    assert result["approved"] is True
    assert result["flagged_for_review"] is False
    assert result["attempts"] == 1
    assert result["scores"] == {"overall": 9}


def test_review_gate_raises_after_max_attempts(monkeypatch):
    async def reject(*args, **kwargs):
        return {"approved": False, "feedback": "wrong exercise image"}

    monkeypatch.setattr(reviewer.clients, "generate_json", reject)

    with pytest.raises(reviewer.ReviewGateError) as exc_info:
        asyncio.run(
            reviewer.review_gate(
                content={"draft": "bad"},
                review_prompt_fn=lambda content: f"review {content['draft']}",
                system_instruction="system",
                max_attempts=2,
                gate_name="image_review",
            )
        )

    result = exc_info.value.result
    assert exc_info.value.gate_name == "image_review"
    assert result["approved"] is False
    assert result["flagged_for_review"] is True
    assert result["attempts"] == 2
    assert result["feedback"] == "wrong exercise image"
    assert len(result["review_history"]) == 2


def test_review_gate_regenerates_raw_list_error_results(monkeypatch, tmp_path):
    calls = {"review": 0}
    regenerated_feedback = None

    async def review_with_vision(*args, **kwargs):
        calls["review"] += 1
        if calls["review"] == 1:
            return [
                {
                    "section_id": 2,
                    "sub_image_index": 1,
                    "severity": "error",
                    "suggestion": "Use a seated knee extension exercise image",
                }
            ]
        return {"approved": True, "feedback": "fixed"}

    async def regenerate(content, feedback):
        nonlocal regenerated_feedback
        regenerated_feedback = feedback
        return content

    monkeypatch.setattr(reviewer.clients, "review_with_vision", review_with_vision)

    image_path = tmp_path / "section_002_01.jpg"
    image_path.write_bytes(b"not used by monkeypatch")

    result = asyncio.run(
        reviewer.review_gate(
            content={"draft": "images"},
            review_prompt_fn=lambda content: "review images",
            system_instruction="system",
            regenerate_fn=regenerate,
            max_attempts=2,
            gate_name="image_review",
            image_paths=[image_path],
        )
    )

    assert result["approved"] is True
    assert calls["review"] == 2
    assert regenerated_feedback["approved"] is False
    assert regenerated_feedback["image_results"][0]["approved"] is False
    assert regenerated_feedback["image_results"][0]["severity"] == "error"


def test_review_gate_reviews_text_only_retry_when_no_images_remain(monkeypatch, tmp_path):
    calls = {"vision": 0, "json": 0}

    async def review_with_vision(*args, **kwargs):
        calls["vision"] += 1
        return {
            "approved": False,
            "feedback": "retry required",
        }

    async def generate_json(*args, **kwargs):
        calls["json"] += 1
        return {
            "approved": False,
            "feedback": "text-only slide still leaks internal instructions",
        }

    monkeypatch.setattr(reviewer.clients, "review_with_vision", review_with_vision)
    monkeypatch.setattr(reviewer.clients, "generate_json", generate_json)

    image_path = tmp_path / "section_001_01.jpg"
    image_path.write_bytes(b"not used")
    image_paths = [image_path]

    async def regenerate_and_clear(content, feedback):
        image_paths.clear()
        return content

    with pytest.raises(reviewer.ReviewGateError) as exc_info:
        asyncio.run(
            reviewer.review_gate(
                content={"draft": "images"},
                review_prompt_fn=lambda content: "review images",
                system_instruction="system",
                regenerate_fn=regenerate_and_clear,
                max_attempts=2,
                gate_name="image_review",
                image_paths=image_paths,
            )
        )

    result = exc_info.value.result
    assert result["approved"] is False
    assert result["attempts"] == 2
    assert calls == {"vision": 1, "json": 1}
    assert result["feedback"] == "text-only slide still leaks internal instructions"
