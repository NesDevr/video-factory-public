from PIL import Image

from core.utils import meets_minimum_source_size, minimum_source_size
from core.utils import Script, ScriptSection, VisualSlot, load_channel_config
from core.validator import validate_raw_images, validate_ready_images


def _script_with_image_slot() -> Script:
    return Script(
        title="Test",
        video_type="listicle",
        sections=[
            ScriptSection(
                id=1,
                narration="A test section that needs a real sourced image.",
                slots=[
                    VisualSlot(
                        visual="google_photo",
                        keywords="Cleveland Clinic hospital exterior",
                    )
                ],
            )
        ],
    )


def _script_with_component_slot(visual: str) -> Script:
    return Script(
        title="Test",
        video_type="listicle",
        sections=[
            ScriptSection(
                id=1,
                narration="A test section with a Remotion component slot.",
                slots=[
                    VisualSlot(
                        visual=visual,
                        prompt="Illustration prompt",
                        props={"title": "Component", "text": "Specific instruction"},
                    )
                ],
            )
        ],
    )


def test_minimum_source_size_for_1080p_render():
    assert minimum_source_size((1920, 1080)) == (1280, 720)
    assert meets_minimum_source_size(1280, 720, (1920, 1080))
    assert not meets_minimum_source_size(382, 215, (1920, 1080))


def test_validate_raw_images_rejects_tiny_source(tmp_path):
    raw_dir = tmp_path / "images" / "raw"
    raw_dir.mkdir(parents=True)
    Image.new("RGB", (382, 215)).save(raw_dir / "section_001_01.jpg")

    config = load_channel_config("demo_channel")
    errors = validate_raw_images(tmp_path, _script_with_image_slot(), config)

    assert len(errors) == 1
    assert "section_001_01.jpg is 382x215" in errors[0]
    assert "minimum 1280x720" in errors[0]


def test_validate_raw_images_accepts_720p_source(tmp_path):
    raw_dir = tmp_path / "images" / "raw"
    raw_dir.mkdir(parents=True)
    Image.new("RGB", (1280, 720)).save(raw_dir / "section_001_01.jpg")

    config = load_channel_config("demo_channel")
    errors = validate_raw_images(tmp_path, _script_with_image_slot(), config)

    assert errors == []


def test_validate_raw_images_requires_info_slide_even_when_illustrations_disabled(tmp_path):
    config = load_channel_config(
        "demo_channel",
        overrides=["image_sourcing.generate_info_slide_illustrations=false"],
    )

    errors = validate_raw_images(
        tmp_path,
        _script_with_component_slot("info_slide"),
        config,
    )

    assert len(errors) == 1
    assert "section_001_01" in errors[0]


def test_validate_ready_images_requires_info_slide_when_enabled_by_channel(tmp_path):
    config = load_channel_config("demo_channel")

    errors = validate_ready_images(
        tmp_path,
        _script_with_component_slot("info_slide"),
        config,
    )

    assert len(errors) == 1
    assert "section_001_01.png" in errors[0]


def test_validate_ready_images_requires_info_slide_even_when_illustrations_disabled(tmp_path):
    config = load_channel_config(
        "demo_channel",
        overrides=["image_sourcing.generate_info_slide_illustrations=false"],
    )

    errors = validate_ready_images(
        tmp_path,
        _script_with_component_slot("info_slide"),
        config,
    )

    assert len(errors) == 1
    assert "section_001_01.png" in errors[0]


def test_validate_ready_images_requires_enabled_info_card_illustrations(tmp_path):
    config = load_channel_config("demo_channel")

    errors = validate_ready_images(
        tmp_path,
        _script_with_component_slot("info_card"),
        config,
    )

    assert errors == ["Missing ready image(s): section_001_01.png"]
