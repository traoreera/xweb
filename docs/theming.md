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

`@source "../xweb/components/**/*.xml"` / `@source "../plugins/**/*.xml"` dans `assets/app.css` — explicite plutôt que de compter sur le scanner de contenu automatique de Tailwind v4 pour reconnaître `.xml` comme une extension à inspecter.
