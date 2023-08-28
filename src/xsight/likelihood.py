# AUTOGENERATED! DO NOT EDIT! File to edit: ../../notebooks/11 - Constrained Likelihood.ipynb.

# %% auto 0
__all__ = ['console', 'key', 'tfd', 'uniform', 'truncnormal', 'normal', 'diagnormal', 'mixture_of_diagnormals',
           'mixture_of_normals', 'mixture_of_truncnormals', 'normal_logpdf', 'truncnorm_logpdf', 'truncnorm_pdf', 'min',
           'max', 'threedp3_outlier', 'get_projections_and_distances', 'get_1d_mixture_components', 'dslice', 'pad',
           'mix_std', 'make_constrained_sensor_model', 'get_data_logprobs', 'get_gaussian_blurr_weights',
           'make_blurred_sensor_model', 'ThreeDP3Outlier', 'make_baseline_sensor_model']

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 3
import jax
import jax.numpy as jnp
from   jax import (jit, vmap)
import genjax
from   genjax import gen, choice_map, vector_choice_map
import matplotlib.pyplot as plt
import numpy as np
import bayes3d
from .utils import *

console = genjax.pretty(show_locals=False)
key     = jax.random.PRNGKey(0)

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 4
import genjax._src.generative_functions.distributions.tensorflow_probability as gentfp
import tensorflow_probability.substrates.jax as tfp
tfd = tfp.distributions

uniform = genjax.tfp_uniform

truncnormal = gentfp.TFPDistribution(
    lambda mu, sig, low, high: tfd.TruncatedNormal(mu, sig, low, high));

normal = gentfp.TFPDistribution(
    lambda mu, sig: tfd.Normal(mu, sig));

diagnormal = gentfp.TFPDistribution(
    lambda mus, sigs: tfd.MultivariateNormalDiag(mus, sigs));


mixture_of_diagnormals = gentfp.TFPDistribution(
    lambda ws, mus, sig: tfd.MixtureSameFamily(
        tfd.Categorical(ws),
        tfd.MultivariateNormalDiag(mus, sig * jnp.ones_like(mus))))

mixture_of_normals = gentfp.TFPDistribution(
    lambda ws, mus, sig: tfd.MixtureSameFamily(
        tfd.Categorical(ws),
        tfd.Normal(mus, sig * jnp.ones_like(mus))))


mixture_of_truncnormals = gentfp.TFPDistribution(
    lambda ws, mus, sigs, lows, highs: tfd.MixtureSameFamily(
        tfd.Categorical(ws),
        tfd.TruncatedNormal(mus, sigs, lows, highs)))

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 5
from scipy.stats import truncnorm as scipy_truncnormal

normal_logpdf    = jax.scipy.stats.norm.logpdf
truncnorm_logpdf = jax.scipy.stats.truncnorm.logpdf
truncnorm_pdf    = jax.scipy.stats.truncnorm.pdf


# %% ../../notebooks/11 - Constrained Likelihood.ipynb 8
def get_projections_and_distances(x, ys):
    """Returns projections and distances of y's on and to ray through x."""
    
    # Projections ONTO ray through `x`
    d   = jnp.linalg.norm(x, axis=-1)
    ys_ = ys @ x / d
    
    # Distances TO ray through `x`
    ds_ = jnp.linalg.norm(ys_[...,None] * x/d - ys, axis=-1)

    return ys_, ds_

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 9
def get_1d_mixture_components(x, ys, sig):
    """Returns 1d mixture components and thier unnormalized weights."""

    # Projections serve as 1d mixture components and 
    # distances will be turned into appropriate weights
    ys_, ds_ = get_projections_and_distances(x, ys)    

    # Transform weights appropriately.
    ws_  = normal_logpdf(ds_, loc=0.0, scale=sig) + normal_logpdf(0.0, loc=0.0, scale=sig)

    return ys_, ws_

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 17
# Some helper to keep code concise
min = jnp.minimum
max = jnp.maximum


