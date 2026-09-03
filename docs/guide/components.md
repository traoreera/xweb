# Composants xweb

~48 composants DaisyUI vivent dans `xweb/components/` — chargés automatiquement, jamais à lister dans `integration.yaml`. Catalogue complet et historique de migration : [`components.md`](../components.md) (onglet *Référence*). `plugins/demo/templates/components.xml` (`/plugins/demo/components`) les exerce tous ensemble pour de vrai — le premier réflexe avant de réinventer un pattern.

## Tableau

```xml
<t t-call="xweb.table" size="sm" zebra="1"
   t-att-columns="[{'key': 'email', 'label': 'Email'}, {'key': 'role', 'label': 'Rôle'}]"
   t-att-rows="members" empty="Aucun membre."/>
```

`columns`/`rows` sont des **props calculées** (`t-att-*`, expressions Python) — `columns`/`rows` littéraux ne marcheraient pas, ce sont des listes, pas des chaînes. Un slot non vide remplace tout le corps auto-généré pour des lignes sur mesure (boutons d'action par ligne, par exemple) — voir `xweb/components/table.xml`.

## Formulaire + champ + validation

```xml
<t t-call="xweb.form" t-att-action="account_path + 'security'" t-att-token="csrf_token">
    <t t-call="xweb.field" label="Email" for_="email" t-att-error="errors.get('email')">
        <t t-call="xweb.input" type="email" name="email" id="email" t-att-value="email" t-att-required="True"/>
    </t>
    <t t-call="xweb.button" variant="primary" size="sm" type="submit" extra_class="">Enregistrer</t>
</t>
```

`xweb.form` pose lui-même le champ CSRF cachée (`xweb.csrf`) dès que `method="post"` (le défaut) — jamais à ajouter à la main. Pour un formulaire qui répond en **fragment htmx** plutôt qu'en redirection (`hx-post`/`hx-target`/`hx-swap`), un `<form>` nu + `<t t-call="xweb.csrf" t-att-token="csrf_token"/>` est le bon niveau : `xweb.form` ne connaît que ses props déclarées, un `hx-post` posé sur le `t-call` lui-même ne serait jamais rendu — voir [Votre première page](first-page.md).

## Modale

```xml
<t t-call="xweb.modal" id="confirm-delete" title="Supprimer ?" size="modal-sm">
    <p>Cette action est irréversible.</p>
    <t t-set="actions" t-value="'<form method=\"dialog\"><button class=\"btn btn-error\">Confirmer</button></form>'"/>
</t>
<button class="btn btn-error btn-sm" _="on click call document.getElementById('confirm-delete').showModal()">
    Supprimer
</button>
```

`<dialog>` natif — ouverture via `_hyperscript`/`showModal()`, fermeture via `<form method="dialog">` (toujours `hx-boost="false"` dessus, sinon htmx intercepte la soumission avant le navigateur).

## Toast (notification éphémère)

```xml
<!-- plugins/mon_plugin/templates/saved_toast.xml — un template dédié, comme
     plugins/demo/templates/toast.xml (exemple réel, /plugins/demo/, bouton
     "Afficher un toast") -->
<template t-name="mon_plugin.saved_toast">
    <t t-call="xweb.toasts_oob">
        <t t-call="xweb.toast" variant="success" t-att-timeout="4">Enregistré.</t>
    </t>
</template>
```

```python
@router.post("/save")
async def save():
    ...
    return HTMLResponse(engine.render("mon_plugin.saved_toast", {}))
```

`xweb.toast` s'auto-supprime après `timeout` secondes (`_hyperscript`, zéro JS écrit à la main) ; `xweb.toasts_oob` enveloppe son slot dans un `hx-swap-oob` qui atterrit dans `#xweb-toasts` (posé par `xweb.shell`) — en plus de la réponse principale d'une route, jamais à la place.

## Icônes — jamais de police d'icônes

```xml
<t t-call="xweb.icon" name="check_circle" extra_class="size-5 text-success"/>
```

SVG inline (`xweb/components/icon.xml`), pas de `<link>` externe — CSP `img-src`/`font-src` restée fermée. Un `name` inconnu retombe sur un point d'interrogation générique, jamais une exception — un plugin qui déclare une icône avec une faute de frappe ne casse jamais le shell entier.
