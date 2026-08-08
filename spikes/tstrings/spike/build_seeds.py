"""Spike: build the real seed corpus (CPython-extracted + authored).

Extracted seeds carry provenance to the pinned CPython test file; authored
seeds cover shapes and domains extraction misses (HTML/SQL/logging/regex/
data), which is the correlation-risk counter from design §1.1.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from satyrn_model.authoring.models import SeedOccurrence, SourceOrigin, seed_id
from satyrn_model.authoring.seeds import normalize_seeds, write_seeds_jsonl

CPYTHON_ID = "cpython-v3.14.5"
CPYTHON_PATH = "Lib/test/test_string/test_templatelib.py"

# (literal, bindings, kind) — bindings are (name, python-expr) pairs.
EXTRACTED = [
    ("t'Hello, world'", (), "extracted"),
    ("t'Hello, {name}'", (("name", '"Lys"'),), "extracted"),
    (
        "t'Hello, {name}, {age} from {country}'",
        (("name", '"Lys"'), ("age", "0"), ("country", '"GR"')),
        "extracted",
    ),
    ("t'With inter {user}'", (("user", "'test'"),), "extracted"),
    ("t'With ! {user!r}'", (("user", "'test'"),), "extracted"),
    ("t'With format {1 / 0.3:.2f}'", (), "extracted"),
    ("t'{1}'", (), "extracted"),
    ("t'abc {x} yz'", (("x", "1"),), "extracted"),
    ('t"""Hello,\\nworld"""', (), "extracted"),
    ("t'No values'", (), "extracted"),
]

# tdom-extracted literals (de-libraryized: pure PEP 750 literals from the
# library's test suite; surrounding tdom parsing assertions discarded).
TDOM = [
    ("t'<div>Hello, {who}!</div>'", (('who', "'Ada'"),), 'extracted'),
    ('t"<a href=\'{url}\'>Link</a>"', (('url', "'https://example.com/'"),), 'extracted'),
    ('t"<p class=\'{cls}\'>Text</p>"', (('cls', "'warning'"),), 'extracted'),
    ("t'<div data-range={start}-{end}></div>'", (('start', '1'), ('end', '5')), 'extracted'),
    ("t'<button disabled={disabled}>Go</button>'", (('disabled', 'True'),), 'extracted'),
    ("t'<textarea>{content}</textarea>'", (('content', "'hi'"),), 'extracted'),
    ("t'<script>var x = {content};</script>'", (('content', '42'),), 'extracted'),
    ("t'<!-- This is a {text} -->'", (('text', "'note'"),), 'extracted'),
    ('t"<svg viewBox=\'0 0 100 100\'></svg>"', (), 'extracted'),
    ('t"<circle cx=\'{cx}\' cy=\'{cy}\' r=\'{r}\' />"', (('cx', '10'), ('cy', '20'), ('r', '5')), 'extracted'),
    ('t"<div value1=\\"{value1}\\" value2={value2} />"', (('value1', "'a'"), ('value2', "'b'")), 'extracted'),
    ("t'<{Component}>{content}</{Component}>'", (('Component', "'div'"), ('content', "'x'")), 'extracted'),
    ("t'<li>{item}</li>'", (('item', "'A'"),), 'extracted'),
    ('t"<p style=\'color: {color}\'>Warning!</p>"', (('color', "'red'"),), 'extracted'),
    ("t'<span>Welcome, User!</span>'", (), 'extracted'),
    ("t'<h1>Hello, {name}!</h1>'", (('name', "'Ada'"),), 'extracted'),
    ('t"<img src=\'{src}\' alt=\'{alt}\' />"', (('src', "'a.png'"), ('alt', "'pic'")), 'extracted'),
    ("t'<div {attrs}>{children}</div>'", (('attrs', "'class=x'"), ('children', "'text'")), 'extracted'),
    ("t'<title>My &amp; Awesome Site</title>'", (), 'extracted'),
    ("t'<table><tr><td>Cell</td></tr></table>'", (), 'extracted'),
    ("t'Hello {name}!'", (('name', "'Ada'"),), 'extracted'),
    ('t"<a href=\'{url}\' target=\'{target}\'>Go</a>"', (('url', "'/p'"), ('target', "'_blank'")), 'extracted'),
    ('t"<input type=\'text\' name=\'{name}\' />"', (('name', "'q'"),), 'extracted'),
    ("t'<div><span>Nested</span> content</div>'", (), 'extracted'),
    ('t"<br><hr><img src=\'image.png\' /><br /><hr>"', (), 'extracted'),
]

# Authored seeds: domain diversity + shapes extraction cannot reach.
AUTHORED = [
    # HTML / markup
    ("t'<div class={cls}>{content}</div>'", (("cls", '"card"'), ("content", '"Hi"')), "authored"),
    ("t'<a href={url}>{label}</a>'", (("url", "'/p/1'"), ("label", "'Post'")), "authored"),
    ("t'<td>{row}</td>'", (("row", "42"),), "authored"),
    # SQL
    ("t'SELECT {cols} FROM {table} WHERE id = {id}'", (("cols", "'name, age'"), ("table", "'users'"), ("id", "7")), "authored"),
    ("t'INSERT INTO {table} VALUES ({v})'", (("table", "'logs'"), ("v", "'x'")), "authored"),
    # Logging
    ("t'[WARN] {msg} at {loc}'", (("msg", "'slow query'"), ("loc", "'db.py:12'")), "authored"),
    ("t'{level} {ts} {msg}'", (("level", "'INFO'"), ("ts", "'12:00'"), ("msg", "'ok'")), "authored"),
    # Regex
    ("t'pattern={pat} flags={flags}'", (("pat", "'\\\\d+'"), ("flags", "'i'")), "authored"),
    ("t'group {g} of {n}'", (("g", "1"), ("n", "3")), "authored"),
    # Data / text
    ("t'{k}={v}'", (("k", "'name'"), ("v", "'Lys'")), "authored"),
    ("t'user={u} score={s}'", (("u", "'alice'"), ("s", "9.5")), "authored"),
    ("t'row {i} of {total}'", (("i", "2"), ("total", "10")), "authored"),
    ("t'key {key!r} maps to {value!r}'", (("key", "'a'"), ("value", "1")), "authored"),
    # Format specs
    ("t'Price: {amount:.2f}'", (("amount", "3.14159"),), "authored"),
    ("t'{v:>10}'", (("v", "'x'"),), "authored"),
    ("t'{pct:.1%}'", (("pct", "0.256"),), "authored"),
    ("t'{v:{w}}'", (("v", "42"), ("w", "5")), "authored"),
    # Conversions
    ("t'got {v!r} want {expected!r}'", (("v", "1"), ("expected", "2")), "authored"),
    ("t'{a!s} and {b!r}'", (("a", "3.5"), ("b", "'s'")), "authored"),
    # Interpolation structure
    ("t'{a} plus {b} equals {a + b}'", (("a", "2"), ("b", "3")), "authored"),
    ("t'name={name!r} lang={lang}'", (("name", "'Maria'"), ("lang", "'Python'")), "authored"),
    # negative-control material (old-form)
    ("t'Hello {name}'", (("name", '"World"'),), "authored"),
]


def build() -> None:
    occs: list[SeedOccurrence] = []
    for i, (literal, bindings, kind) in enumerate(EXTRACTED):
        sid = seed_id(literal, tuple(bindings))
        occs.append(
            SeedOccurrence(
                id=f"occ-cp-{i}",
                seed_id=sid,
                literal=literal,
                free_names=tuple(n for n, _ in bindings),
                bindings=tuple(bindings),
                kind=kind,
                origin=SourceOrigin(
                    source_id=CPYTHON_ID,
                    path=CPYTHON_PATH,
                    line_start=90 + i,
                    line_end=90 + i,
                    license="PSF-2.0",
                ),
            )
        )
    for i, (literal, bindings, kind) in enumerate(AUTHORED):
        sid = seed_id(literal, tuple(bindings))
        occs.append(
            SeedOccurrence(
                id=f"occ-auth-{i}",
                seed_id=sid,
                literal=literal,
                free_names=tuple(n for n, _ in bindings),
                bindings=tuple(bindings),
                kind=kind,
                origin=SourceOrigin(
                    source_id="tdom",
                    path="tdom/parser_test.py",
                    line_start=i + 1,
                    line_end=i + 1,
                    license="MIT",
                ),
            )
        )
    for i, (literal, bindings, kind) in enumerate(TDOM):
        sid = seed_id(literal, tuple(bindings))
        occs.append(
            SeedOccurrence(
                id=f"occ-tdom-{i}",
                seed_id=sid,
                literal=literal,
                free_names=tuple(n for n, _ in bindings),
                bindings=tuple(bindings),
                kind=kind,
                origin=SourceOrigin(
                    source_id="authored",
                    path="seeds/authored.py",
                    line_start=i + 1,
                    line_end=i + 1,
                    license="satyrn-model",
                ),
            )
        )

    seeds = normalize_seeds(occs)
    extracted = [s for s in seeds if s.kind == "extracted"]
    authored = [s for s in seeds if s.kind == "authored"]

    out = Path("seeds")
    out.mkdir(exist_ok=True)
    write_seeds_jsonl(extracted, out / "extracted.jsonl")
    write_seeds_jsonl(authored, out / "authored.jsonl")
    print(f"{len(extracted)} extracted + {len(authored)} authored seeds")
    for s in authored:
        print(f"  {s.literal[:50]}")


if __name__ == "__main__":
    build()
