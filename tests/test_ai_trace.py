import json
from datetime import datetime

import clients as ai_trace
from core import costs


def test_ai_trace_writes_json_and_embedded_report_data(tmp_path):
    costs.initialize_cost_tracking(
        workspace=tmp_path,
        run_id="vf_test_1234",
        channel="demo_channel",
    )
    try:
        with costs.bound_context(stage="script"):
            trace_ref = ai_trace.reserve_trace(
                operation="script_generate",
                service="generate_content",
                model="gemini-test-model",
            )
            assert trace_ref is not None

            payload = ai_trace.base_payload(
                trace_ref,
                started_at=datetime(2026, 4, 16, 12, 0, 0),
                duration_seconds=2.345,
                status="ok",
            )
            payload["request"] = {
                "system_instruction": "You are a scriptwriter.",
                "prompt": "Write a 60-second script about circulation.",
                "response_mime_type": "application/json",
            }
            payload["response"] = {
                "text": '{"title":"Test"}',
                "json": {"title": "Test"},
                "prompt_token_count": 123,
                "output_token_count": 45,
            }

            ai_trace.write_trace(trace_ref, payload)

        assert trace_ref.json_path.name == "ai_trace_report.json"
        assert trace_ref.html_rel_path == "pipeline.html#0001_script_generate"
        assert trace_ref.json_path.exists()

        report_json = json.loads(trace_ref.json_path.read_text(encoding="utf-8"))
        assert report_json["run_id"] == "vf_test_1234"
        assert len(report_json["traces"]) == 1
        trace_json = report_json["traces"][0]
        embedded_html = ai_trace.render_embedded_html(report_json)

        assert trace_json["trace_id"] == trace_ref.trace_id
        assert trace_json["request"]["prompt"] == "Write a 60-second script about circulation."
        assert trace_json["response"]["json"] == {"title": "Test"}
        assert 'id="0001_script_generate"' in embedded_html
        assert "You are a scriptwriter." in embedded_html
        assert "Write a 60-second script about circulation." in embedded_html
        assert "&quot;title&quot;: &quot;Test&quot;" in embedded_html
    finally:
        costs.shutdown_cost_tracking()
