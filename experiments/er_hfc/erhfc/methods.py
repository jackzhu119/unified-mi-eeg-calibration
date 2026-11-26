"""Target-prefix-only fitting, original ERFC profile and proposed dual gate."""

from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter

import numpy as np
from scipy.optimize import brentq
from scipy.special import expit
from scipy.stats import rankdata

from . import original_erfc

PRIOR = 32.0
REG = 0.25
TRUST_CAP = 0.5
SEED = 20261126
PROB_CHANGE = 1e-4
LOGIT_CHANGE = 1e-9
SEVERE = 0.02
D_RESIDUAL = 8


def rng(*parts):
    digest = sha256(repr((SEED, *parts)).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


def weights(y):
    if not len(y) or len(set(y)) != 2:
        return None
    return np.where(y == 1, 0.5 / (y == 1).sum(), 0.5 / (y == 0).sum())


def losses(y, z):
    return np.logaddexp(0, z) - y * z


def intercept(y, z):
    w = weights(y)
    if w is None:
        return 0.0

    def derivative(d):
        return w @ (expit(z + d) - y) + REG * d

    return float(brentq(derivative, -32.0, 32.0, xtol=1e-10))


@dataclass(frozen=True)
class Fit:
    coef: np.ndarray
    edf: float
    amplitude: float
    iterations: int
    converged: bool


def fit_readout(x, z, y, *, min_scale=False):
    """Identically penalized, nested additive logit updates with optional positive scale."""
    beta = np.zeros(x.shape[1])
    w = weights(y)
    if w is None or not len(beta):
        return Fit(beta, 0, 0, 0, True)
    penalty = np.eye(len(beta)) * REG
    floor = -.95

    def objective(b):
        return float(w @ losses(y, z + x @ b) + REG / 2 * (b @ b))

    value = objective(beta)
    converged = False
    for iteration in range(1, 33):
        prob = expit(z + x @ beta)
        curvature = prob * (1 - prob) * w
        gradient = x.T @ (w * (prob - y)) + REG * beta
        hessian = x.T @ (curvature[:, None] * x) + penalty
        free = np.ones(len(beta), dtype=bool)
        if min_scale and beta[1] <= floor + 1e-10 and gradient[1] > 0:
            free[1] = False
        if np.max(np.abs(gradient[free])) < 1e-8:
            converged = True
            break
        direction = np.zeros_like(beta)
        direction[free] = -np.linalg.solve(hessian[np.ix_(free, free)], gradient[free])
        for step in (0.5 ** k for k in range(24)):
            trial = beta + step * direction
            if min_scale:
                trial[1] = max(floor, trial[1])
            delta = trial - beta
            proposed = objective(trial)
            if np.any(delta) and proposed <= value + 1e-4 * (gradient @ delta) + 1e-13:
                beta, value = trial, proposed
                break
        else:
            break
    if not converged:
        # A projected gradient step can recover an active-boundary Newton direction.
        lip = REG + np.linalg.norm(np.sqrt(w)[:, None] * x, ord=2) ** 2 / 4
        for extra in range(256):
            prob = expit(z + x @ beta)
            g = x.T @ (w * (prob - y)) + REG * beta
            update = beta - g / lip
            if min_scale:
                update[1] = max(floor, update[1])
            if np.max(abs(update - beta)) <= 1e-8:
                converged = True
                break
            beta = update
        iteration += extra + 1
    p = expit(z + x @ beta)
    jac = np.sqrt(w * p * (1 - p))[:, None] * x
    if min_scale and beta[1] <= floor + 1e-8:
        jac = np.delete(jac, 1, axis=1)
    covariance = jac @ jac.T if jac.shape[0] < jac.shape[1] else jac.T @ jac
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0)
    return Fit(beta, float(np.sum(eigenvalues / (eigenvalues + REG))),
               float(np.sqrt(np.mean((x @ beta) ** 2))), iteration, converged)


def matrix(z, x, d):
    if d == 0:
        return np.empty((len(z), 0))
    if d == 1:
        return np.ones((len(z), 1))
    n_pc = x.shape[1] if d == "Full" else min(d - 2, x.shape[1])
    return np.column_stack((np.ones(len(z)), z, x[:, :n_pc]))


def rates(y, z, anchor, weakness=None):
    """Classification, probabilistic and decision-transition metrics on one common probe."""
    if len(y) != len(z) or len(z) != len(anchor):
        raise ValueError("Query labels, scores and reference do not align")
    w = weights(y)
    empty = dict.fromkeys(("ba", "auc", "weak_recall", "min_recall", "nll", "left", "right",
                           "introduced", "corrected", "decision_flip", "prob_update", "called_right",
                           "delta_ba", "negative", "severe_negative"), None)
    if w is None:
        return empty
    prediction, anchor_prediction = z >= 0, anchor >= 0
    hit, old = prediction == y, anchor_prediction == y
    left, right = float(hit[y == 0].mean()), float(hit[y == 1].mean())
    rank = rankdata(z)
    n_right = int(y.sum())
    introduced, corrected = float(w @ (old & ~hit)), float(w @ (~old & hit))
    net = corrected - introduced
    return dict(ba=(left + right) / 2, left=left, right=right, min_recall=min(left, right),
                weak_recall=(left if weakness == 0 else right if weakness == 1 else None),
                auc=float((rank[y == 1].sum() - n_right * (n_right + 1) / 2) / (n_right * (len(y) - n_right))),
                nll=float(w @ losses(y, z)), introduced=introduced, corrected=corrected, delta_ba=net,
                decision_flip=float(np.mean(prediction != anchor_prediction)),
                prob_update=float(np.mean(np.abs(expit(z) - expit(anchor)) >= PROB_CHANGE)),
                called_right=float(prediction.mean()), negative=float(net < -1e-12),
                severe_negative=float(net < -SEVERE - 1e-12))


