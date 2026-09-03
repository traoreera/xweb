"""xweb — moteur de rendu QWeb et SDK de plugin pour xcore.

Voir docs/spec-v1.md pour les principes fondateurs. Comme xui avant lui,
xweb s'importe et fonctionne (contexte, CSRF, forms, mounts statics) sans
xcore installé — seul mount_xweb_page l'exige, au moment de l'appel.
"""

from .context import (
    XwebContext,
    XwebLoginRequired,
    XwebPermissionDenied,
    XwebRedirect,
    resolve_user_or_anonymous,
    user_display,
)
from .contrib import AUTHENTICATED, Contribution, commands, nav, ribbon, status_bar
from .csrf import CSRF_FIELD, CSRF_HEADER, CSRFMiddleware
from .forms import FormResult, parse_form
from .i18n import LOCALE_COOKIE, LOCALE_QUERY_PARAM, SOURCE_LOCALE, Catalog, resolve_locale
from .mount import (
    DEFAULT_ACCOUNT_PATH,
    DEFAULT_LAYOUT,
    DEFAULT_LOGIN_PATH,
    DEFAULT_LOGOUT_PATH,
    MINIMAL_LAYOUT,
    is_hx_request,
    login_url,
    mount_builtin_assets,
    mount_dev_proxy,
    mount_plugin_static,
    mount_spa,
    mount_spa_or_proxy,
    mount_xweb_page,
    redirect_response,
    render_xweb_template,
)
from .packages import XwebPackageRegistry
from .security import DEFAULT_CSP, XWEB_THEME_SCRIPT_HASH, SecurityHeadersMiddleware
from .urls import PageRoute, mount_xweb_pages, path, reverse

__all__ = [
    "XwebContext",
    "XwebLoginRequired",
    "XwebPermissionDenied",
    "XwebRedirect",
    "resolve_user_or_anonymous",
    "user_display",
    "AUTHENTICATED",
    "Contribution",
    "nav",
    "ribbon",
    "commands",
    "status_bar",
    "CSRFMiddleware",
    "CSRF_FIELD",
    "CSRF_HEADER",
    "FormResult",
    "parse_form",
    "Catalog",
    "resolve_locale",
    "SOURCE_LOCALE",
    "LOCALE_COOKIE",
    "LOCALE_QUERY_PARAM",
    "DEFAULT_LAYOUT",
    "MINIMAL_LAYOUT",
    "DEFAULT_LOGIN_PATH",
    "DEFAULT_ACCOUNT_PATH",
    "DEFAULT_LOGOUT_PATH",
    "is_hx_request",
    "login_url",
    "redirect_response",
    "mount_xweb_page",
    "render_xweb_template",
    "mount_plugin_static",
    "mount_spa",
    "mount_dev_proxy",
    "mount_spa_or_proxy",
    "mount_builtin_assets",
    "XwebPackageRegistry",
    "SecurityHeadersMiddleware",
    "DEFAULT_CSP",
    "XWEB_THEME_SCRIPT_HASH",
    "PageRoute",
    "path",
    "mount_xweb_pages",
    "reverse",
]
