import pytest

from xweb.packages import XwebPackageRegistry


def test_register_and_get():
    r = XwebPackageRegistry()
    r.register("com.xcore.ui_kit", "ui_kit", {"card": object()})
    assert r.get("com.xcore.ui_kit", "card") is not None


def test_register_duplicate_package_id_raises():
    r = XwebPackageRegistry()
    r.register("com.xcore.ui_kit", "ui_kit", {})
    with pytest.raises(ValueError):
        r.register("com.xcore.ui_kit", "other_plugin", {})


def test_get_unknown_package_raises_with_hint():
    r = XwebPackageRegistry()
    with pytest.raises(KeyError, match="chargé avant"):
        r.get("com.xcore.missing", "x")


def test_get_unknown_export_raises():
    r = XwebPackageRegistry()
    r.register("com.xcore.ui_kit", "ui_kit", {"card": 1})
    with pytest.raises(KeyError, match="n'exporte pas"):
        r.get("com.xcore.ui_kit", "modal")


def test_unregister_plugin_removes_only_its_packages():
    r = XwebPackageRegistry()
    r.register("a.pkg", "plugin_a", {"x": 1})
    r.register("b.pkg", "plugin_b", {"y": 1})
    r.unregister_plugin("plugin_a")
    assert r.get("b.pkg", "y") == 1
    with pytest.raises(KeyError):
        r.get("a.pkg", "x")
