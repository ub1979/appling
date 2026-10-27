"""Project checker edits survive kit refreshes; untouched copies still upgrade."""

import pytest

from lyra_lite import templates


@pytest.fixture
def checkers(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for key, name in (("SITE_CHECK", "site-check.mjs"), ("DECK_CHECK", "deck-check.mjs")):
        path = bundle / name
        path.write_bytes(b"bundled checker v1\n")
        monkeypatch.setattr(templates, key, path)
    root = tmp_path / "project"
    return root, root / templates.KIT_DIR


def test_untouched_checkers_upgrade_but_custom_checkers_survive(checkers):
    root, kit = checkers
    templates.ensure_website_kit(root, None)
    site, deck = kit / "site-check.mjs", kit / "deck-check.mjs"
    assert site.read_bytes() == deck.read_bytes() == b"bundled checker v1\n"
    site.write_bytes(b"project authentication checks\n")
    templates.SITE_CHECK.write_bytes(b"bundled checker v2\n")
    templates.DECK_CHECK.write_bytes(b"bundled checker v2\n")
    for _ in range(2):
        templates.ensure_website_kit(root, None)
        assert site.read_bytes() == b"project authentication checks\n"
        assert deck.read_bytes() == b"bundled checker v2\n"
    deck.unlink()
    templates.ensure_website_kit(root, None)
    assert deck.read_bytes() == b"bundled checker v2\n"
    assert site.read_bytes() == b"project authentication checks\n"


@pytest.mark.parametrize("manifest", [None, "invalid json", "[]"])
def test_legacy_or_unreadable_tracking_preserves_unknown_checkers(checkers, manifest):
    root, kit = checkers
    kit.mkdir(parents=True)
    (kit / "site-check.mjs").write_bytes(b"legacy customized checker\n")
    (kit / "deck-check.mjs").write_bytes(b"bundled checker v1\n")
    if manifest is not None:
        (kit.parent / "kit-checksums.json").write_text(manifest)
    templates.ensure_website_kit(root, None)
    templates.SITE_CHECK.write_bytes(b"bundled checker v2\n")
    templates.DECK_CHECK.write_bytes(b"bundled checker v2\n")
    templates.ensure_website_kit(root, None)
    assert (kit / "site-check.mjs").read_bytes() == b"legacy customized checker\n"
    assert (kit / "deck-check.mjs").read_bytes() == b"bundled checker v2\n"


def test_project_checker_symlink_is_not_overwritten(checkers, tmp_path):
    root, kit = checkers
    kit.mkdir(parents=True)
    target = tmp_path / "custom-checker"
    target.write_bytes(b"external customized checker\n")
    (kit / "site-check.mjs").symlink_to(target)
    templates.ensure_website_kit(root, None)
    assert target.read_bytes() == b"external customized checker\n"
    assert (kit / "site-check.mjs").is_symlink()
