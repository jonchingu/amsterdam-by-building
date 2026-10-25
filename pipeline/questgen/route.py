"""Route planning: the camera path through a quest's buildings, behind one small interface.

A planner has a name and two methods:
  plan(steps, city)   steps: a list of BAG-id lists, one per step; returns the route (a list of anchors), or None
  check(route, city)  problems with a route (an empty list when it is fine)

`flyover` is the planner s13 uses (quest_routes.py): framings checked against the 3D BAG heights, legs bent or lifted
until they clear every roof and wall. Another planner (a low drone, street level) registers next to it.
"""
from .. import quest_routes as qr
from .registry import PLANNERS


class Flyover:
    name = "flyover"

    def plan(self, steps, city):
        return qr.plan(steps, city.heights)

    def check(self, route, city):
        return [f"leg {leg + 1} passes through a building" for leg, _, _ in qr.clips(route, city.heights)]


class NoRoute:
    """No route: s13 plans one when it builds the quest set (and for quick previews)."""
    name = "none"

    def plan(self, steps, city):
        return None

    def check(self, route, city):
        return []


PLANNERS.register("flyover", Flyover())
PLANNERS.register("none", NoRoute())
