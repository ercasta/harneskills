from __future__ import annotations

import tomllib

from .constants import PROFILES_PATH


def _load_profiles() -> dict[str, dict]:
    if not PROFILES_PATH.exists():
        return {}
    try:
        with PROFILES_PATH.open("rb") as f:
            return tomllib.load(f).get("profiles", {})
    except Exception:
        return {}


def _save_profiles(profiles: dict[str, dict]) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for name, cfg in sorted(profiles.items()):
        lines.append(f"[profiles.{name}]")
        for key, val in cfg.items():
            if isinstance(val, bool):
                lines.append(f"{key} = {'true' if val else 'false'}")
            elif isinstance(val, (int, float)):
                lines.append(f"{key} = {val}")
            else:
                escaped = str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                lines.append(f'{key} = "{escaped}"')
        lines.append("")
    PROFILES_PATH.write_text("\n".join(lines), encoding="utf-8")
