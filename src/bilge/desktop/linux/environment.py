"""Which display server and desktop this session runs, since the tools for each differ."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Environment:
    wayland: bool
    x11: bool
    # Lowercase names from XDG_CURRENT_DESKTOP, e.g. ("ubuntu", "gnome") or ("kde",).
    desktops: tuple[str, ...]

    @property
    def gnome(self) -> bool:
        return any(d in ("gnome", "unity", "budgie", "pantheon") for d in self.desktops)

    @property
    def kde(self) -> bool:
        return "kde" in self.desktops

    @property
    def sway(self) -> bool:
        return "sway" in self.desktops

    @property
    def hyprland(self) -> bool:
        return "hyprland" in self.desktops


def current(environ: dict[str, str] | None = None) -> Environment:
    env = os.environ if environ is None else environ
    desktops = tuple(d.strip().lower() for d in env.get("XDG_CURRENT_DESKTOP", "").split(":") if d.strip())
    return Environment(wayland=bool(env.get("WAYLAND_DISPLAY")), x11=bool(env.get("DISPLAY")), desktops=desktops)
