# Thème — DaisyUI

## Le mécanisme

DaisyUI théme via l'attribut `data-theme` sur `<html>` — pas via une classe (`.dark`) comme le faisait cotton-ui. Chaque valeur (`light`, `dark`, ou un nom de thème personnalisé) sélectionne un jeu de variables CSS que les classes DaisyUI (`btn`, `card`, …) consomment déjà.

```html
<html data-theme="dark">
```

## Bascule côté client — `_hyperscript`, pas de round-trip serveur

> **Vérifié** — exécuté pour de vrai contre `_hyperscript.min.js` 0.9.93 dans un DOM jsdom, pas juste de la syntaxe qui a l'air plausible. `npm install && npm run verify:hyperscript` (`scripts/verify-hyperscript.mjs`). La première version écrite ici utilisait `#html` en pensant cibler la balise `<html>` — `#html` est en réalité le sélecteur `id="html"` (inexistant), l'exécution a échoué avec `'#html' is null`. Corrigé avec `document.documentElement` (accès de propriété JS classique, que `_hyperscript` supporte nativement).

```xml
<button type="button" class="btn btn-ghost btn-circle"
    _="on click
         if document.documentElement.dataset.theme is 'dark' set document.documentElement.dataset.theme to 'light'
         else set document.documentElement.dataset.theme to 'dark'
       end
       then call localStorage.setItem('theme', document.documentElement.dataset.theme)">
    <t t-esc="icon"/>
</button>
```

Au premier chargement, un petit script inline (dans `<head>`, avant tout rendu de contenu — pour éviter le flash du mauvais thème) lit `localStorage.theme` et pose `data-theme` avant que le navigateur peigne quoi que ce soit :

```html
<script>
  document.documentElement.dataset.theme = localStorage.getItem('theme') || 'light';
</script>
```

Seule ligne de JS "à la main" de tout le système de thème — tout le reste passe par `_hyperscript` ou des classes.

## `mount_theme()` — simplifié par rapport à xui

`xui/theme.py` sert un fichier CSS custom entier (`FileResponse`) et expose son URL comme global de rendu. Avec DaisyUI, le thème n'est plus un fichier à servir — c'est une valeur (`data-theme`) à injecter dans le contexte du shell :

```python
# xweb/theme.py
def mount_theme(app: FastAPI, registry: "QwebRegistry", default: str = "light") -> None:
    """Expose la valeur data-theme par défaut au contexte de rendu du shell.
    L'utilisateur peut la surcharger localement (_hyperscript, localStorage) sans
    round-trip serveur — voir ci-dessus."""
    registry.add_global("default_theme", default)
```

Pas de route dédiée, pas de `FileResponse` — la seule chose que le serveur doit fournir est la valeur par défaut du premier rendu (avant que `localStorage` prenne le relais côté client).

## Thèmes personnalisés

DaisyUI permet de définir des thèmes nommés au-delà de `light`/`dark`, en CSS (`@plugin "daisyui/theme"` ou équivalent selon la version — voir *xweb Blueprint* §10, question ouverte sur le mode de build).

```css
/* assets/app.css */
@plugin "daisyui" {
  themes: light --default, dark --prefersdark, xcore-brand;
}

@plugin "daisyui/theme" {
  name: "xcore-brand";
  --color-primary: oklch(55% 0.2 250);
}
```

## Build {#build}

**Tranché — les deux, pas l'un ou l'autre.** Node est un outil de *dev*, jamais une dépendance d'exécution de xweb. `assets/app.css` (source, `@import "tailwindcss"; @plugin "daisyui";`) est compilé via `npm run build:css` (`package.json`, Tailwind CLI v4 + DaisyUI 5) vers `xweb/static/app.css` — qui est ensuite **vendorisé/commité**, exactement comme `htmx.min.js`/`_hyperscript.min.js`. Qui déploie xweb sert un fichier statique, point ; qui modifie les templates recompile avant de commiter.

```bash
npm install        # une fois
npm run build:css  # à chaque changement de classes utilisées dans xweb/components/**/*.xml ou plugins/**/*.xml
npm run watch:css   # pendant le développement
```

**Vérifié, pas juste construit** — `scripts/verify-demo-page.mjs` fetch `app.css` depuis un vrai xcore démarré et vérifie que les classes réellement utilisées (`.btn`, `.btn-primary`, `.btn-ghost`, `data-theme`...) y sont bien générées, pas un DaisyUI générique jamais branché sur les vraies sources.

**Limite trouvée en vérifiant** — jsdom (utilisé pour `verify-demo-page.mjs`, voir plus haut) ne peut pas vérifier un style *calculé* : son moteur CSS ne parse pas la syntaxe que Tailwind v4 génère (`@layer`, `@property`, `@supports` imbriqués — `Could not parse CSS stylesheet`, testé). La vérification se fait au niveau qui compte réellement : le contenu du fichier généré, pas le rendu visuel (que seul un vrai navigateur peut confirmer).

`@source "../templates/**/*.xml"` / `@source "../plugins/**/*.xml"` dans `assets/app.css` — explicite plutôt que de compter sur le scanner de contenu automatique de Tailwind v4 pour reconnaître `.xml` comme une extension à inspecter. `xweb/components/**/*.xml`, lui, est couvert par `xweb/static/xweb.css` (voir ci-dessous), pas dupliqué ici.

## Reconstruire le thème quand xweb est installé comme paquet (pas ce monorepo) {#build-consommateur}

