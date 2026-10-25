"""Selection: N stops out of a theme's candidates.

Each candidate scores on how well it fits the theme (sourcing's `fit`), how notable it is (a checked fact, a story,
an article, a photo, a monument, a name) and how well it can be picked out from the air (footprint, height, how it
rises over its neighbours).

Stops are filled slot by slot. The theme's roles come first (each its count of slots, the roles in a seeded order,
but the scarce ones, 12 candidates or fewer, first of all), each from its own candidates; a role with no candidate
left is skipped and its slot goes to the theme's whole pool, which fills whatever is left. Every next stop is scored less a penalty for repeating what the set already has
(period, layer groups, architect) and for lying far from it, and must keep `gap` metres from every stop (and from the
start), stay within 2 × radius of all of them, and lie no further from its nearest stop than the cap: twice the
longest hop so far (at least 250 m, or 4 × gap), so no far-off stop is tacked onto a tight cluster. Only when no
candidate meets the cap is it dropped for that slot, and then the selector tries again (up to 8 seeded attempts) for a
set that never needs to.

The seed varies the quest by sampling, not by noise on the scores: each slot takes one of the k best candidates (k=4
by default, and only those within `margin`=0.25 of the best), uniformly, by the seed. Same seed, same data: same quest.
"""
import numpy as np

from .registry import SELECTORS

K, MARGIN = 4, 0.25
SCARCE = 12


class SelectionError(RuntimeError):
    pass


def notability(c):
    return (0.3 * c.fact.notna() + 0.2 * c.stories.map(bool) + 0.2 * c.wiki_url.notna() + 0.15 * c.image.notna()
            + 0.1 * c.monument.astype(float) + 0.05 * c.name_en.notna()).astype(float)


def visibility(c):
    size = np.sqrt(c.area.astype(float))
    return (0.4 * np.clip(size / 50, 0, 1) + 0.35 * np.clip((c.prominence - 1) / 2, 0, 1)
            + 0.25 * np.clip(c.height / 60, 0, 1)).astype(float)


def score(c):
    return (0.4 * c.fit + 0.35 * notability(c) + 0.25 * visibility(c)).to_numpy(float)


def top_k(rng, idx, gains, k=K, margin=MARGIN):
    """One of idx: uniformly among the k with the best gains, keeping only those within margin of the best."""
    o = np.argsort(-gains, kind="stable")[:max(1, k)]
    o = o[gains[o] >= gains[o[0]] - margin]
    return int(idx[o[rng.integers(len(o))]])


def slots(roles, rng, sizes=None):
    """One entry per slot the roles fill: the roles in a seeded order, those with few candidates (sizes: role name
    → count, ≤ SCARCE) first, so the stops cluster round the stops only they can give."""
    order = [roles[i] for i in rng.permutation(len(roles))]
    if sizes:
        order.sort(key=lambda r: sizes.get(r.name, 0) > SCARCE)
    return [r for r in order for _ in range(r.count)]


def leg_cap(D, S, theme):
    """How far the next stop may lie from its nearest stop: twice the set's longest hop (nearest-neighbour), and at
    least 250 m or 4 × gap."""
    floor = max(250.0, 4 * theme.gap)
    if len(S) < 2:
        return floor
    sub = D[np.ix_(S, S)] + np.diag(np.full(len(S), np.inf))
    return max(floor, 2 * sub.min(1).max())


def fill(c, n, theme, rng, roles, gain, allowed, k, margin, tries=8):
    """Slot positions into c and the role filling each (None: the theme's whole pool). Up to `tries` seeded
    attempts: the first that never had to drop the leg cap wins, else the one that dropped it least."""
    member = {r.name: c[f"role:{r.name}"].to_numpy(bool) for r in roles}
    sizes = {name: int(m.sum()) for name, m in member.items()}
    general = c["general"].to_numpy(bool) if "general" in c else np.ones(len(c), bool)
    best = None
    for _ in range(tries):
        S, R, relaxed = [], [], [0]

        def take(mask, name):
            for strict in (True, False):
                idx = np.flatnonzero(mask & allowed(S, strict))
                if len(idx):
                    S.append(top_k(rng, idx, gain(S)[idx], k, margin))
                    R.append(name)
                    relaxed[0] += not strict
                    return True
            return False

        for r in slots(roles, rng, sizes):
            if len(S) < n:
                take(member[r.name], r.name)
        while len(S) < n and take(general, None):
            pass
        if len(S) == n:
            if not relaxed[0]:
                return S, R
            if best is None or relaxed[0] < best[0]:
                best = (relaxed[0], S, R)
    return best[1:] if best else None


