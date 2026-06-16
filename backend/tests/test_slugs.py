from app.services.slugs import slugify_unique


class TestSlugifyUnique:
    def test_basic_slug(self):
        assert slugify_unique("Were you the Driver?", []) == "were-you-the-driver"

    def test_appends_suffix_on_collision(self):
        assert slugify_unique("Driver", ["driver"]) == "driver-2"

    def test_increments_until_free(self):
        assert slugify_unique("Driver", ["driver", "driver-2", "driver-3"]) == "driver-4"

    def test_empty_text_falls_back_to_item(self):
        assert slugify_unique("!!!", []) == "item"
