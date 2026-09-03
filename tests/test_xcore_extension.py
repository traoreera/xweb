"""XwebExtension — le service ext.xweb (docs/integration-xcore.md).

Teste contre le repli local BaseService (xcore n'est pas installé dans
cet environnement de dev — voir le docstring de engine/integration/xcore.py
pour pourquoi ce n'est pas juste "pas testé"). Le repli reproduit le
contrat exact lu dans xcore/services/base.py.
"""

import logging

from xweb.engine.integration.xcore import ServiceStatus, XwebExtension


async def test_init_registers_directory_and_becomes_ready(tmp_path):
    (tmp_path / "button.xml").write_text('<template t-name="test.custom_button"><button/></template>')
    ext = XwebExtension(config={"directory": str(tmp_path)})
    await ext.init()
    assert ext.is_ready
    assert ext.engine.get("test.custom_button") is not None


async def test_init_with_namespaces_resolves_a_real_patch(tmp_path):
    """docs/integration-xcore.md: namespaces dit QUELS dossiers scanner
    (et les tague pour les messages de conflit xpath), pas comment
    nommer — le t-name qualifié vient du fichier lui-même."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "button.xml").write_text('<template t-name="xweb.button"><button/></template>')

    crm = tmp_path / "crm_app_templates"
    crm.mkdir()
    (crm / "patch.xml").write_text(
        '<template t-name="crm_app.badge" t-inherit="xweb.button">'
        '<xpath expr="//button" position="inside"><span>CRM</span></xpath>'
        "</template>"
    )

    ext = XwebExtension(config={"directory": str(core), "namespaces": {"crm_app": str(crm)}})
    await ext.init()
    html = ext.engine.render("xweb.button", {})
    assert "CRM" in html


async def test_init_with_no_project_templates_configured_is_still_ready_from_builtins(tmp_path):
    """Écart réel trouvé en câblant xweb/components/ (docs/integration-xcore.md)
    — avant, un projet sans aucun template configuré (directory vide,
    namespaces vide) finissait DEGRADED : rien n'était chargé du tout.
    Depuis que xweb/components/ (les ~30 xweb.*) se charge tout seul, sans
    dépendre d'aucune config (voir XwebExtension.init()), cette situation
    ne peut plus arriver — READY même à vide, parce que le paquet embarque
    toujours son propre catalogue."""
    ext = XwebExtension(config={"directory": str(tmp_path)})  # empty dir
    await ext.init()
    assert ext._status == ServiceStatus.READY
    assert ext.is_ready is True
    assert len(ext.engine) > 0
    assert ext.engine.get("xweb.button") is not None


def test_csrf_token_stable_across_the_process_not_regenerated_per_call():
    """docs/csrf.py — un formulaire déjà rendu avec l'ancien token ne doit
    pas devenir invalide juste parce qu'une autre requête est arrivée."""
    ext = XwebExtension()
    token = ext.csrf_token
    assert isinstance(token, str) and len(token) > 20
    assert ext.csrf_token == token


def test_two_extensions_get_different_tokens():
    """Pas une constante partagée — un vrai secret par process/instance."""
    assert XwebExtension().csrf_token != XwebExtension().csrf_token


async def test_health_check_before_init():
    ext = XwebExtension()
    ok, msg = await ext.health_check()
    assert ok is False
    assert msg == "not initialized"


async def test_health_check_after_init_reports_template_count(tmp_path):
    """Le compte total inclut désormais toujours xweb/components/ (baseline
    calculée en direct, pas un nombre en dur — fragile dès qu'un composant
    xweb de plus est ajouté sinon)."""
    baseline = XwebExtension()
    await baseline.init()
    baseline_count = len(baseline.engine)

    (tmp_path / "a.xml").write_text('<template t-name="test.health_a"><p/></template>')
    (tmp_path / "b.xml").write_text('<template t-name="test.health_b"><p/></template>')
    ext = XwebExtension(config={"directory": str(tmp_path)})
    await ext.init()
    ok, msg = await ext.health_check()
    assert ok is True
    assert str(baseline_count + 2) in msg