def prepare(cands, n, theme, start, roles, pool):
    c = cands.reset_index(drop=True)
    if len(c) < n:
        raise SelectionError(f"only {len(c)} candidates for {n} stops")
    base = score(c)
    if start is not None:  # stops near the start first: a radius away costs as much as the best notability gains
        base = base - 0.5 * np.clip(np.hypot(c.x - start[0], c.z - start[1]).to_numpy() / theme.radius, 0, 1.5)
    keep = set(np.argsort(-base, kind="stable")[:pool])
    for r in roles:  # and every role's best, however it scores against the whole pool
        m = np.flatnonzero(c[f"role:{r.name}"].to_numpy(bool))
        keep |= set(m[np.argsort(-base[m], kind="stable")[:max(pool // 5, 20)]])
    top = np.array(sorted(keep, key=lambda i: (-base[i], i)), dtype=int)
    c, base = c.iloc[top].reset_index(drop=True), base[top]
    xz = c[["x", "z"]].to_numpy()
    D = np.hypot(*(xz[:, None, :] - xz[None, :, :]).transpose(2, 0, 1))
    free = (np.ones(len(c), bool) if start is None
            else np.hypot(c.x - start[0], c.z - start[1]).to_numpy() >= theme.gap)  # never at the start itself
    return c, base, D, free


def result(c, picked, what, n, theme, cands):
    if picked is None:
        raise SelectionError(f"no {n} candidates {what} ({len(cands)} candidates)")
    S, R = picked
    out = c.iloc[S].reset_index(drop=True)
    out["role"] = R
    return out


@SELECTORS.register("balanced")
def balanced(cands, n, theme, rng, start=None, roles=(), k=K, margin=MARGIN, pool=300):
    c, base, D, free = prepare(cands, n, theme, start, roles, pool)
    gcols = [col for col in c.columns if col.startswith("g:")]
    G = c[gcols].to_numpy(float) if gcols else np.zeros((len(c), 1))
    gsum = G.sum(1)
    period = c.period.to_numpy()
    arch = c.architects.map(lambda a: a[0] if a else "").to_numpy()

    def gain(S):
        if not S:
            return base
        S = np.asarray(S)
        inter = G @ G[S].T
        union = gsum[:, None] + gsum[S][None, :] - inter
        jac = np.where(union > 0, inter / np.maximum(union, 1), 0).mean(1)
        same_period = (period[:, None] == period[S][None, :]).mean(1)
        same_arch = ((arch[:, None] == arch[S][None, :]) & (arch != "")[:, None]).mean(1)
        far = 0.2 * D[:, S].mean(1) / theme.radius + 0.15 * D[:, S].min(1) / theme.radius
        return base - (0.15 * same_period + 0.1 * jac + 0.1 * same_arch + far)

    def allowed(S, strict):
        ok = free.copy()
        if S:
            near = D[:, S].min(1)
            ok &= (near >= theme.gap) & (D[:, S].max(1) <= 2 * theme.radius)
            if strict:
                ok &= near <= leg_cap(D, S, theme)
            ok[S] = False
        return ok

    picked = fill(c, n, theme, rng, roles, gain, allowed, k, margin)
    return result(c, picked, f"within {2 * theme.radius:.0f} m of each other and {theme.gap:.0f} m apart",
                  n, theme, cands)


@SELECTORS.register("notable")
def most_notable(cands, n, theme, rng, start=None, roles=(), k=K, margin=MARGIN, pool=300):
    """The best-scoring candidates wherever they are, still `gap` apart (and the roles filled): for a city-wide
    'where is it?' quest."""
    c, base, D, free = prepare(cands, n, theme, start, roles, pool)
    period = c.period.to_numpy()

    def gain(S):
        return base if not S else base - 0.15 * (period[:, None] == period[np.asarray(S)][None, :]).mean(1)

    def allowed(S, strict):
        ok = free.copy()
        if S:
            ok &= D[:, S].min(1) >= theme.gap
            ok[S] = False
        return ok

    picked = fill(c, n, theme, rng, roles, gain, allowed, k, margin)
    return result(c, picked, f"{theme.gap:.0f} m apart", n, theme, cands)