def dslice(X, i, j, w):     
    m = 2*w + 1
    return  jax.lax.dynamic_slice(X, (i, j, 0), (m, m, 3))   


def pad(X, w, val=-100.0):
    return jax.lax.pad(X,  val, ((w,w,0),(w,w,0),(0,0,0)))


def mix_std(ps, mus, stds):
    """Standard Deviation of a mixture of Gaussians."""
    return jnp.sqrt(jnp.sum(ps*stds**2) + jnp.sum(ps*mus**2) - (jnp.sum(ps*mus))**2)

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 18
# TODO: The input Y should be an array only containing range measruements as well. 
#       For this to work we need to have the pixel vectors (the rays through each pixel)

def make_constrained_sensor_model(zmax, w):
    """Returns an (untruncated) constrained sensor model marginalized over outliers."""    

    pad_val = -100.0

    @genjax.drop_arguments
    @gen
    def _sensor_model_ij(i, j, Y_, sig, outlier):

        # Note that `i,j` are at the edge of the filter window,
        # the Center is offset by `w``
        y  = Y_[i+w,j+w] 
        ys = dslice(Y_, i, j, w).reshape(-1,3)
        
        d = jnp.linalg.norm(y, axis=-1)
        ds, ws = get_1d_mixture_components(y, ys, sig)

        inlier_outlier_mix = genjax.tfp_mixture(genjax.tfp_categorical, [
                                mixture_of_normals, genjax.tfp_uniform])

        # Adjustment weights to make up for 
        # the difference to the 3dp3 model
        adj = logsumexp(ws) - jnp.log(len(ws))

        # NOTE: To compare to baseline one should set: `zmax_ = zmax``
        # zmax_ = d/y[2]*zmax
        zmax_ = zmax
        
        z = inlier_outlier_mix([jnp.log(1.0-outlier), jnp.log(outlier)], (
                                    (ws, ds, sig), 
                                    (0.0, zmax_))) @ "measurement"

        return z * y/d, adj

        
    @gen
    def sensor_model(Y, sig, outlier):   
        """
        Constrained sensor model that returns a vector of range measurements conditioned on 
        an image, noise level, and outlier probability.
        """
        Y_ = pad(Y, w, val=pad_val)

        I, J = jnp.mgrid[:Y.shape[0], :Y.shape[1]]
        I, J = I.ravel(), J.ravel()
                
        
        X, W = genjax.Map(_sensor_model_ij, (0,0,None,None,None))(I, J, Y_, sig, outlier) @ "X"
        W = W.reshape(Y.shape[:2])
        X = X.reshape(Y.shape)

        return X, W

    return sensor_model

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 19
def get_data_logprobs(tr):
    pixel_addr = lambda i: genjax.select({"X":
        genjax.index_select(i,  genjax.select("measurement"))
    })
    inds = jnp.arange(tr["X", "measurement"].shape[0])
    logps = vmap(lambda i: tr.project(pixel_addr(i)))(inds)
    return logps

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 21
def get_gaussian_blurr_weights(x, ys, sig_pix=5):
    """Gaussian blurr weights"""

    # Projections serve as 1d mixture components
    ys_ = ys @ x / jnp.linalg.norm(x, axis=-1)

    # Pixels on on canvas `[-w/2, w/2] x [-h/2,h/2]`, where
    # `w,h` are the width and height in pixels. This comes from 
    # how the renderer works, the ys alone don't carry that infromation.
    # We just assume they come from Nishad's renderer. 
    pixs   = ys/ys[:,[2]]*(100/2)
    center = x/x[2]*(100/2)
    
    # Compute gaussian blurr weights
    ds_ = jnp.linalg.norm(pixs[:,:2] - center[:2], axis=-1)
    ws_ = normal_logpdf(ds_, loc=0.0, scale=sig_pix)

    return ys_, ws_

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 25
# TODO: The input Y should be an array only containing range measruements as well. 
#       For this to work we need to have the pixel vectors (the rays through each pixel)

