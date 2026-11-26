"""Within-cohort participant-level uncertainty and prespecified contrast families."""

import numpy as np
import pandas as pd

from .methods import rng

METRICS = ("ba", "auc", "weak_recall", "min_recall", "nll", "left", "right", "introduced",
           "corrected", "decision_flip", "prob_update", "negative", "severe_negative", "called_right", "delta_ba",
           "effective_d", "support_rms", "worst_ba", "right_drift")
KEYS = ["experiment", "panel", "cohort", "arch", "budget", "arm", "person", "session", "fold"]


def estimate(differences, key, *, null=0, alternative="two-sided", draws=10000, permutations=20000):
    diff = np.asarray(differences, dtype=float)
    diff = diff[np.isfinite(diff)]
    n = len(diff)
    result = dict(n=n, delta=float(diff.mean()) if n else np.nan, lo95=np.nan, hi95=np.nan, p=np.nan,
                  sd=float(diff.std(ddof=1)) if n > 1 else np.nan, standardized_delta=np.nan,
                  higher=int(sum(diff > 1e-12)), lower=int(sum(diff < -1e-12)), tied=int(sum(abs(diff) <= 1e-12)))
    if n < 2:
        return result
    generator = rng("paired_effect", *key)
    samples = generator.integers(0, n, size=(draws, n))
    result["lo95"], result["hi95"] = np.quantile(diff[samples].mean(axis=1), (0.025, 0.975))
    if result["sd"] > 1e-12:
        result["standardized_delta"] = result["delta"] / result["sd"]
    d = diff - null
    observed = d.sum()
    if n <= 15:
        masks = (np.arange(2 ** n)[:, None] >> np.arange(n)) & 1
        numerator_bias, denominator_bias = 0, 0
    else:
        masks = generator.integers(0, 2, size=(permutations, n), dtype=np.int8)
        numerator_bias, denominator_bias = 1, 1
    null_statistics = (2 * masks - 1) @ d
    extreme = null_statistics >= observed - 1e-12 if alternative == "greater" else abs(null_statistics) >= abs(observed) - 1e-12
    result["p"] = (int(extreme.sum()) + numerator_bias) / (len(extreme) + denominator_bias)
    return result


def holm(probabilities):
    p = np.asarray(probabilities, dtype=float)
    finite = np.flatnonzero(np.isfinite(p))
    order = finite[np.argsort(p[finite])]
    adjust = np.full_like(p, np.nan)
    sorted_values = np.minimum(1, np.maximum.accumulate(p[order] * np.arange(len(order), 0, -1)))
    adjust[order] = sorted_values
    return adjust


def merged_people(raw):
    all_rows = raw.copy()
    for k in ("draw", "worst_ba", "right_drift"):
        if k not in all_rows:
            all_rows[k] = np.nan
    good = all_rows[all_rows["eligible"].eq(True)].copy()
    stress = good[(good.experiment == "E09") & (good.panel == "stress_alpha")].copy()
    if not stress.empty:
        stress["draw"] = stress["draw"].fillna(-1)
        triple = stress.pivot(index=KEYS + ["draw"], columns="mixture", values=["ba", "called_right"])
        span = triple[["ba", "called_right"]]
        if set(span.columns.get_level_values("mixture")) != {20.0, 50.0, 80.0}:
            raise ValueError("Rest exposure triples are incomplete")
        selected = span.index.to_frame(index=False).assign(panel="stress_summary")
        selected["worst_ba"] = np.minimum(span["ba"][20].to_numpy(), span["ba"][80].to_numpy())
        base = span["called_right"][50]
        selected["right_drift"] = ((span["called_right"][20] - base).abs() +
                                    (span["called_right"][80] - base).abs()).to_numpy() / 2
        good = pd.concat([good[~((good.experiment == "E09") & (good.panel == "stress_alpha"))],
                          selected], ignore_index=True)
    present = [m for m in METRICS if m in good]
    per_fold = good.groupby(KEYS, sort=True)[present].mean().reset_index()
    # Each registered source fold and each session counts equally within a person.
    episodes = per_fold.groupby(KEYS[:-1], sort=True)[present].mean().reset_index()
    people = episodes.groupby(KEYS[:-2], sort=True)[present].mean().reset_index()
    return episodes, people


