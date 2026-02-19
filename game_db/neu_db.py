from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


# Fallback minimal si NEU ne contient pas (ou si on n'a pas encore trouvé) la table XP
# Ça évite de casser l'UI pendant qu'on stabilise l'extraction NEU.
FALLBACK_XP_TABLES: Dict[str, List[int]] = {
    "zombie":   [5, 15, 200, 1000, 5000, 20000, 100000, 400000, 1000000],
    "spider":   [5, 25, 200, 1000, 5000, 20000, 100000, 400000, 1000000],
    "wolf":     [10, 30, 250, 1500, 5000, 20000, 100000, 400000, 1000000],
    "enderman": [10, 30, 250, 1500, 5000, 20000, 100000, 400000, 1000000],
    "blaze":    [10, 30, 250, 1500, 5000, 20000, 100000, 400000, 1000000],
    "vampire":  [20, 75, 240, 840, 2400],
}

KNOWN_BOSSES = {"zombie", "spider", "wolf", "enderman", "blaze", "vampire"}


def _load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _looks_like_xp_table(obj: Any) -> bool:
    if not isinstance(obj, list) or not obj:
        return False
    if not all(isinstance(x, (int, float)) for x in obj):
        return False
    xs = [int(x) for x in obj]
    if xs[0] < 0:
        return False
    # croissant + pas complètement délirant
    return all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1)) and xs[-1] <= 50_000_000


def _extract_tables_from_json_tree(tree: Any) -> Dict[str, List[int]]:
    """
    Heuristique: on scanne un JSON NEU et on essaie de détecter une structure qui contient
    des tables XP pour les slayers.

    On attrape :
      - {"zombie":[...], "spider":[...], ...}
      - {"zombie":{"xp":[...]}} / {"zombie":{"levels":[...]}}
      - ou des sous-arbres équivalents
    """
    out: Dict[str, List[int]] = {}

    def walk(node: Any):
        if isinstance(node, dict):
            # cas boss->list
            for k, v in node.items():
                lk = str(k).lower().strip()
                if lk in KNOWN_BOSSES and _looks_like_xp_table(v):
                    out[lk] = [int(x) for x in v]

                # cas boss->dict qui contient une liste xp/levels
                if lk in KNOWN_BOSSES and isinstance(v, dict):
                    for kk in ("xp", "levels", "xp_table", "xptable", "level_xp", "levelxp"):
                        if kk in v and _looks_like_xp_table(v[kk]):
                            out[lk] = [int(x) for x in v[kk]]

            # continue
            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for it in node:
                walk(it)

    walk(tree)
    return out


@dataclass
class NeuDB:
    repo_root: Path
    _slayer_tables: Optional[Dict[str, List[int]]] = None

    def get_slayer_xp_tables(self) -> Dict[str, List[int]]:
        """
        Renvoie boss_type -> liste XP cumulée level1..levelMax.
        Stratégie:
          - scan ciblé de JSON dans le repo NEU pour trouver les tables
          - complète avec fallback si manquant
        """
        if self._slayer_tables is not None:
            return self._slayer_tables

        tables: Dict[str, List[int]] = {}

        # Scan ciblé (on évite de parser 10k json inutiles)
        candidates: List[Path] = []
        if self.repo_root.exists():
            candidates.append(self.repo_root)

        # On cherche des noms évocateurs.
        hits: List[Path] = []
        for base in candidates:
            for p in base.rglob("*.json"):
                name = p.name.lower()
                if "slayer" in name or ("level" in name and "xp" in name):
                    hits.append(p)

        # Extraction
        for p in hits:
            tree = _load_json(p)
            if tree is None:
                continue
            found = _extract_tables_from_json_tree(tree)
            if found:
                tables.update(found)

        # complète avec fallback
        for k, v in FALLBACK_XP_TABLES.items():
            tables.setdefault(k, v)

        self._slayer_tables = tables
        return tables

    def get_slayer_xp_table(self, boss_type: str) -> List[int]:
        boss_type = (boss_type or "").lower().strip()
        return self.get_slayer_xp_tables().get(boss_type, [])
