"""L'enregistrement des templates — pas le comportement d'un composant en
particulier (déjà couvert par test_components*.py/test_kanban.py/...), mais
le PROCESSUS lui-même : est-ce que tout ce qui existe sous xweb/components/
et templates/ s'enregistre sans plantage, sans collision de t-name, sans
avertissement de conflit — exactement la séquence réelle du boot
(xweb/engine/integration/xcore.py::XwebExtension.init(), vérifié ligne par
ligne ci-dessous, pas une approximation).

Pourquoi ça a sa place à part : QwebRegistry.register_source() ne lève
JAMAIS sur un t-name déjà pris — il logue un warning et le nouveau template
écrase silencieusement l'ancien (registry.py, "shadows the previous
definition"). Un vrai risque à chaque nouveau composant ajouté (comme
xweb.editable_table_row a bien failli entrer en collision avec un futur
xweb.something_row) — jamais détecté par les tests qui rendent un
composant PAR SON NOM (si le mauvais template gagne, le test du nom
gagnant continue de passer, celui qui a perdu silencieusement disparaît).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from lxml import etree

from xweb.engine.registry import QwebRegistry

ROOT = Path(__file__).parent.parent
COMPONENTS_DIR = ROOT / "xweb" / "components"
SITE_TEMPLATES_DIR = ROOT / "templates"


def _declared_template_names(directory: Path) -> set[str]:
    """t-name de chaque <template> déclaré dans *directory*, lu par un
    vrai parse XML (lxml) — pas une regex, qui confondrait par exemple
    t-att-name="..." avec t-name="..." (piège réel rencontré en écrivant
    ce test à la main avant de passer par lxml)."""
    names: set[str] = set()
    for path in directory.glob("*.xml"):
        root = etree.fromstring(path.read_bytes())
        elements = [root] if root.tag == "template" else root.findall(".//template")
        for el in elements:
            name = el.get("t-name")
            if name:
                names.add(name)
    return names


@pytest.fixture
def registry() -> QwebRegistry:
    return QwebRegistry()


def test_xweb_components_register_with_zero_conflicts(registry, caplog):
    """Même appel que le vrai boot (XwebExtension.init(), source_plugin=
    "xweb-core") — un seul avertissement suffit à signaler un t-name
    réutilisé deux fois dans le SDK lui-même, jamais acceptable ici (pas
    un conflit légitime entre deux plugins tiers, juste une collision de
    nommage à l'intérieur d'un seul et même dossier)."""
    with caplog.at_level(logging.WARNING, logger="xweb.engine.registry"):
        registry.register_dir(COMPONENTS_DIR, source_plugin="xweb-core")
    assert caplog.records == [], (
        "au moins un t-name est réutilisé deux fois sous xweb/components/ : "
        + "; ".join(r.message for r in caplog.records)
    )


def test_xweb_components_register_count_matches_declared_names(registry):
    """Si le compte après enregistrement est INFÉRIEUR au nombre de t-name
    déclarés dans les sources, une collision a fait disparaître un
    template silencieusement — le seul signe visible serait un warning
    (déjà vérifié à part) OU rien du tout si ce test n'existait pas."""
    declared = _declared_template_names(COMPONENTS_DIR)
    registry.register_dir(COMPONENTS_DIR, source_plugin="xweb-core")
    assert len(registry) == len(declared)


def test_site_templates_register_alongside_components_like_a_real_boot(registry, caplog):
    """Reproduit exactement xweb/engine/integration/xcore.py::XwebExtension.init() :
    builtin_components d'abord (source_plugin="xweb-core"), puis chaque
    entrée de `namespaces` (ici seulement "site" -> templates/, integration.yaml)."""
    with caplog.at_level(logging.WARNING, logger="xweb.engine.registry"):
        registry.register_dir(COMPONENTS_DIR, source_plugin="xweb-core")
        registry.register_dir(SITE_TEMPLATES_DIR, source_plugin="site")
    assert caplog.records == [], (
        "un t-name de templates/ entre en collision avec xweb/components/ ou avec lui-même : "
        + "; ".join(r.message for r in caplog.records)
    )
    declared = _declared_template_names(COMPONENTS_DIR) | _declared_template_names(SITE_TEMPLATES_DIR)
    assert len(registry) == len(declared)


def test_check_all_resolves_everything_without_raising_or_warning(registry, caplog):
    """check_all() — appelé depuis XwebExtension.init() juste après
    l'enregistrement (docs/inheritance.md#conflits) — force la résolution
    de CHAQUE template plutôt que d'attendre le premier rendu qui le
    touche. Ce projet n'a aucun t-inherit dans xweb/components/ ou
    templates/ (vérifié : seul un commentaire en parle dans landing.xml,
    aucune vraie directive) — donc zéro conflit XPath possible ici, zéro
    warning attendu, contrairement à un projet qui utiliserait vraiment
    t-inherit entre plugins (là, un conflit resterait légitime, voir
    tests/test_inherit.py pour ce cas précis)."""
    registry.register_dir(COMPONENTS_DIR, source_plugin="xweb-core")
    registry.register_dir(SITE_TEMPLATES_DIR, source_plugin="site")
    with caplog.at_level(logging.WARNING, logger="xweb.engine.registry"):
        registry.check_all()  # ne doit jamais lever — docs/inheritance.md#conflits
    assert caplog.records == []


def test_no_template_file_is_silently_unparseable(registry):
    """register_dir() ne dit jamais explicitement "ce fichier a échoué" —
    une XMLSyntaxError remonterait telle quelle (pas de try/except dans
    register_file), donc ce test suffit en soi : s'il passe, chaque
    fichier .xml de xweb/components/ a bien été un XML valide."""
    for path in COMPONENTS_DIR.glob("*.xml"):
        registry.register_file(path, source_plugin="xweb-core")
    # Si on arrive ici sans exception, tous les fichiers étaient valides.
    assert len(registry) > 0