def weak_side(y, z):
    if weights(y) is None:
        return None
    left, right = np.mean(z[y == 0] < 0), np.mean(z[y == 1] >= 0)
    return int(right < left) if left != right else None


def source_scores(fold, arch, cov, valid):
    out = np.full(len(cov), np.nan)
    out[valid] = fold.score(cov[valid], arch)
    return out


def transformed(fold, arch, cov, valid, support_cov, kappa):
    scores = np.full(len(cov), np.nan)
    feats = np.full((len(cov), fold.basis.shape[1]), np.nan)
    aligned = fold.transport(cov[valid], support_cov, kappa)
    scores[valid] = fold.score(aligned, arch)
    feats[valid] = np.clip(fold.features(aligned), -8, 8)
    return scores, feats


def original_pair(zs, xs, ys, ids, zq, xq, query_ids=None, *, map_only=False):
    """Archive code receives already frozen coordinates and the common offset anchor."""
    dimension = xs.shape[1]
    config = original_erfc.Config(
        amplitude=0.3, evidence_fraction=0.10, include_intercept=False,
        mode="map" if map_only else "robust",
    )
    reference = dict(mean=np.zeros(dimension), whitener=np.eye(dimension), lengthscale=1,
                     provenance={"role": "source_pretrain_train", "coordinates": "whitened tangent PCA"})
    before = perf_counter()
    fit = original_erfc.fit(xs, zs, ys, config, reference=reference, support_ids=ids)
    fit_seconds = perf_counter() - before
    before = perf_counter()
    _, output = original_erfc.predict(fit, xq, zq, query_ids=query_ids)
    predict_seconds = perf_counter() - before
    raw = np.asarray([r.get("map_correction", 0.0) for r in output["queries"]])
    profile = np.asarray([r["correction"] for r in output["queries"]])
    if not map_only and np.any(abs(profile) > abs(raw) + 1e-10):
        raise ValueError("Archived ERFC profile exceeded its fitted MAP correction")
    return raw, profile, dict(gain=float(fit.gain), fit_status=fit.status,
                              reason_counts=output["summary"]["reason_counts"],
                              fit_seconds=fit_seconds, predict_seconds=predict_seconds)


def loo_geometry(episode, fold, arch, support, use_ea=True):
    """Cache each refit geometry; no held trial shapes its own reference."""
    cov = episode.cov[support]
    output = []
    for j in range(len(support)):
        keep = np.arange(len(support)) != j
        inputs = fold.transport(cov, cov[keep], PRIOR) if use_ea else cov
        score = fold.score(inputs, arch)
        features = np.clip(fold.features(inputs)[:, :D_RESIDUAL], -8, 8)
        output.append((keep, score, features))
    return output


def loo_gain(episode, support, labels, geometry, use_threshold=True):
    sample_weights = weights(labels)
    if sample_weights is None or min(np.bincount(labels, minlength=2)) < 2:
        return None
    delta = np.empty(len(support))
    ids = episode.ids[support]
    for j, (keep, score, features) in enumerate(geometry):
        b = intercept(labels[keep], score[keep]) if use_threshold else 0.0
        z = score + b
        raw, _, meta = original_pair(z[keep], features[keep], labels[keep], ids[keep],
                                      z[j:j + 1], features[j:j + 1], ids[j:j + 1], map_only=True)
        delta[j] = losses(labels[j], z[j]) - losses(labels[j], z[j] + raw[0])
    return float(sample_weights @ delta)


def matched_controls(raw, dual, anchor, seed_parts, repetitions=16):
    """Retrospective queries matched in count and total absolute logit movement."""
    candidates = np.flatnonzero(abs(raw) > LOGIT_CHANGE)
    k = int((abs(dual) > LOGIT_CHANGE).sum())
    if k > len(candidates):
        raise ValueError("Dual updates must be contained in the candidate pool")
    mass = float(abs(dual[abs(dual) > LOGIT_CHANGE]).sum())

    def rescale(indices):
        change = np.zeros_like(raw)
        if len(indices):
            change[indices] = raw[indices] * (mass / abs(raw[indices]).sum())
        return change

    preferred = candidates[np.argsort(abs(anchor[candidates]), kind="stable")[:k]]
    generator = rng(*seed_parts, "random_match")
    random = [rescale(generator.choice(candidates, k, replace=False)) for _ in range(repetitions)]
    return dict(confidence_matched=rescale(preferred), scalar_mass=rescale(candidates)), random, k
