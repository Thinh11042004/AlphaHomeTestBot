from app.utils.slug import slugify, unique_slug


def test_slugify_ascii_and_lowercase():
    assert slugify("How to Add a YouTube Video?") == "how-to-add-a-youtube-video"


def test_unique_slug_adds_id_on_collision():
    seen = set()
    assert unique_slug("Same", "1", seen) == "same"
    assert unique_slug("Same", "2", seen) == "same-2"
