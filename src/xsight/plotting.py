# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/01 - Plotting.ipynb.

# %% auto 0
__all__ = ['rgba_from_vals', 'line_collection', 'plot_segs', 'zoom_in', 'plot_poses', 'plot_pose']

# %% ../../notebooks/01 - Plotting.ipynb 2
import matplotlib.pyplot as plt
import numpy as np
import jax.numpy as jnp
import jax

# %% ../../notebooks/01 - Plotting.ipynb 3
def rgba_from_vals(vs, q=0.0, cmap="viridis", vmin=None, vmax=None):
    if isinstance(q,list):
        v_min = np.quantile(vs, q[0])
        v_max = np.quantile(vs, q[1])
    else:
        v_min = np.quantile(vs, q)
        v_max = np.max(vs)

    if vmax is not None: v_max = vmax
    if vmin is not None: v_min = vmin

    cm  = getattr(plt.cm, cmap)
    vs_ = np.clip(vs, v_min, v_max)
    cs  = cm(plt.Normalize()(vs_))
    return cs

# %% ../../notebooks/01 - Plotting.ipynb 5
from matplotlib.collections import LineCollection


def line_collection(a, b, c=None, linewidth=1, **kwargs):
    lines = np.column_stack((a, b)).reshape(-1, 2, 2)
    lc = LineCollection(lines, colors=c, linewidths=linewidth, **kwargs)
    return lc

# %% ../../notebooks/01 - Plotting.ipynb 7
def plot_segs(segs, c="k", linewidth=1, ax=None,  **kwargs):
    if ax is None: ax = plt.gca()
    n = 10
    segs = segs.reshape(-1,2,2)
    a = segs[:,0]
    b = segs[:,1]
    lc = line_collection(a, b, linewidth=linewidth, **kwargs)
    lc.set_colors(c)
    ax.add_collection(lc)

# %% ../../notebooks/01 - Plotting.ipynb 9
def zoom_in(x, pad, ax=None):
    if ax is None: ax = plt.gca()
    ax.set_xlim(np.min(x[...,0])-pad, np.max(x[...,0])+pad)
    ax.set_ylim(np.min(x[...,1])-pad, np.max(x[...,1])+pad)

# %% ../../notebooks/01 - Plotting.ipynb 10
from .utils import unit_vec


def plot_poses(ps, sc=None,  r=0.5, clip=-1e12, cs=None, c="lightgray", cmap="viridis", ax=None, q=0.0, zorder=None, linewidth=2):
    if ax is None: ax = plt.gca()
    ax.set_aspect(1)
    ps = ps.reshape(-1,3)

    a = ps[:,:2]
    b = a + r * jax.vmap(unit_vec)(ps[:,2])

    if cs is None:
        if sc is None:
            cs = c
        else:
            sc = sc.reshape(-1)
            sc = jnp.where(jnp==-jnp.inf, clip, sc)
            sc = jnp.clip(sc, clip,  jnp.max(sc))
            sc = jnp.clip(sc, jnp.quantile(sc, q), jnp.max(sc))
            cs = getattr(plt.cm, cmap)(plt.Normalize()(sc))

            order = jnp.argsort(sc)
            a = a[order]
            b = b[order]
            cs = cs[order]



    ax.add_collection(line_collection(a,b, c=cs, zorder=zorder, linewidth=linewidth));

# %% ../../notebooks/01 - Plotting.ipynb 11
def plot_pose(p, r=0.5, c="red", ax=None,zorder=None, linewidth=2):
    if ax is None: ax = plt.gca()
    ax.set_aspect(1)
    a = p[:2]
    b = a + r*unit_vec(p[2])
    ax.plot([a[0],b[0]],[a[1],b[1]], c=c, zorder=zorder, linewidth=linewidth)

