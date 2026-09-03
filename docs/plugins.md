# Intégrer xweb dans un plugin

## Structure

```
plugins/<name>/
├── plugin.yaml
├── src/
│   └── main.py
└── templates/
    ├── *.xml
    └── components/
```

## 1. Déclarer une page

```python
# plugins/crm_app/src/main.py
from xweb import mount_page

def get_router():
    router = APIRouter()
    mount_page(router, path="/contacts", template="crm_app.contacts_list", roles=["crm.viewer"])
    return router
```

`mount_page` résout l'utilisateur, applique `require_role`, redirige vers le login si non authentifié — même contrat que `mount_xui_page` dans xui, renommé pour cohérence.

## 2. Mutation = route htmx explicite

Jamais de dispatcher générique. Chaque bouton qui mute quelque chose pointe vers une route déclarée par le plugin.

```xml
<!-- plugins/crm_app/templates/contacts_list.xml -->
<button hx-post="/plugins/crm_app/contacts" hx-target="#contacts" hx-swap="afterbegin"
        class="btn btn-primary">Ajouter</button>
<div id="contacts">
    <t t-foreach="contacts" t-as="c"><t t-call="crm_app.contact_row" contact="c"/></t>
</div>
```

```python
@router.post("/contacts")
async def create_contact(ctx: XwebContext = Depends(xweb_context)):
    ctx.require_role("crm.editor")
    form = await parse_form(ctx.request, ContactForm)
    if not form.valid:
        return await engine.render("crm_app.contact_row_error", {"errors": form.errors})
    contact = await create(form.data)
    return await engine.render("crm_app.contact_row", {"contact": contact})   # fragment htmx, pas la page entière
```

La route htmx retourne un **fragment** (`crm_app.contact_row`), pas la page complète — `hx-swap` l'insère à l'endroit ciblé. C'est la différence structurante avec un `POST` classique qui redirige : ici, une seule route sert à la fois le rendu initial (via `t-call` dans la page) et la mise à jour (en réponse à `hx-post`), le même template des deux côtés.

## 3. Contribuer au shell

```python
from xweb.contrib import NavRegistry, NavNode, RibbonRegistry, CommandRegistry, Contribution

NavRegistry.register(NavNode(id="crm.contacts", plugin="crm_app", label="Contacts", path="/plugins/crm_app/contacts", permission="crm.viewer"))
CommandRegistry.register(Contribution(id="crm.new_contact", plugin="crm_app", order=10))
```

À faire dans `on_load()` du plugin. Le nettoyage au unload/reload, lui, est centralisé dans `ext.xweb` (abonnement à `plugin.*.unloaded` sur l'event bus xcore, voir `spec-v1.md` §3) — un plugin n'a rien à faire lui-même pour ça, contrairement à ce que `NavRegistry` exigeait dans xui.

## 4. Étendre un plugin tiers

```xml
<!-- plugins/analytics_widget/templates/dashboard_patch.xml -->
<template t-name="analytics_widget.dashboard_widget" t-inherit="dashboard.index" t-inherit-mode="extension">
    <xpath expr="//div[@id='kpis']" position="after">
        <t t-call="analytics_widget.chart_card"/>
    </xpath>
</template>
```

Aucune coordination requise avec l'auteur de `dashboard` — voir `inheritance.md` pour la résolution de priorité si plusieurs plugins patchent le même nœud.

## RBAC unifié

```python
ctx.require_role("crm.editor")   # lève XwebPermissionDenied — jamais un 200 avec du HTML vide
```

Même `AuthPayload`/`RBACChecker` que les routes API pures du kernel (`spec-v1.md` principe 3) — pas de second système de rôles propre à xweb.

## Mode SPA — zéro dépendance xweb

```yaml
# plugin.yaml
ui:
  mode: spa
  dist_dir: ui/dist
```

Un plugin `mode: spa` n'importe jamais `xweb` — StaticFiles + fallback `index.html`, comme documenté pour xui aujourd'hui.

## Checklist sécurité

- Toute route mutative (`hx-post`/`hx-put`/`hx-delete`) passe par `require_role` avant d'agir, jamais après avoir déjà écrit en base.
- Aucun `t-out` sur une donnée qui vient directement d'un `t-att-*`/formulaire sans passer par un composant de confiance.
- `permissions:` dans `plugin.yaml` déclaré explicitement pour toute route appelée en htmx (`integration-xcore.md#permissions`) — sinon bloqué silencieusement par défaut.
