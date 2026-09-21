"""Corpus XSS serveur — vérifie que les payloads malveillants sont neutralisés
par l'échappement dans les différents sinks QWeb (t-esc, t-att, t-attf, t-out).

Chaque payload est passé via le contexte à un template qui l'injecte dans
un sink précis. On vérifie que la structure HTML résultante est inchangée
(aucun élément/attribut supplémentaire créé) et que la valeur injectée
correspond au payload original (l'échappement rend le texte inerte).

t-out est intentionnellement NON échappé (source de confiance uniquement) —
le test documente ce comportement.
"""

import textwrap

import pytest
from lxml import etree

from xweb.engine.registry import QwebRegistry

# Payloads XSS classiques + variantes
XSS_PAYLOADS = [
    # Injection de balise script
    "<script>alert(1)</script>",
    # Injection img onerror
    "<img src=x onerror=alert(1)>",
    # Sortie d'attribut + injection script
    '"><script>alert(1)</script>',
    # Sortie d'attribut + événement
    '" onmouseover="alert(1)',
    # Guillemet simple + événement
    "' onclick='alert(1)",
    # Entité HTML malveillante
    "' onclick=alert(1)",
    # Template-like (doit rester littéral)
    "{{1+1}}",
    # Caractères spéciaux
    "a&b",
    # SVG onload
    "<svg/onload=alert(1)>",
    # javascript: URI (reste dans href si échappé correctement)
    "javascript:alert(1)",
    # Double encodage tentative
    "<script>alert(1)</script>",
]


def _render_template(template_xml: str, ctx: dict) -> str:
    """Rend un template XML avec le contexte donné."""
    r = QwebRegistry()
    r.register_source(template_xml)
    return r.render("corpus", ctx)


def _parse_fragment(html: str) -> etree._Element:
    """Parse un fragment HTML en l'enveloppant dans <root>."""
    return etree.fromstring(f"<root>{html}</root>")


def _get_sink_result(html: str, sink_id: str) -> etree._Element:
    """Extrait l'élément avec l'id donné du HTML rendu."""
    root = _parse_fragment(html)
    return root.find(f".//*[@id='{sink_id}']")


# ---------------------------------------------------------------------
# Template de test commun — 4 sinks : t-esc (texte), t-att-href (attr),
# t-attf-href (attr formaté), t-out (raw, confiance seulement)
# ---------------------------------------------------------------------

CORPUS_TEMPLATE = textwrap.dedent("""
    <template t-name="corpus">
        <div>
            <!-- t-esc : sink texte (échappé) -->
            <p id="esc"><t t-esc="payload"/></p>
            <!-- t-att-href : sink attribut simple (échappé) -->
            <a id="attr" t-att-href="payload">link</a>
            <!-- t-attf-href : sink attribut formaté (échappé) -->
            <a id="attf" t-attf-href="/go?q={{payload}}">link</a>
            <!-- t-out : sink raw (NON échappé — confiance seulement) -->
            <p id="out"><t t-out="payload"/></p>
        </div>
    </template>
""").strip()


class TestXssCorpus:
    """Tests du corpus XSS sur les sinks échappés."""

    def test_esc_text_sink_neutralizes_payloads(self):
        """t-esc : le payload ne crée AUCUN élément/attribut supplémentaire.
        La structure HTML reste exactement 1 <p> avec le texte échappé."""
        for payload in XSS_PAYLOADS:
            html = _render_template(CORPUS_TEMPLATE, {"payload": payload})
            p = _get_sink_result(html, "esc")
            assert p is not None
            assert p.tag == "p"
            # Le texte du nœud doit être le payload original (lxml décode les entités)
            # Mais la structure ne doit PAS contenir de sous-éléments
            assert len(list(p)) == 0, f"Sous-éléments créés pour payload {payload!r}"
            # Vérifier qu'aucun attribut n'a fuité (hors id qui est dans le template)
            assert set(p.attrib.keys()) == {"id"}

    def test_attr_href_sink_neutralizes_payloads(self):
        """t-att-href : le payload devient la valeur de l'attribut href.
        Aucun attribut supplémentaire ne doit apparaître (pas de sortie d'attribut)."""
        for payload in XSS_PAYLOADS:
            html = _render_template(CORPUS_TEMPLATE, {"payload": payload})
            a = _get_sink_result(html, "attr")
            assert a is not None
            assert a.tag == "a"
            # Attributs : href + id (du template)
            assert set(a.attrib.keys()) == {"href", "id"}, (
                f"Attributs inattendus pour payload {payload!r}: {list(a.attrib.keys())}"
            )
            # La valeur href doit correspondre au payload (lxml décode)
            assert a.get("href") == payload

    def test_attf_href_sink_neutralizes_payloads(self):
        """t-attf-href : le payload est interpolé dans la chaîne de format.
        La valeur href finale = '/go?q=' + payload. Aucun attribut bonus."""
        for payload in XSS_PAYLOADS:
            html = _render_template(CORPUS_TEMPLATE, {"payload": payload})
            a = _get_sink_result(html, "attf")
            assert a is not None
            assert a.tag == "a"
            assert set(a.attrib.keys()) == {"href", "id"}
            expected = "/go?q=" + payload
            assert a.get("href") == expected

    def test_out_sink_escapes_strings_only_markup_is_raw(self):
        """t-out : échappe les chaînes SAUF si la valeur est déjà un
        markupsafe.Markup (HTML de confiance pré-marqué). Ce test documente
        le comportement réel — t-out n'est PAS un sink 'raw' pour des
        chaînes arbitraires, il nécessite Markup(value) pour être raw."""
        from markupsafe import Markup

        # Chaîne simple -> échappée
        payload = "<strong>bold</strong>"
        html = _render_template(CORPUS_TEMPLATE, {"payload": payload})
        p = _get_sink_result(html, "out")
        assert p is not None
        # Le <strong> est échappé, pas interprété
        assert p.text == "<strong>bold</strong>"

        # Même payload dans Markup -> raw (non échappé)
        # Utiliser un payload XML valide pour le parsing lxml
        safe_payload = "<em>italic</em>"
        html2 = _render_template(CORPUS_TEMPLATE, {"payload": Markup(safe_payload)})
        p2 = _get_sink_result(html2, "out")
        assert p2 is not None
        em = p2.find("em")
        assert em is not None
        assert em.text == "italic"

    def test_no_structure_change_in_escaped_sinks(self):
        """Test global : pour chaque payload, les sinks échappés ne changent
        JAMAIS la structure du DOM (mêmes tags, mêmes attributs, pas de bonus)."""
        for payload in XSS_PAYLOADS:
            html = _render_template(CORPUS_TEMPLATE, {"payload": payload})
            root = _parse_fragment(html)

            # Vérifier la structure exacte attendue
            div = root.find("div")
            assert div is not None

            # 1 p#esc (texte seul)
            esc = div.find("p[@id='esc']")
            assert esc is not None
            assert len(list(esc)) == 0
            assert set(esc.attrib.keys()) == {"id"}

            # 2 a#attr (href + id)
            attr = div.find("a[@id='attr']")
            assert attr is not None
            assert set(attr.attrib.keys()) == {"href", "id"}

            # 3 a#attf (href + id)
            attf = div.find("a[@id='attf']")
            assert attf is not None
            assert set(attf.attrib.keys()) == {"href", "id"}

            # 4 p#out (peut avoir des enfants — c'est le point du t-out)
            out = div.find("p[@id='out']")
            assert out is not None