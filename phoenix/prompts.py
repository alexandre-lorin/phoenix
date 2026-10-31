"""
Confirmation interactive. Une seule implémentation, utilisée partout
où une action est destructive — pas de copier-coller de `input()` dispersé.
"""
from __future__ import annotations


def confirm(prompt: str, auto_yes: bool = False) -> bool:
    if auto_yes:
        print(f"[phoenix] (--yes) {prompt} → OK auto")
        return True
    answer = input(f"[phoenix] {prompt} [o/N] ").strip().lower()
    return answer in ("o", "oui", "y", "yes")
