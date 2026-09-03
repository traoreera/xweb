"""XwebContext — injecté dans chaque vue de page xweb.

Porté depuis xui/context.py (docs/spec-v1.md §4) — aucune logique RBAC
dupliquée : has_role/require_role lisent le même AuthPayload que
get_current_user/RBACChecker du kernel.

## Sans xcore

xweb s'importe et s'utilise (XwebContext, CSRF, forms, mounts statics)
sans xcore installé — AuthPayload/PluginContext ne servent qu'à
l'annotation, retombent sur Any si le kernel est absent. Seul
mount_xweb_page exige xcore à l'appel (résolution de l'utilisateur), pas
à l'import — voir xweb/mount.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.requests import Request

if TYPE_CHECKING:
    from xcore.kernel.api.auth import AuthPayload
    from xcore.kernel.api.context import PluginContext
else:
    try:
        from xcore.kernel.api.auth import AuthPayload
        from xcore.kernel.api.context import PluginContext
    except ImportError:
        AuthPayload = Any  # type: ignore[misc, assignment]
        PluginContext = Any  # type: ignore[misc, assignment]


async def resolve_user_or_anonymous(request: Request) -> AuthPayload | None:
    """Résout l'utilisateur courant en distinguant "anonyme" d'une panne
    réelle du backend d'auth : un 401 devient None (visiteur légitime),
    toute autre HTTPException remonte telle quelle — ne jamais élargir en
    except Exception généralisé (docs/spec-v1.md, porté depuis xui)."""
    from fastapi import HTTPException
    from xcore.kernel.api.rbac import _resolve_user

    try:
        return await _resolve_user(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


class XwebPermissionDenied(Exception):
    """Levée par XwebContext.require_role — jamais laissée remonter telle
    quelle : mount_xweb_page l'intercepte pour rediriger vers le login
    (utilisateur anonyme) ou rendre une page 403 (rôle manquant)."""

    def __init__(self, required_roles: tuple[str, ...]) -> None:
        self.required_roles = required_roles
        super().__init__(f"rôle(s) requis manquant(s) : {', '.join(required_roles)}")


class XwebLoginRequired(XwebPermissionDenied):
    """Levée par XwebContext.require_user — la page exige juste d'être
    connecté, aucun rôle particulier. mount_xweb_page redirige vers le
    login ; un utilisateur connecté ne peut pas la déclencher."""

    def __init__(self) -> None:
        super().__init__(())


@dataclass
class XwebRedirect:
    path: str
    code: int = 303


def user_display(user: Any) -> dict[str, str]:
    """Nom lisible / email / initiale depuis un AuthPayload (xcore/kernel/
    api/auth.py) — seul `sub` est garanti, `user` est un dict optionnel de
    forme libre côté backend d'auth. Utilisé par le shell (widget de
    compte) et par plugins/account ; dégrade toujours sur `sub`, ne plante
    jamais."""
    if not user:
        return {"label": "", "email": "", "initial": "", "sub": ""}
    profile = user.get("user") or {}
    email = profile.get("email") or ""
    label = profile.get("name") or email or user.get("sub") or "?"
    return {"label": label, "email": email, "initial": label[:1].upper(), "sub": user.get("sub", "")}


@dataclass
class XwebContext:
    plugin_ctx: PluginContext
    request: Request
    user: AuthPayload | None

    def get_service(self, name: str) -> Any:
        return self.plugin_ctx.get_service(name)

    async def call_plugin(self, plugin: str, action: str, payload: dict | None = None) -> dict:
        if self.plugin_ctx.caller is None:
            raise RuntimeError(
                f"[{self.plugin_ctx.name}] call_plugin() indisponible "
                "(pas de caller injecté — plugin sandboxed ou contexte de test)."
            )
        return await self.plugin_ctx.caller(
            plugin, action, payload or {},
            caller=self.plugin_ctx.name, tenant_id=self.plugin_ctx.tenant_id,
        )

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    def has_role(self, *roles: str) -> bool:
        if self.user is None:
            return False
        granted = set(self.user.get("roles", [])) | set(self.user.get("permissions", []))
        return bool(granted & set(roles))

    def require_user(self) -> None:
        """Page réservée aux utilisateurs connectés, sans rôle particulier
        (profil, sessions…). Anonyme → redirection login par mount_xweb_page."""
        if self.user is None:
            raise XwebLoginRequired()

    def require_role(self, *roles: str) -> None:
        if not self.has_role(*roles):
            raise XwebPermissionDenied(roles)

    def redirect(self, path: str, code: int = 303) -> XwebRedirect:
        return XwebRedirect(path, code)

    @property
    def csrf_token(self) -> str:
        """Token CSRF de process (XwebExtension.csrf_token) — "" hors xcore
        (tests, CLI), jamais une exception."""
        try:
            ext = self.plugin_ctx.get_service("ext.xweb")
        except Exception:
            return ""
        return getattr(ext, "csrf_token", "") or ""
