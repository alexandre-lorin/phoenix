# Guide de setup — Phoenix

De zéro à `phoenix snapshot` qui tourne. Suis l'ordre, ne saute pas d'étape.

---

## 0. Prérequis

- Arch Linux (ou dérivé pacman-based). Non testé sur autre chose, n'essaie pas.
- Python 3.11+ (`python --version` — sur Arch à jour c'est déjà le cas).
- `git` installé (`pacman -S git` si absent).
- Un AUR helper (`yay` ou `paru`) — optionnel, à installer séparément. Sans helper, `restore` signale les paquets AUR ignorés ; il n'en installe plus automatiquement.

---

## 1. Installation

```bash
git clone <ton-repo-git-phoenix> phoenix-tool
cd phoenix-tool
pip install --user -e ".[dev]"
```

Le `[dev]` installe aussi `pytest` — utile pour l'étape 3.

Vérifie que la commande est accessible :

```bash
phoenix --help
```

Si `command not found` : `~/.local/bin` n'est probablement pas dans ton `$PATH`. Ajoute dans ton `~/.bashrc`/`~/.zshrc`/`~/.config/fish/config.fish` :

```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## 2. Premier lancement

```bash
phoenix snapshot
```

Ce premier run va :
1. Créer `~/phoenix-config/` (le repo Git qui contient tout).
2. Y déposer un `phoenix.toml` avec des chemins de dotfiles **par défaut, devinés** (Hyprland, Waybar, Alacritty, fish, kitty, rofi, wlogout, gitconfig).
3. Capturer ces chemins et créer un commit. Il ne s'arrête pas après la création de la configuration. Préparer et relire `phoenix.toml` avant d'exécuter ce premier snapshot, notamment pour exclure les secrets et adapter les chemins à la machine.

**Étape obligatoire avant de faire confiance au résultat :**

```bash
$EDITOR ~/phoenix-config/phoenix.toml
```

Édite la liste `paths` sous `[dotfiles]` pour qu'elle corresponde à ta vraie structure. Exemple si tu utilises GNU Stow avec un dossier `~/dotfiles/` :

```toml
[dotfiles]
paths = [
    "~/dotfiles/hypr/.config/hypr",
    "~/dotfiles/waybar/.config/waybar",
    "~/dotfiles/alacritty/.config/alacritty",
]
```

Relance ensuite :

```bash
phoenix snapshot
```

Et vérifie ce qui a été capturé :

```bash
cat ~/phoenix-config/packages/pacman.txt | wc -l   # doit être proche du nombre de paquets réels
cat ~/phoenix-config/dotfiles/manifest.json         # doit lister tes vrais chemins
```

Si `packages/pacman.txt` est vide ou absurdement court, ou si `manifest.json` a des chemins qui n'existent pas chez toi, **ne va pas plus loin** — dis-moi l'erreur exacte.

---

## 3. Valider avec les tests

Avant de faire confiance à `restore` ou `rollback` sur du réel, fais tourner la suite de tests — elle ne touche jamais ton vrai système, tout est en environnement isolé (`tmp_path` pytest) :

```bash
cd phoenix-tool
pytest tests/ -v
```

37 tests. S'ils ne passent pas tous, quelque chose a cassé entre ce que je t'ai livré et ton environnement (version Python, etc.) — corrige avant de continuer, pas après.

---

## 4. Vérifier que le système est aligné

```bash
phoenix status
```

Doit dire `✓ Système aligné avec le dernier snapshot.` juste après un `snapshot`. Si ça affiche une divergence à ce stade, y'a un bug — pas censé arriver juste après capture.

---

## 5. Tester `restore` — JAMAIS en direct sur ta machine principale

`restore` réinstalle des paquets et écrase des dotfiles. Tu ne testes pas ça à l'aveugle sur le système que tu utilises tous les jours.

**Option recommandée : VM Arch.**

```bash
# Dans la VM, après avoir cloné/copié ton repo phoenix-config :
export PHOENIX_REPO=/chemin/vers/phoenix-config
phoenix restore --skip-aur   # d'abord sans AUR, pour limiter la casse potentielle
```

Regarde ce qui se passe à chaque étape (confirmations activées, pas de `--yes` pour ce premier test). Si tout se passe bien :

```bash
phoenix restore   # avec AUR cette fois
```

**Seulement après un restore propre en VM**, tu peux envisager `phoenix restore` sur une machine réelle fraîchement installée (le cas d'usage réel : reinstall, nouveau PC, casse système).

---

## 6. Workflow quotidien

Une fois que 1 à 5 sont validés :

```bash
phoenix snapshot     # après chaque modif de config que tu veux garder
phoenix status        # pour vérifier avant un restore ou juste par prudence
```

Idée : un cron/systemd timer qui lance `phoenix snapshot` automatiquement (ex: chaque soir). Pas fourni par défaut — à toi de le brancher si tu veux, avec un `systemd --user timer` qui appelle `phoenix snapshot`.

---

## 7. Cas d'usage avancés

### Rollback — revenir à un état antérieur du repo

```bash
phoenix rollback                # liste les 15 derniers snapshots
phoenix rollback <hash>         # ramène le REPO à cet état (le système live n'est pas touché)
phoenix restore                 # applique cet état au système, si tu veux vraiment revenir en arrière
```

### Diff entre deux machines

Utile quand tu as un deuxième poste. Récupère le repo de l'autre machine (clone Git, clé USB, peu importe) :

```bash
phoenix diff /chemin/vers/repo-de-lautre-machine
```

---

## Pièges connus (lis ça avant de râler que ça marche pas)

| Symptôme | Cause probable |
|---|---|
| `phoenix: command not found` | `~/.local/bin` pas dans `$PATH` — voir étape 1 |
| `manifest.json` vide ou chemins faux | `phoenix.toml` jamais édité après le premier run — voir étape 2 |
| `restore` plante sur les paquets AUR | Aucun `yay`/`paru`, bootstrap refusé ou échoué — relance avec `--skip-aur` puis installe un helper manuellement |
| `phoenix status` montre une divergence juste après un snapshot | Bug potentiel — remonte-le avec le message exact, pas juste "ça marche pas" |
| Dotfiles avec des secrets (clés SSH, tokens) commités dans le repo | Non géré automatiquement — vérifie `~/phoenix-config/dotfiles/` avant tout push sur un remote, surtout public |

---

## Sécurité — dernier rappel avant de push sur GitHub

Phoenix ne détecte **pas** les secrets automatiquement au-delà des patterns génériques (`*cache*`, `*.log`, etc. dans `phoenix.toml`). Si tes dotfiles contiennent des clés API, tokens, ou configs SSH en clair, **vérifie manuellement `~/phoenix-config/dotfiles/` avant de pousser sur un remote public.** Un `git log -p` rapide ou un `grep -riE "token|key|secret|password" ~/phoenix-config/dotfiles/` avant le premier push, c'est deux minutes contre une fuite.