def make_blurred_sensor_model(zmax, w):
    """Returns an symbolic gaussian blurred sensor model (marginalized over outliers)."""    

    pad_val = -100.0

    @genjax.drop_arguments
    @gen
    def _sensor_model_ij(i, j, Y_, sig, outlier):

        # Note that `i,j` are at the edge of the filter window,
        # the Center is offset by `w``
        y  = Y_[i+w,j+w]
        d  = jnp.linalg.norm(y, axis=-1)
        ys = dslice(Y_, i, j, w).reshape(-1,3)
        
        ys_, ws_ =  get_gaussian_blurr_weights(y, ys, w)

        inlier_outlier_mix = genjax.tfp_mixture(genjax.tfp_categorical, [
                                mixture_of_normals, genjax.tfp_uniform])

        # Adjustment weights to make up for 
        # the difference to the 3dp3 model
        adj = logsumexp(ws_) - jnp.log(len(ws_))

        # NOTE: To compare to baseline one should set: `zmax_ = zmax``
        # zmax_ = d/y[2]*zmax
        zmax_ = zmax
        
        z = inlier_outlier_mix([jnp.log(1.0-outlier), jnp.log(outlier)], (
                                    (ws_, ys_, sig), 
                                    (0.0, zmax_))) @ "measurement"

        
        return z * y/d, adj

        
    @gen
    def sensor_model(Y, sig, outlier):   
        """
        Constrained sensor model that returns a vector of range measurements conditioned on 
        an image, noise level, and outlier probability.
        """
        Y_ = pad(Y, w, val=pad_val)

        I, J = jnp.mgrid[:Y.shape[0], :Y.shape[1]]
        I, J = I.ravel(), J.ravel()
                
        
        X, W = genjax.Map(_sensor_model_ij, (0,0,None,None,None))(I, J, Y_, sig, outlier) @ "X"
        W = W.reshape(Y.shape[:2])
        X = X.reshape(Y.shape)

        return X, W

    return sensor_model

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 27
from bayes3d.likelihood import threedp3_likelihood
from genjax.generative_functions.distributions import ExactDensity
from .mixtures import HeterogeneousMixture


class ThreeDP3Outlier(ExactDensity):
    def sample(self, key, y, zmax):
        u = zmax*jax.random.uniform(key)
        return u*y

    def logpdf(self, x, y, zmax):
        # We assume here that x and y linearly dependent.
        y_ = y/jnp.linalg.norm(y)
        u  = jnp.dot(x,y_)
        return genjax.tfp_uniform.logpdf(u, 0.0, zmax)


threedp3_outlier = ThreeDP3Outlier()

# %% ../../notebooks/11 - Constrained Likelihood.ipynb 28
def make_baseline_sensor_model(zmax, w):
    """Explicit version of the 3dp3 sensor model."""
  
    pad_val = -100.0

    @genjax.drop_arguments
    @gen
    def _sensor_model_ij(i, j, Y_, sig, outlier):

        # Note that `i,j` are at the edge of the filter window,
        # the Center is offset by `w``
        y  = Y_[i+w,j+w] 
        ys = dslice(Y_, i, j, w).reshape(-1,3)

        inlier_outlier_mix = HeterogeneousMixture([mixture_of_diagnormals, threedp3_outlier])

        # zmax_ = d/y[2]*zmax
        zmax_ = zmax

        m = len(ys)
        x = inlier_outlier_mix(jnp.array([1.0-outlier, outlier]), (
                                    (jnp.zeros(m), ys, sig), 
                                    (y, zmax_))) @ "measurement"

        return x, None

        
    @gen
    def sensor_model(Y, sig, outlier):   
        """Constrained sensor model."""
        Y_ = pad(Y, w, val=pad_val)

        I, J = jnp.mgrid[:Y.shape[0], :Y.shape[1]]
        I, J = I.ravel(), J.ravel()
                
        
        X,_ = genjax.Map(_sensor_model_ij, (0,0,None,None,None))(I, J, Y_, sig, outlier) @ "X"
        X = X.reshape(Y.shape)

        return X, None

    return sensor_model
