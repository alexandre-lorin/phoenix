# Phoenix

Clonage complet de config Arch (paquets, dotfiles, services) versionné dans Git.

**→ [SETUP.md](./SETUP.md) pour l'installation complète, étape par étape, avec les pièges à éviter.**

## Install rapide

```bash
git clone <ton repo> phoenix-tool
cd phoenix-tool
pip install --user -e .
```

`tomllib` fait partie de la stdlib depuis Python 3.11 — vérifie que tu es dessus (`python --version`). Sur Arch c'est déjà le cas de base.

## Usage

```bash
phoenix snapshot
phoenix restore              # interactif, demande confirmation à chaque étape
phoenix restore --yes        # non-interactif de bout en bout : ni Phoenix ni pacman/yay ne demandent quoi que ce soit
phoenix restore --skip-aur   # ignore les paquets AUR
```

Premier run : crée `~/phoenix-config/` (override avec `PHOENIX_REPO=/autre/path`) et un `phoenix.toml` avec des chemins par défaut. **Édite ce fichier** pour matcher ta vraie structure de dotfiles avant le premier vrai snapshot.

⚠️ Phoenix capture les fichiers configurés tels quels. Vérifie qu'ils ne contiennent pas de tokens, clés API ou autres secrets avant de pousser le dépôt vers un remote (même privé) — l'historique Git garde tout, y compris après suppression ultérieure du fichier.

Chaque `phoenix snapshot` :
1. Exporte `pacman -Qqe` (natifs) et `pacman -Qqem` (AUR) séparément → `packages/`
2. Copie les chemins listés dans `phoenix.toml` → `dotfiles/` — **refuse et n'écrit rien** si deux chemins configurés partagent le même nom final (ex. deux dossiers `nvim` différents) plutôt que de laisser le second écraser silencieusement le premier
3. Exporte les services `systemctl` activés (système + user, seulement si `include_user_services = true`) → `services/`
4. Commit tout avec un message horodaté

## État d'implémentation

| Étape | Statut |
|---|---|
| V0 — inventaire paquets | ✅ |
| V1 — capture dotfiles | ✅ |
| V2 — services & systemd | ✅ |
| V3 — `phoenix snapshot` | ✅ |
| V4 — `phoenix restore` | ✅ |
| V5 — détection de divergence | ✅ |
| V6 — diff entre deux machines | ✅ |
| Rollback (point 4 du brief) | ✅ |
| DotDiff V0-V1 — comparaison + sortie lisible | ✅ (= `phoenix status`) |
| DotDiff V2 — diff de contenu textuel | ✅ (`phoenix status --content`) |
| DotDiff V3 — actions sélectives fichier par fichier | ✅ (`phoenix status --resolve`) |
| DotDiff V5 — rappel périodique de dérive | ✅ (`phoenix reminder`) |

## Fiabilité — audit et correctifs (feature freeze le temps de fermer ça)

Une revue technique a mis en évidence des bugs qui touchaient directement les trois garanties centrales de l'outil (capture → restore → rollback). Tous corrigés avec test de régression dédié :

- **Capture — collision de basename.** Deux chemins configurés avec la même feuille (`~/a/nvim` et `~/b/nvim`) faisaient que le second écrasait silencieusement le premier dans le manifest — perte de données non récupérable puisque le premier n'était jamais copié. `capture_dotfiles` (et donc `phoenix snapshot`) refuse maintenant **avant** de copier quoi que ce soit dès qu'une collision est détectée, message clair à l'appui.
- **Rollback — resynchronisation incomplète.** `git checkout <ref> -- <path>` (mode overlay, le défaut) ne supprime jamais un fichier ajouté après `<ref>` — un "rollback" laissait donc traîner des fichiers censés ne plus exister. Remplacé par `git checkout --no-overlay`, qui resynchronise l'arbre exactement (ajouts annulés, modifs annulées, suppressions annulées).
- **`diff_services` ignorait `include_user_services`.** Avec le flag à `false`, `phoenix status` comparait quand même les unités `--user` à un `services/user.txt` jamais tenu à jour, générant de faux positifs en continu. `diff_services` saute maintenant entièrement l'axe `user` si le flag est désactivé.
- **`restore --yes` n'était pas vraiment non-interactif.** Le bypass ne couvrait que les confirmations internes de Phoenix ; `pacman`/`yay`/`paru` posaient quand même leur propre question. `--noconfirm` est maintenant propagé à ces commandes quand `--yes` est passé — un restore scripté (VM de test, provisioning) ne bloque plus dessus. (Seule exception assumée : un `sudo` sans mot de passe reste un prérequis pour un restore totalement sans supervision — ce n'est pas une confirmation d'action, c'est une frontière d'authentification, hors du périmètre de `--yes`.)

