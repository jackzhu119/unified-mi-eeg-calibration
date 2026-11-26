"""Numerical self-tests for causality guards and the matched calibration analysis."""

from pathlib import Path
import json

import numpy as np
import pandas as pd
from dataclasses import replace

from erhfc.data import BUDGETS, DIMENSIONS, PANEL_CUTS, ROSTERS, fingerprint, project
from erhfc.external import verify_release
from erhfc.experiments import gate_predictions
from erhfc.methods import (PRIOR, fit_readout, intercept, loo_geometry, matched_controls,
                           matrix, original_pair, rates, transformed, weights)
from erhfc.models import root, inverse_root
from erhfc.statistics import estimate, holm

ROOT = Path(__file__).resolve().parent


def test_real_no_label_leak(episode, fold):
    support = episode.support(20)
    probe = episode.query(64)
    z, x = transformed(fold, "CSP", episode.cov, episode.valid, episode.cov[support], PRIOR)
    geometry = loo_geometry(episode, fold, "CSP", support)
    before, _ = gate_predictions(episode, z, x, support, probe, episode.labels[support], geometry)
    masked = episode.labels.copy()
    masked[probe] ^= 1
    control = replace(episode, labels=masked)
    # The held-out labels enter rates only after the adapter has produced predictions.
    after, _ = gate_predictions(control, z, x, support, probe, control.labels[support], geometry)
    if any(not np.array_equal(before[k], after[k]) for k in before):
        raise ValueError("Changing future labels affected an adapted prediction")
    return {"passed": True, "scope": "One actual Stieger episode; held-out label inversion error check"}


def run():
    registry = json.loads((ROOT / "DATA_LINEAGE_MANIFEST.json").read_text())
    assert fingerprint(ROOT / "erhfc/original_erfc.py") == registry["source_vendor"]["sha256"]
    for source in ("EXPERIMENT_DESIGN.md", "STATISTICAL_ANALYSIS_PLAN.md", "HYPOTHESIS_REGISTRY.json", "EXPERIMENT_MATRIX.csv"):
        assert (ROOT / source).stat().st_size > 100
    task = pd.read_csv(ROOT / "EXPERIMENT_MATRIX.csv")
    assert task.task_id.is_unique and (task.default == "run").sum() == 2236
    assert len(BUDGETS) == len(DIMENSIONS) == 9 and max(BUDGETS) == 128
    assert set(ROSTERS) == set(PANEL_CUTS)

    generator = np.random.default_rng(7061)
    labels = np.tile([0, 1], 10)
    score = np.linspace(-1, 1, len(labels))
    feat = generator.normal(size=(len(labels), 91))
    assert weights(np.zeros(5)) is None and intercept(np.zeros(5), score[:5]) == 0
    for d in DIMENSIONS:
        x = matrix(score, feat, d)
        assert x.shape[1] == (93 if d == "Full" else d)
        result = fit_readout(x, score, labels, min_scale=d not in (0, 1))
        assert result.converged and 0 <= result.edf <= min(d if d != "Full" else 93, len(labels)) + 1e-10
        if d not in (0, 1):
            assert result.coef[1] > -1
    binary = rates(labels, score - 0.25, score)
    base = rates(labels, score, score)
    assert abs(binary["auc"] - base["auc"]) < 1e-14
    assert abs(binary["ba"] - base["ba"] - (binary["corrected"] - binary["introduced"])) < 1e-14
    assert np.allclose(inverse_root(project(np.eye(14))) @ root(project(np.eye(14))), np.eye(13))

    ids = np.asarray([f"s{i}" for i in range(20)])
    query = np.asarray([f"q{i}" for i in range(20)])
    raw, certified, _ = original_pair(score, feat[:, :8], labels, ids, score, feat[:, :8], query)
    raw1, cert1, _ = original_pair(score, feat[:, :8], labels, ids, score[:1], feat[:1, :8], query[:1])
    np.testing.assert_allclose([raw1[0], cert1[0]], [raw[0], certified[0]], atol=1e-10)
    assert np.all(abs(certified) <= abs(raw) + 1e-12)
    empty, empty_profile, _ = original_pair(score[:0], feat[:0, :8], labels[:0], ids[:0],
                                            score, feat[:, :8], query)
    assert not np.any(empty) and not np.any(empty_profile)
    try:
        original_pair(score, feat[:, :8], labels, ids, score, feat[:, :8], ids)
    except ValueError as error:
        assert "overlap" in str(error)
    else:
        raise AssertionError("The ERFC caller accepted intersecting prefix/future IDs")

    trial_change = np.array([0.0, .07, -.12, .3, -.4, .05, .06, .07])
    choose = np.array([0.0, 0.0, -.1, 0.0, -.2, 0.0, 0.0, .02])
    controls, resampling, n = matched_controls(trial_change, choose, np.arange(8), ("fixture",), repetitions=7)
    assert all(np.count_nonzero(v) == n for v in [controls["confidence_matched"], *resampling])
    assert all(np.isclose(abs(v).sum(), abs(choose).sum()) for v in [*controls.values(), *resampling])

    result1 = estimate(np.array([.01, .02, -.02, .03]), ("fixture",), draws=150)
    result2 = estimate(np.array([.01, .02, -.02, .03]), ("fixture",), draws=150)
    assert result1 == result2 and 0 <= result1["p"] <= 1
    np.testing.assert_allclose(holm([.01, .04, .03]), [.03, .06, .06])

    try:
        verify_release({"cohort": "Stieger"}, "sha")
    except ValueError:
        pass
    else:
        raise AssertionError("The external guard accepted an incomplete reused cohort")
    print("SELFTEST OK — vendor checksum, queue, finite readouts, no query overlap, matched gates and paired statistics")


if __name__ == "__main__":
    run()
