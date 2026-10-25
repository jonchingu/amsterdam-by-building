"""Selection: N stops out of a theme's candidates.

Each candidate scores on how well it fits the theme (sourcing's `fit`), how notable it is (a checked fact, a story,
an article, a photo, a monument, a name) and how well it can be picked out from the air (footprint, height, how it
rises over its neighbours). Stops are grown greedily from a few of the best candidates: each next stop is the one
with the best score less a penalty for repeating what the set already has (period, layer groups, architect) and for
lying far from it (and from the start, if one is given); every stop stays within 2 × radius of every other and `gap` metres from it. The best set wins.

The seed shuffles near-equal candidates (a jitter of up to 0.08 on scores of about 1), so seeds give different quests
from the same theme. Same seed, same data: same quest.
"""
import numpy as np

from .registry import SELECTORS


class SelectionError(RuntimeError):
    pass


def notability(c):
    return (0.3 * c.fact.notna() + 0.2 * c.stories.map(bool) + 0.2 * c.wiki_url.notna() + 0.15 * c.image.notna()
            + 0.1 * c.monument.astype(float) + 0.05 * c.name_en.notna()).astype(float)


def visibility(c):
    size = np.sqrt(c.area.astype(float))
    return (0.4 * np.clip(size / 50, 0, 1) + 0.35 * np.clip((c.prominence - 1) / 2, 0, 1)
            + 0.25 * np.clip(c.height / 60, 0, 1)).astype(float)


def score(c, rng):
    return (0.4 * c.fit + 0.35 * notability(c) + 0.25 * visibility(c)).to_numpy() + rng.uniform(0, 0.08, len(c))


@SELECTORS.register("balanced")
def balanced(cands, n, theme, rng, start=None, pool=300, seeds=15):
    c = cands.reset_index(drop=True)
    if len(c) < n:
        raise SelectionError(f"only {len(c)} candidates for {n} stops")
    base = score(c, rng)
    if start is not None:  # stops near the start first: a radius away costs as much as the best notability gains
        base = base - 0.5 * np.clip(np.hypot(c.x - start[0], c.z - start[1]).to_numpy() / theme.radius, 0, 1.5)
    top = np.argsort(-base, kind="stable")[:pool]
    c, base = c.iloc[top].reset_index(drop=True), base[top]
    xz = c[["x", "z"]].to_numpy()
    D = np.hypot(*(xz[:, None, :] - xz[None, :, :]).transpose(2, 0, 1))
    gcols = [k for k in c.columns if k.startswith("g:")]
    G = c[gcols].to_numpy(float) if gcols else np.zeros((len(c), 1))
    period = c.period.to_numpy()
    arch = c.architects.map(lambda a: a[0] if a else "").to_numpy()

    def penalty(i, S):
        S = np.asarray(S)
        inter = G[S] @ G[i]
        union = G[S].sum(1) + G[i].sum() - inter
        jac = np.where(union > 0, inter / np.maximum(union, 1), 0).mean()
        same_arch = np.mean((arch[S] == arch[i]) & (arch[i] != ""))
        return 0.15 * np.mean(period[S] == period[i]) + 0.1 * jac + 0.1 * same_arch + 0.25 * D[i, S].mean() / theme.radius

    best = None
    for s in range(min(seeds, len(c))):
        S, total = [s], base[s]
        while len(S) < n:
            ok = (D[S].min(0) >= theme.gap) & (D[S].max(0) <= 2 * theme.radius)
            ok[S] = False
            idx = np.flatnonzero(ok)
            if not len(idx):
                break
            gains = np.array([base[i] - penalty(i, S) for i in idx])
            j = int(np.argmax(gains))
            S.append(int(idx[j]))
            total += gains[j]
        if len(S) == n and (best is None or total > best[0] + 1e-12):
            best = (total, S)
    if best is None:
        raise SelectionError(f"no {n} candidates within {2 * theme.radius:.0f} m of each other "
                             f"and {theme.gap:.0f} m apart ({len(cands)} candidates)")
    return c.iloc[best[1]].reset_index(drop=True)


@SELECTORS.register("notable")
def most_notable(cands, n, theme, rng, start=None):
    """The n best-scoring candidates wherever they are, still `gap` apart: for a city-wide 'where is it?' quest."""
    c = cands.reset_index(drop=True)
    order = np.argsort(-score(c, rng), kind="stable")
    xz = c[["x", "z"]].to_numpy()
    S = []
    for i in order:
        if all(np.hypot(*(xz[i] - xz[j])) >= theme.gap for j in S):
            S.append(int(i))
            if len(S) == n:
                return c.iloc[S].reset_index(drop=True)
    raise SelectionError(f"only {len(S)} candidates {theme.gap:.0f} m apart for {n} stops")