### Restore robuste (deuxième passe, une fois le moteur de confiance stabilisé)

Un `restore` sert le plus souvent des mois après le snapshot, sur une machine neuve — exactement le moment où un paquet a été renommé/retiré des dépôts, ou une unité systemd a disparu avec son paquet. Trois correctifs pour que ça ne fasse plus tout échouer en bloc :

- **Paquets/AUR — isolation des échecs.** `pacman -S`/`yay -S` échouaient entièrement si un seul paquet du lot était introuvable, y compris pour les dizaines d'autres qui auraient pu s'installer sans problème. Maintenant : tentative en lot d'abord (rapide, cas normal), et seulement si elle échoue, retry paquet par paquet pour isoler précisément le(s) fautif(s) — les autres s'installent quand même.
- **Services — stderr remonté au lieu d'être avalé.** `systemctl enable ... check=False` sans lire la sortie faisait qu'une unité masquée ou absente semblait "activée" du point de vue de l'utilisateur. Même stratégie d'isolation que les paquets, avec le détail de l'erreur affiché.
- **Résumé final + code de sortie fidèle.** `phoenix restore` affiche maintenant un bilan (`✓ N installés`, `⚠ N indisponibles`, etc. pour chaque axe) et sort avec le code `1` s'il y a eu le moindre échec isolé — plus de "Restore terminé." optimiste alors que des paquets n'ont jamais été installés.
- **Plus de bootstrap automatique d'AUR helper.** L'ancienne version clonait `yay-bin` depuis l'AUR et lançait `makepkg -si --noconfirm` avec sudo pour compiler et installer un paquet tiers non vérifié — trop invasif pour un outil censé restaurer *ta* config, pas installer un gestionnaire de paquets à ta place. Sans `yay`/`paru` détecté, `phoenix restore` prévient et laisse les paquets AUR de côté ; à toi de les installer manuellement.

### Nice-to-have (troisième passe, polish une fois le reste stable)

- **`_hash_tree` élague maintenant les dossiers exclus au lieu de les parcourir puis filtrer.** `os.walk` + `dirnames[:] = [...]` empêche de descendre dans un dossier exclu par pattern (cache de plugin manager, `node_modules`...) plutôt que de lister tout son contenu pour le jeter ensuite. Zéro différence fonctionnelle, juste moins d'I/O payée pour rien à chaque `phoenix status`.
- **Plus de double calcul du diff dotfiles sur `phoenix status --content`/`--resolve`.** `run_status()` renvoie maintenant le diff déjà calculé (`(aligned, dot)`) au lieu que `cli.py` rappelle `diff_dotfiles()` une seconde fois derrière — le hash de tout l'arbre des dotfiles n'est plus fait deux fois pour une seule invocation.
- **`phoenix snapshot` affiche un `git diff --stat` après le commit.** Savoir qu'un commit a eu lieu ne disait rien de son contenu ; maintenant le nombre de fichiers touchés et les +/- sont visibles immédiatement, sans avoir à lancer `git show` à la main.
- **Le reminder (V5) ne compte plus les commits de rollback comme des snapshots.** `last_snapshot_timestamp` cherche maintenant spécifiquement le dernier commit dont le message commence par `snapshot:` — un `rollback` fréquent sans jamais relancer un vrai `snapshot` ne réinitialise plus le compteur de dérive à tort.

