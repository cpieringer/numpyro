import jax.numpy as np
import numpy as onp
import pytest
import scipy.special as sp
from jax import device_put, jit, lax, partial, grad
from numpy.testing import assert_allclose

from numpyro.distributions.util import xlogy, xlog1py
from numpyro.util import dual_averaging, welford_covariance

_zeros = partial(lax.full_like, fill_value=0)


@pytest.mark.parametrize('x, y', [
    (np.array([1]), np.array([1, 2, 3])),
    (np.array([0]), np.array([0, 0])),
    (np.array([[0.], [0.]]), np.array([1., 2.])),
])
@pytest.mark.parametrize('jit_fn', [False, True])
def test_xlogy(x, y, jit_fn):
    fn = xlogy if not jit_fn else jit(xlogy)
    assert np.allclose(fn(x, y), sp.xlogy(x, y))


@pytest.mark.parametrize('x, y, grad1, grad2', [
    (np.array([1., 1., 1.]), np.array([1., 2., 3.]),
     np.log(np.array([1, 2, 3])), np.array([1., 0.5, 1./3])),
    (np.array([1.]), np.array([1., 2., 3.]),
     np.sum(np.log(np.array([1, 2, 3]))), np.array([1., 0.5, 1./3])),
    (np.array([1., 2., 3.]), np.array([2.]),
     np.log(np.array([2., 2., 2.])), np.array([3.])),
    (np.array([0.]), np.array([0, 0]),
     np.array([-float('inf')]), np.array([0, 0])),
    (np.array([[0.], [0.]]), np.array([1., 2.]),
     np.array([[np.log(2.)], [np.log(2.)]]), np.array([0, 0])),
])
def test_xlogy_jac(x, y, grad1, grad2):
    assert_allclose(grad(lambda x, y: np.sum(xlogy(x, y)))(x, y), grad1)
    assert_allclose(grad(lambda x, y: np.sum(xlogy(x, y)), 1)(x, y), grad2)


@pytest.mark.parametrize('x, y', [
    (np.array([1]), np.array([0, 1, 2])),
    (np.array([0]), np.array([-1, -1])),
    (np.array([[0.], [0.]]), np.array([1., 2.])),
])
@pytest.mark.parametrize('jit_fn', [False, True])
def test_xlog1py(x, y, jit_fn):
    fn = xlog1py if not jit_fn else jit(xlog1py)
    assert_allclose(fn(x, y), sp.xlog1py(x, y))


@pytest.mark.parametrize('x, y, grad1, grad2', [
    (np.array([1., 1., 1.]), np.array([0., 1., 2.]),
     np.log(np.array([1, 2, 3])), np.array([1., 0.5, 1./3])),
    (np.array([1., 1., 1.]), np.array([-1., 0., 1.]),
     np.log(np.array([0, 1, 2])), np.array([float('inf'), 1., 0.5])),
    (np.array([1.]), np.array([0., 1., 2.]),
     np.sum(np.log(np.array([1, 2, 3]))), np.array([1., 0.5, 1./3])),
    (np.array([1., 2., 3.]), np.array([1.]),
     np.log(np.array([2., 2., 2.])), np.array([3.])),
    (np.array([0.]), np.array([-1, -1]),
     np.array([-float('inf')]), np.array([0, 0])),
    (np.array([[0.], [0.]]), np.array([1., 2.]),
     np.array([[np.log(6.)], [np.log(6.)]]), np.array([0, 0])),
])
def test_xlog1py_jac(x, y, grad1, grad2):
    assert_allclose(grad(lambda x, y: np.sum(xlog1py(x, y)))(x, y), grad1)
    assert_allclose(grad(lambda x, y: np.sum(xlog1py(x, y)), 1)(x, y), grad2)


@pytest.mark.parametrize('jitted', [True, False])
def test_dual_averaging(jitted):
    def optimize(f):
        da_init, da_update = dual_averaging(gamma=0.5)
        da_state = da_init()
        for i in range(10):
            x = da_state[0]
            g = grad(f)(x)
            da_state = da_update(g, da_state)
        x_avg = da_state[1]
        return x_avg

    f = lambda x: (x + 1) ** 2  # noqa: E731
    if jitted:
        x_opt = jit(optimize, static_argnums=(0,))(f)
    else:
        x_opt = optimize(f)

    assert_allclose(x_opt, -1., atol=1e-3)


@pytest.mark.parametrize('jitted', [True, False])
@pytest.mark.parametrize('diagonal', [True, False])
@pytest.mark.parametrize('regularize', [True, False])
def test_welford_covariance(jitted, diagonal, regularize):
    onp.random.seed(0)
    loc = onp.random.randn(3)
    a = onp.random.randn(3, 3)
    target_cov = onp.matmul(a, a.T)
    x = onp.random.multivariate_normal(loc, target_cov, size=(2000,))
    x = device_put(x)

    def get_cov(x):
        wc_init, wc_update, wc_final = welford_covariance(diagonal=diagonal)
        wc_state = wc_init(3)
        wc_state = lax.fori_loop(0, 2000, lambda i, val: wc_update(x[i], val), wc_state)
        cov = wc_final(wc_state, regularize=regularize)
        return cov

    if jitted:
        cov = jit(get_cov)(x)
    else:
        cov = get_cov(x)

    if diagonal:
        assert_allclose(cov, np.diagonal(target_cov), rtol=0.06)
    else:
        assert_allclose(cov, target_cov, rtol=0.06)
