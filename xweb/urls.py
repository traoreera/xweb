"""Déclaration de pages façon Django urlpatterns (docs/spec-v1.md §6).

Porté depuis xui/urls.py — pur sucre syntaxique au moment du montage,
mount_xweb_pages déroule la liste UNE FOIS pendant get_router() et
enregistre chaque route via mount_xweb_page. Rien de nouveau au moment
d'une requête, ce n'est pas un dispatcher générique.

    urlpatterns = [
        path("/", index_view, template="landing.index", name="landing.index"),
    ]

    def get_router(self):
        router = APIRouter()
        mount_xweb_pages(router, self.ctx, engine, urlpatterns, login_path="/plugins/demo_auth/login")
        return router
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter

from .mount import DEFAULT_LOGIN_PATH, PageView, mount_xweb_page

_names: dict[str, str] = {}


@dataclass(frozen=True)
class PageRoute:
    path: str
    view: PageView
    template: str
    name: str | None = None


def path(route: str, view: PageView, *, template: str, name: str | None = None) -> PageRoute:
    """Équivalent de django.urls.path() pour une page xweb — construit
    l'entrée, ne monte rien : le montage reste explicite via mount_xweb_pages()."""
    return PageRoute(path=route, view=view, template=template, name=name)


def mount_xweb_pages(
    router: APIRouter,
    ctx: Any,
    engine: Any,
    urlpatterns: list[PageRoute],
    *,
    login_path: str = DEFAULT_LOGIN_PATH,
) -> None:
    """Monte chaque PageRoute de urlpatterns via mount_xweb_page, dans
    l'ordre de la liste."""
    for route in urlpatterns:
        if route.name:
            if route.name in _names and _names[route.name] != route.path:
                raise ValueError(
                    f"xweb.urls: nom de route '{route.name}' déjà utilisé pour "
                    f"'{_names[route.name]}' — chaque name doit être unique process-wide."
                )
            _names[route.name] = route.path
        mount_xweb_page(
            router, ctx, engine,
            path=route.path, template=route.template, view=route.view,
            login_path=login_path,
        )


def reverse(name: str) -> str:
    """Équivalent minimal de django.urls.reverse() — pas de paramètres de
    chemin dynamiques pour l'instant, seulement les routes statiques
    déclarées via path(..., name=...)."""
    try:
        return _names[name]
    except KeyError:
        raise KeyError(
            f"xweb.urls.reverse: aucune route nommée '{name}' — "
            f"vérifie qu'elle est déclarée avec name= et que "
            f"mount_xweb_pages() a bien tourné avant cet appel."
        ) from None
