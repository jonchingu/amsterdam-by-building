"""A small registry per stage of the quest builder, so a stage's module can be swapped by name."""


class Registry:
    def __init__(self, stage):
        self.stage = stage
        self.items = {}

    def register(self, name, obj=None):
        """Register obj under name; without obj, a decorator."""
        if obj is None:
            return lambda o: self.register(name, o)
        if name in self.items:
            raise ValueError(f"{self.stage} '{name}' is registered twice")
        self.items[name] = obj
        return obj

    def get(self, name):
        if name not in self.items:
            raise ValueError(f"unknown {self.stage} '{name}'; known: {', '.join(self.items)}")
        return self.items[name]

    def names(self):
        return list(self.items)

    def __iter__(self):
        return iter(self.items.items())


THEMES = Registry("theme")        # themes.py: what a quest is about
SOURCES = Registry("source")      # themes.py: theme → candidate checkpoints
SELECTORS = Registry("selector")  # select.py: candidates → N stops
ORDERS = Registry("order")        # order.py: stops → visiting order
PLANNERS = Registry("planner")    # route.py: steps → camera route
WRITERS = Registry("writer")      # steps.py: ordered stops → quest steps