## Tests

Suite pytest formelle — 92 tests, tout le testable-sans-Arch-réel :

```bash
pip install --user -e ".[dev]"
pytest tests/ -v
```

Couvre : roundtrip capture/restore dotfiles (avec backup), refus de capture sur collision, détection de divergence (y compris respect de `include_user_services`), diff entre deux machines, rollback via Git réel (y compris resynchronisation exacte sur ajout+modif+suppression combinés, et le cas d'échec propre sur un commit inconnu), propagation de `--noconfirm` en mode `--yes`. **Ce que ça NE couvre PAS** : tout ce qui appelle `pacman`/`systemctl`/`makepkg` réellement — ça, seule ta machine peut le valider.

## `phoenix rollback` (point 4 du brief d'origine)

Le repo Git est déjà l'historique complet. Rollback ramène `packages/services/dotfiles/phoenix.toml` à l'état **exact** d'un commit antérieur — y compris la suppression des fichiers apparus après ce commit, pas seulement l'écrasement de ceux qui existaient déjà — sans jamais perdre l'historique : le rollback lui-même devient un nouveau commit, donc `git log` garde tout, y compris les allers-retours.

```bash
phoenix rollback                # liste les 15 derniers snapshots
phoenix rollback <hash>         # revient à cet état (demande confirmation)
phoenix rollback <hash> --yes   # sans confirmation
```

Rollback ne touche **pas** le système live — seulement le repo. Pour appliquer l'état revenu en arrière, lancer `phoenix restore` ensuite. Séparation volontaire : "changer d'avis sur le repo" et "toucher au système" ne doivent jamais être la même opération accidentelle.

## `phoenix status` (V5)

Lecture seule, zéro écriture sur le système. Compare l'état actuel au dernier snapshot committé :

```bash
phoenix status
```

- **Paquets** : ce qui a été installé/désinstallé à la main depuis le dernier `snapshot`.
- **Services** : services activés/désactivés à la main.
- **Dotfiles** : diff par hash SHA-256, fichier par fichier — modifié, ajouté, supprimé.

Code de sortie `0` = rien n'a bougé, `1` = divergence détectée. Exploitable en pre-check avant `restore` :

```bash
phoenix status || echo "snapshot avant de restaurer, sinon tu perds tes modifs manuelles"
```

`restore` appelle aussi un check de divergence sur les dotfiles avant de les écraser et affiche un avertissement — il ne bloque pas (le but de `restore` est parfois d'écraser volontairement), mais tu ne peux plus dire que tu savais pas.

### DotDiff — `phoenix status --content` / `--resolve`

Sous-ensemble de `status`, pas un outil à part (le repo Git versionné est déjà la seule source de vérité, pas besoin d'en ouvrir un autre).

```bash
phoenix status --content    # V2 : diff textuel réel (git diff --no-index) pour chaque dotfile modifié
phoenix status --resolve    # V3 : résolution interactive, fichier par fichier
```

`--resolve` demande, pour chaque fichier divergent, une action individuelle — jamais de "tout écraser en bloc" :

- **modifié** : garder la modif locale / revenir à la version versionnée (backup auto, `.phoenix-bak-<timestamp>`, jamais de suppression sèche) / skip
- **nouveau (jamais capturé)** : garder / supprimer (backup auto) / skip
- **supprimé du système** : garder supprimé / restaurer depuis le snapshot / skip

Pas de flag `--yes` sur `--resolve` : c'est un choix par fichier, pas un oui/non global — en forcer un par défaut irait à l'encontre du but même de cette fonctionnalité.

Le nom `phoenix diff` est déjà pris par la V6 (comparaison entre deux machines) — d'où l'intégration comme options de `status` plutôt qu'une nouvelle sous-commande.

Deux détails soignés :

- **`phoenix status --resolve --content`** : le diff textuel de chaque fichier modifié s'affiche juste avant la question, pas besoin de lancer `--content` séparément en amont pour savoir sur quoi on tranche.
- **Fichiers binaires** : `git diff --no-index` sort un `"Binary files ... differ"` illisible sur un binaire modifié. DotDiff le détecte et affiche à la place un message clair (`fichier binaire — pas de diff textuel affichable`), aussi bien dans `--content` que dans `--resolve --content`.

### DotDiff V5 — `phoenix reminder`

Rappel périodique : signale si les dotfiles ont dérivé **et** que ça fait plus de X jours (défaut 7) sans nouveau snapshot. Une dérive fraîche n'est pas un problème — elle sera absorbée au prochain `phoenix snapshot` normal ; c'est l'oubli prolongé qui mérite un rappel. Lecture seule, ne fait jamais de snapshot à ta place.

```bash
phoenix reminder                # seuil par défaut : 7 jours
phoenix reminder --days 14
phoenix reminder --quiet        # rien à l'écran, juste le code de sortie (pour hooks/scripts)
```

Code de sortie `0` = rien à signaler, `1` = rappel déclenché. Pas un daemon — à brancher sur un cron/timer systemd ou un hook de shell :

```bash
# crontab -e, une fois par jour
0 9 * * * PHOENIX_REPO=/home/user/phoenix-config /usr/bin/phoenix reminder

# .bashrc / .zshrc, rappel à l'ouverture d'un nouveau shell
phoenix reminder --quiet || echo "⚠ dotfiles en dérive depuis un moment — phoenix status ?"
```

## `phoenix diff <autre_repo>` (V6)

Compare **deux repos Phoenix déjà snapshotés** — pas deux systèmes live. Volontaire : rien ne garantit que ton laptop et un futur second poste soient allumés en même temps. Le repo Git est la seule source de vérité toujours comparable, peu importe le transport (clone Git, clé USB, partage réseau).

```bash
git clone <remote-du-poste-2> /tmp/poste2-config
phoenix diff /tmp/poste2-config
```

Sort paquets/services/dotfiles qui diffèrent entre les deux, hash-based pour les dotfiles. Code de sortie `0` = machines identiques, `1` = divergence.

## Comment `restore` fonctionne

Ordre fixe : **paquets → services → dotfiles**. Ce n'est pas arbitraire — les dotfiles référencent des binaires qui doivent déjà être installés, et les services dépendent des paquets, pas l'inverse.

1. **Paquets** : compare `packages/pacman.txt` et `aur.txt` à ce qui est déjà installé, n'installe que le manquant. Si aucun AUR helper (`yay`/`paru`) n'est trouvé et qu'il y a des paquets AUR à poser, prévient et laisse ces paquets de côté — installe `yay`/`paru` toi-même puis relance.
2. **Services** : active les units manquantes (`systemctl enable`), système et `--user` séparément.
3. **Dotfiles** : restaure via le `manifest.json` généré au dernier snapshot (nom → chemin d'origine complet). **Tout fichier/dossier existant à la cible est renommé en `.phoenix-bak-<timestamp>` avant écrasement — jamais de suppression sèche.**

Chaque étape demande confirmation individuelle (`o/N`), sauf avec `--yes`.

## Ce qui n'est PAS géré (volontairement, pour l'instant)

- Les **secrets** (clés SSH, tokens dans des configs) ne sont pas exclus automatiquement au-delà des patterns génériques. Vérifie `dotfiles/` avant de push sur un repo distant, surtout si public.
- Pas de rollback automatique si `restore` plante en cours de route — les backups `.phoenix-bak-*` existent, mais c'est à toi de les rebasculer manuellement pour l'instant.
- V5 (détection de divergence) n'existe pas encore : si tu modifies une config à la main sans relancer `snapshot`, `restore` n'a aucun moyen de le savoir et écrasera silencieusement au prochain restore.
