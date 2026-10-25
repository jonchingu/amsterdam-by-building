"""Thematic quest builder: quests generated from the building directory the pipeline already holds.

Stages, each a registry of swappable modules (registry.py):

  themes.py   THEMES, SOURCES    a theme is filters and scores over the buildings' attributes; sourcing yields its
                                 candidate checkpoints
  select.py   SELECTORS          N stops: the theme's roles first, then notable, varied, visible from the air, close
                                 together; seeded by sampling among each slot's best
  order.py    ORDERS             visiting order: nearest neighbour and 2-opt, from a start point if given
  route.py    PLANNERS           the camera route (quest_routes.py's flyover, checked against the 3D BAG heights)
  steps.py    WRITERS            find / where / year / choice steps from the data alone

city.py loads the directory; build.py runs the stages and checks the result with s13_quests' own checks.
CLI: python -m pipeline.questgen --help
"""
from . import order, route, select, steps, themes  # noqa: E402,F401  (each module registers itself)