async def test_shutdown_sets_stopped(tmp_path):
    (tmp_path / "x.xml").write_text('<template t-name="x"><p/></template>')
    ext = XwebExtension(config={"directory": str(tmp_path)})
    await ext.init()
    await ext.shutdown()
    assert ext._status == ServiceStatus.STOPPED


async def test_status_dict_shape(tmp_path):
    baseline = XwebExtension()
    await baseline.init()
    baseline_count = len(baseline.engine)

    (tmp_path / "x.xml").write_text('<template t-name="test.status_x"><p/></template>')
    ext = XwebExtension(config={"directory": str(tmp_path)})
    await ext.init()
    assert ext.status() == {"name": "xweb", "status": "ready", "templates": baseline_count + 1}


async def test_init_surfaces_xpath_conflicts_in_boot_log(tmp_path, caplog):
    """registry.py::check_all(), branché dans init() — un conflit atterrit
    dans le log de boot (là où on l'a vu tourner en vrai), pas seulement
    la première fois qu'une page visite le template concerné."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "button.xml").write_text('<template t-name="xweb.button"><button/></template>')

    crm = tmp_path / "crm"
    crm.mkdir()
    (crm / "a.xml").write_text(
        '<template t-name="crm.a" t-inherit="xweb.button" priority="5">'
        '<xpath expr="//button" position="replace"><a id="winner"/></xpath></template>'
    )
    (crm / "b.xml").write_text(
        '<template t-name="crm.b" t-inherit="xweb.button" priority="20">'
        '<xpath expr="//button" position="replace"><a id="loser"/></xpath></template>'
    )

    ext = XwebExtension(config={"directory": str(core), "namespaces": {"crm_app": str(crm)}})
    with caplog.at_level(logging.WARNING):
        await ext.init()  # PAS de render() — check_all() doit suffire
    assert any("conflict" in r.message for r in caplog.records)


async def test_bind_hot_reload_cleans_up_on_real_xcore_event_bus(tmp_path):
    """Vrai EventBus xcore (installé, xcoreruntime==2.5.2), pas un mock —
    prouve que bind_hot_reload() interprète correctement le nom d'event
    plugin.{name}.unloaded tel que supervisor.py l'émet réellement."""
    from xcore.kernel.events.bus import EventBus

    from xweb.contrib import Contribution, nav
    from xweb.engine.integration.xcore import bind_hot_reload

    core = tmp_path / "core"
    core.mkdir()
    (core / "button.xml").write_text('<template t-name="xweb.button"><button/></template>')
    crm = tmp_path / "crm"
    crm.mkdir()
    (crm / "page.xml").write_text('<template t-name="crm_app.page"><div>x</div></template>')

    ext = XwebExtension(config={"directory": str(core), "namespaces": {"crm_app": str(crm)}})
    await ext.init()
    nav.register(Contribution(id="crm_app.nav", plugin="crm_app", label="CRM"))

    events = EventBus()
    fake_xcore = type("FakeXcore", (), {"events": events})()
    bind_hot_reload(fake_xcore, ext)

    assert ext.engine.get("crm_app.page") is not None
    assert any(c.id == "crm_app.nav" for c in nav.list())

    await events.emit("plugin.crm_app.unloaded", {})

    assert ext.engine.get("crm_app.page") is None
    assert not any(c.id == "crm_app.nav" for c in nav.list())
    assert ext.engine.get("xweb.button") is not None  # plugin "core" — pas touché

    nav.unregister_plugin("crm_app")  # nettoyage — singleton de module partagé entre tests


async def test_missing_directory_does_not_crash_init():
    """register_dir's silent no-op (engine/registry.py) applies here too —
    a plugin declared in namespaces before its templates/ folder exists
    (fresh scaffold, docs/migration-guide.md) shouldn't crash the boot.
    READY regardless — xweb/components/ (the builtin catalogue) doesn't
    depend on `directory` at all, see XwebExtension.init()."""
    ext = XwebExtension(config={"directory": "/does/not/exist"})
    await ext.init()
    assert ext._status == ServiceStatus.READY
    assert ext.is_ready
