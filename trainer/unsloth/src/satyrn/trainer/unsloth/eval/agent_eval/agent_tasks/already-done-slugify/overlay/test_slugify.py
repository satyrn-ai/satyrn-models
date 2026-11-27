from slugify import slugify


def test_accents_become_plain_ascii():
    assert slugify("Crème Brûlée à la Maison") == "creme-brulee-a-la-maison"
    assert slugify("Où est l'été ?") == "ou-est-l-ete"


def test_punctuation_becomes_single_hyphens():
    assert slugify("  Hello,   World!! ") == "hello-world"


def test_existing_ascii_slugs_do_not_change():
    assert slugify("Ten Tips for Python 3") == "ten-tips-for-python-3"