def contrasts(people):
    request = [
        ("E01", "labeled", 20, "full_er_hfc", "stage12", ("ba", "nll", "weak_recall", "min_recall")),
        ("E01", "labeled", 20, "full_er_hfc", "standard_ea_threshold", ("ba", "nll")),
        ("E01", "labeled", 20, "stage12", "frozen", ("ba", "weak_recall", "min_recall")),
        ("E01", "labeled", 20, "stage12", "prior_ea", ("ba", "nll")),
        ("E01", "labeled", 20, "stage12", "threshold_only", ("ba", "nll")),
        ("E01", "labeled", 20, "prior_ea", "standard_ea", ("ba",)),
        ("E01", "labeled", 20, "erfc_profile", "stage12", ("ba", "nll")),
        ("E01", "unlabeled_rest", 20, "rest_threshold", "frozen", ("ba", "auc", "min_recall")),
        ("E01", "unlabeled_rest", 20, "rest_prior_ea_center", "rest_threshold", ("ba", "min_recall")),
        ("E02", "common_future", 20, "d4", "d32", ("ba", "auc", "nll", "severe_negative")),
        ("E02", "amplitude_matched", 20, "d4", "d32", ("ba", "severe_negative")),
        ("E03", "gates", 20, "full_er_hfc", "matched_map", ("ba", "severe_negative", "introduced", "corrected")),
        ("E03", "gates", 20, "erfc_profile", "matched_map", ("ba", "severe_negative", "introduced", "corrected")),
        ("E03", "gates", 20, "full_er_hfc", "loo_only", ("ba", "severe_negative")),
        ("E03", "gates", 20, "full_er_hfc", "trust_only", ("ba", "severe_negative")),
        ("E03", "gates", 20, "full_er_hfc", "random_matched", ("ba", "severe_negative", "introduced", "corrected")),
        ("E03", "gates", 20, "full_er_hfc", "confidence_matched", ("ba", "severe_negative", "introduced", "corrected")),
        ("E03", "gates", 20, "full_er_hfc", "scalar_mass", ("ba", "severe_negative")),
        ("E09", "stress_summary", 20, "alpha0.5", "shuffled_alpha0.5", ("worst_ba", "right_drift")),
        *[("E09", "stress_summary", 20, "alpha0.5", f"alpha{a}", ("worst_ba", "right_drift"))
          for a in ("0", "0.25", "0.75", "1")],
        *[("E08", f"time{k}", 20, "full_er_hfc", "stage12", ("ba", "nll")) for k in (1, 2, 3)],
    ]
    rows = []
    for experiment, panel, budget, method, reference, endpoints in request:
        block = people[(people.experiment == experiment) & (people.panel == panel) & (people.budget == budget)]
        for (cohort, arch), subset in block.groupby(["cohort", "arch"], sort=True):
            for endpoint in endpoints:
                if endpoint not in subset:
                    continue
                table = subset.pivot(index="person", columns="arm", values=endpoint).reindex(columns=[method, reference]).dropna()
                if table.empty:
                    continue
                d = (table[method] - table[reference]).to_numpy()
                result = estimate(d, (experiment, panel, budget, cohort, arch, method, reference, endpoint))
                rows.append(dict(experiment=experiment, panel=panel, budget=budget,
                                 cohort=cohort, arch=arch, metric=endpoint, method=method, reference=reference,
                                 unit="nats" if endpoint == "nll" else "proportion",
                                 method_mean=table[method].mean(), reference_mean=table[reference].mean(), **result))
    # Complete three-factor contrast on the realized factorial subset.
    factors = people[(people.experiment == "E01") & (people.panel == "factorial")]
    for (cohort, arch), subset in factors.groupby(["cohort", "arch"]):
        arms = [f"S{k:03b}" for k in range(8)]
        table = subset.pivot(index="person", columns="arm", values="ba").reindex(columns=arms).dropna()
        for term in ((0, 1), (0, 2), (1, 2), (0, 1, 2)):
            contrast = np.array([np.prod([1 if arm[1 + i] == "1" else -1 for i in term]) for arm in arms])
            scale = 2 ** (3 - len(term))
            value = table.to_numpy() @ contrast / scale
            label = "interaction_" + "".join(str(k + 1) for k in term)
            rows.append(dict(experiment="E01", panel="factorial", budget=20, cohort=cohort, arch=arch, metric="ba",
                             method=label, reference="zero", unit="proportion", method_mean=float(np.mean(value)),
                             reference_mean=0., **estimate(value, ("factorial", cohort, arch, label))))
    result = pd.DataFrame(rows)
    if len(result):
        result["p_holm"] = result.groupby(["experiment", "panel"])["p"].transform(holm)
        result["analysis_role"] = "development_only"
    return result


def crossing_analysis(people):
    data = people[(people.experiment == "E05") & (people.panel == "long_common_future")]
    rows, curves = [], []
    for (site, arch), part in data.groupby(["cohort", "arch"], sort=True):
        low = part[part.arm == "d4"].pivot(index="person", columns="budget", values="ba")
        high = part[part.arm == "d32"].pivot(index="person", columns="budget", values="ba")
        vector = (high - low).drop(columns=[0], errors="ignore").dropna()
        if len(vector) < 2 or vector.shape[1] < 2:
            continue
        values = vector.to_numpy()
        levels = vector.columns.to_numpy()
        generator = rng("crossing", site, arch)
        means = values[generator.integers(0, len(values), (10000, len(values)))].mean(axis=1)
        persistent = (np.minimum.accumulate(means[:, ::-1], axis=1)[:, ::-1] > 0)
        weights_total = 0.0
        for j in range(1, len(levels)):
            probability = float(np.mean((means[:, j-1] <= 0) & persistent[:, j]))
            weights_total += probability
            rows.append(dict(cohort=site, arch=arch, n=len(vector), interval=f"{levels[j-1]}–{levels[j]}",
                             probability=probability))
        rows.append(dict(cohort=site, arch=arch, n=len(vector), interval="no_persistent_crossing",
                         probability=max(0.0, 1.0 - weights_total)))
        for j, budget in enumerate(levels):
            x = values[:, j]
            lo, hi = np.quantile(means[:, j], (0.025, 0.975))
            curves.append(dict(cohort=site, arch=arch, n=len(vector), budget=int(budget), delta=x.mean(),
                               lo95=lo, hi95=hi))
    return pd.DataFrame(rows), pd.DataFrame(curves)
