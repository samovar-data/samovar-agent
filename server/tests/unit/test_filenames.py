from samovar_agent.service.filenames import ascii_slug, output_name


def test_names_are_short_latin_slugs_with_the_query_id() -> None:
    assert output_name("Визиты по источникам", "36e30c75a0c5", "chart") == "vizity-po-istochnikam-36e30c75"
    assert output_name("Объём, съезд!", "abcdef123", "x") == "obem-sezd-abcdef12"


def test_titles_without_letters_fall_back() -> None:
    assert ascii_slug("??? ", "export") == "export"
    assert len(ascii_slug("очень " * 40, "x")) <= 40