**Le problème** — `xweb/static/app.css` (compilé, vendorisé, servi en prod) ships avec le paquet `xweb` installé (`pip`/`uv add xcoreruntime`… `xweb`), mais c'est une sortie Tailwind **figée** : les couleurs de marque de xcore-integration (`--color-primary: #00c896`, etc.) y sont déjà cuites. `assets/app.css` (la SOURCE Tailwind, avec les vrais `@plugin "daisyui/theme"`) et `package.json` (l'outillage npm/Tailwind CLI) vivent tous les deux à la racine de CE dépôt, **hors du paquet Python `xweb`** — un projet qui installe `xweb` comme dépendance ne les récupère pas. Un utilisateur final qui veut changer de thème dans un déploiement qui *consomme* xweb n'a donc, par défaut, aucun moyen de reconstruire le CSS.

**La solution** — `xweb/static/xweb.css` (dans le paquet, donc installé avec `xweb`) contient tout ce qui est *intrinsèque* aux composants xweb et indépendant de la marque : le `@source` vers les composants xweb eux-mêmes, la sécurité anti-scan des classes DaisyUI interpolées (`@source inline(...)`), et la mécanique CSS requise par `xweb.theme_toggle`/`xweb.popover`/`xweb.sidebar_toggle` pour fonctionner. Les chemins `@source` qu'il contient sont relatifs à *ce fichier* (Tailwind v4 les résout par rapport au fichier où ils sont déclarés, jamais par rapport au fichier qui fait le `@import`) — donc l'importer depuis n'importe quel projet, à n'importe quelle profondeur, retrouve toujours `xweb/components/` au bon endroit tant que le chemin relatif jusqu'à `xweb/static/xweb.css` lui-même est correct.

Ce dépôt applique ce même mécanisme sur lui-même — `assets/app.css` fait `@import "../xweb/static/xweb.css";` exactement comme le ferait un projet consommateur externe — donc la preuve qu'il fonctionne est vérifiable ici (`npm run build:css`, puis comparer les classes/règles générées) plutôt que juste affirmée.

**Étapes pour un projet qui installe xweb comme dépendance :**

```bash
# 1. Localiser où le paquet xweb a été installé dans votre venv
uv run python -c "import xweb, pathlib; print(pathlib.Path(xweb.__file__).parent)"
# ex. /chemin/vers/votre-projet/.venv/lib/python3.X/site-packages/xweb

# 2. Outillage Tailwind, dans VOTRE projet (jamais une dépendance d'exécution)
npm init -y
npm install -D tailwindcss @tailwindcss/cli daisyui
```

```css
/* votre-projet/assets/app.css — votre PROPRE fichier, pas celui de xweb */
@import "tailwindcss";

/* Chemin vers l'installation réelle de xweb — celui trouvé à l'étape 1,
   relatif à ce fichier (ou un chemin absolu si votre outillage le permet). */
@import "../.venv/lib/python3.X/site-packages/xweb/static/xweb.css";

@plugin "daisyui" {
  themes: light --default, dark --prefersdark;  /* xweb.theme_toggle ne connaît que ces deux noms littéraux */
}

@plugin "daisyui/theme" {
  name: "light";
  --color-primary: /* votre couleur de marque */;
  /* … le reste de vos tokens de thème, voir "Thèmes personnalisés" ci-dessus */
}

@plugin "daisyui/theme" {
  name: "dark";
  /* … */
}

/* VOS templates à vous (vos plugins/pages), pas ceux de xweb —
   déjà couverts par le @import ci-dessus. */
@source "./templates/**/*.xml";
@source "./plugins/**/*.xml";
```

```bash
npx tailwindcss -i assets/app.css -o chemin/vers/votre/sortie/app.css --minify
```

Reste à servir ce fichier de sortie à la place de (ou en overlay de) `xweb/static/app.css` — selon comment votre app monte ses fichiers statiques (voir `mount_builtin_assets` / vos propres routes statiques) — **et** à faire pointer la page vers ce nouveau fichier, pas vers le `/xweb-static/app.css` vendorisé. `xweb.shell_head` (le `<head>` partagé par `xweb.shell`/`xweb.shell_minimal`/`xweb.marketing_layout`) est un composant vendorisé, pas un fichier de votre projet — jamais à éditer directement (la prochaine mise à jour du paquet xweb l'écraserait). La façon non-destructive de changer ce qu'il sert : un patch `t-inherit` (docs/inheritance.md), exactement comme n'importe quelle autre extension de composant partagé.

```xml
<!-- templates/shell_head_patch.xml, dans VOTRE projet, source_plugin="site" -->
<template t-name="site.shell_head_patch" t-inherit="xweb.shell_head" t-inherit-mode="extension">
    <xpath expr="//link[@href='/xweb-static/app.css']" position="attributes">
        <attribute name="href">/static/app.css</attribute>
    </xpath>
</template>
```

Vérifié en rendant `xweb.shell_head` avec ce patch enregistré : le `<link rel="stylesheet">` pointe bien vers `/static/app.css` — aucune page qui `t-call="xweb.shell_head"` n'a besoin d'être modifiée, le patch s'applique partout où le composant est appelé (extension, pas primary — voir docs/inheritance.md).

**Non résolu ici** — un helper `xcli`/script qui automatise l'étape 1 et génère le squelette `assets/app.css` d'un coup ; aujourd'hui c'est un geste manuel documenté, pas outillé.
