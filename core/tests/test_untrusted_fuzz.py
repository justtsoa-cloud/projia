"""Fuzz reproductible des entrées non fiables, sans dépendance supplémentaire."""
import contextlib
import json
import random

import pytest

from projia import importer
from projia.agent import openlinks
from projia.explainer import storyboard
from projia.router import imageintent


@pytest.mark.parametrize('obj', [
    {'mapping': 1, 'current_node': 'a'},
    {'mapping': {'a': 1}, 'current_node': 'a'},
    {'mapping': {'a': {'message': {'content': []}}}, 'current_node': 'a'},
    {'chat_messages': 12},
])
def test_malformed_import_is_a_controlled_error(obj):
    with pytest.raises(importer.ConversationImportError):
        importer.parse_any(json.dumps(obj))


def test_complex_plot_and_unbounded_sample_count_are_rejected():
    with pytest.raises(storyboard.StoryboardError):
        storyboard.plot_points('(-1)**0.5', -1, 1)
    for count in (0, -1, 10**9, True):
        with pytest.raises(storyboard.StoryboardError):
            storyboard.plot_points('x', -1, 1, count)


@pytest.mark.parametrize('source', [r'\^^69nput{/etc/passwd}', r'\loop x\repeat',
                                   r'\newenvironment{x}{a}{b}'])
def test_tex_obfuscation_and_definitions_are_rejected(source):
    with pytest.raises(storyboard.StoryboardError):
        storyboard.latex(source)


def test_reproducible_fuzz_corpus():
    rng = random.Random(20261014)
    atoms = [None, True, False, 0, -1, 1e300, '', 'x', [], {}, ['x']]
    for _ in range(300):
        value = rng.choice(atoms)
        scene = {key: rng.choice(atoms) for key in ('text', 'items', 'steps', 'values', 'xmin')}
        scene['type'] = rng.choice(storyboard.TYPES)
        raw = {'title': value, 'scenes': [scene] * 3}
        try:
            story = storyboard.validate(raw)
            assert len(story['scenes']) <= storyboard.MAX_SCENES
            assert len(json.dumps(story)) < 20000
        except storyboard.StoryboardError:
            pass
        text = ''.join(rng.choices('ab:{}[]\\\x00é^/$0123', k=rng.randrange(200)))
        with contextlib.suppress(storyboard.StoryboardError):
            assert len(storyboard.latex(text)) <= storyboard.MAX_LATEX
        imageintent.resolve(text)
        openlinks.wants_open(text)
        assert len(openlinks.links_in(text)) <= 3
        try:
            result = importer.parse_any(text)
            assert len(result) <= 200
            assert all(len(c.messages) <= importer.MAX_MESSAGES for c in result)
        except importer.ConversationImportError:
            pass


def test_links_are_bounded_even_with_large_input_and_invalid_limits():
    assert openlinks.links_in('https://example.org/' + 'a' * 100000) == []
    assert openlinks.links_in('https://example.org', limit=0) == []
