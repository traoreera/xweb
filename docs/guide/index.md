# Guide

Cette section explique **comment utiliser** xweb et xcore, avec des exemples précis et copiables — le contraire du reste de la doc (`docs/*.md`, onglet *Référence*), qui explique **pourquoi** le système est construit comme il l'est, décisions architecturales et pièges déjà rencontrés à l'appui.

Si vous cherchez... | Allez plutôt vers...
---|---
Lancer ce dépôt et voir une page réelle tourner | [Démarrage rapide](quickstart.md)
Créer une page server-rendue de bout en bout | [Votre première page](first-page.md)
La liste des directives `t-*` avec un exemple pour chacune | [Templates QWeb](templates.md)
Les ~48 composants DaisyUI prêts à l'emploi | [Composants xweb](components.md)
Ajouter une entrée de nav, un raccourci Ctrl+K, une permission | [Shell, nav et permissions](shell-and-nav.md)
Faire parler votre plugin HTML à un plugin JSON pur | [Parler à un plugin JSON](auth-pattern.md)

!!! tip "Un doute sur une signature ?"
    Chaque exemple de ce guide est vérifié contre le code réel de ce dépôt (`xweb/`, `plugins/account/`, `plugins/demo/`) — pas une API imaginée à l'avance. En cas de doute, `grep` la fonction citée vaut mieux que faire confiance à un extrait qui aurait dérivé.
