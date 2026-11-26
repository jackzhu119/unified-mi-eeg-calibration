"""Per-session jobs, with aligned support, common future IDs and explicit fallbacks."""

from hashlib import sha256
from time import perf_counter

import numpy as np
from scipy.special import expit

from .data import BUDGETS, DIMENSIONS, PANEL_CUTS
from .methods import (D_RESIDUAL, PRIOR, TRUST_CAP, LOGIT_CHANGE, intercept, fit_readout,
                      loo_gain, loo_geometry, losses, matched_controls, matrix, original_pair,
                      rates, rng, source_scores, transformed, weak_side, weights)

ALPHAS = (0, 0.25, 0.5, 0.75, 1)


def ids_hash(ids):
    return sha256("\n".join(map(str, ids)).encode()).hexdigest()


def metric(episode, common, experiment, panel, budget, arm, q, score, anchor, weak, **values):
    result = rates(episode.labels[q], score, anchor, weak)
    return common | dict(experiment=experiment, panel=panel, budget=budget, arm=arm,
                         n_query=len(q), query_left=int((episode.labels[q] == 0).sum()),
                         query_right=int((episode.labels[q] == 1).sum()),
                         query_ids_sha256=ids_hash(episode.ids[q]), **values) | result


def labeled_diagnostics(episode, s, fold, z, x):
    y, z = episode.labels[s], z[s]
    n = len(s)
    use = weights(y) is not None
    cov = episode.cov[s].mean(axis=0) if n else fold.ref
    eig = np.maximum(np.linalg.eigvalsh(cov), 1e-12)
    scale = eig / eig.sum()
    fisher_jacobian = np.sqrt(expit(z) * (1 - expit(z)))[:, None] * x[s, :16]
    mean_margin = float(np.mean(z)) if n else 0.0
    return dict(n_support=n, n_left=int((y == 0).sum()), n_right=int((y == 1).sum()),
                support_loss=float(np.mean(losses(y, z))) if n else 0.0,
                mean_margin=mean_margin, std_margin=float(np.std(z)) if n else 0.0,
                mean_confidence=float(np.mean(expit(abs(z)))) if n else 0.5,
                predicted_right=float(np.mean(z >= 0)) if n else 0.5,
                separation=float((z[y == 1].mean() - z[y == 0].mean()) / max(0.1, np.std(z))) if use else 0,
                eff_rank=float(np.exp(-np.sum(scale * np.log(scale)))),
                log_condition=float(np.log(eig[-1] / eig[0])),
                source_dist=float(np.linalg.norm(cov - fold.ref)),
                fisher_trace=float(np.square(fisher_jacobian).sum() / n) if n else 0,
                fisher_leading=float(np.linalg.svd(fisher_jacobian, compute_uv=False)[0] ** 2 / n) if n else 0)


def evaluate_grid(episode, fold, arch, common, before, run_long, *, compact=False):
    query = episode.query(PANEL_CUTS[episode.cohort])
    weak = weak_side(episode.labels[episode.support(20)], before[episode.support(20)])
    long_query = episode.query(128) if run_long else np.empty(0, dtype=int)
    rows, prefix = [], []
    b20 = None
    dims = DIMENSIONS if not compact else (0, 1, 4, 8, 32, "Full")
    selected = BUDGETS if not compact else (0, 4, 20, 64, 128)
    for budget in selected:
        primary = budget <= PANEL_CUTS[episode.cohort]
        if not primary and not run_long:
            continue
        s = episode.support(budget)
        y = episode.labels[s]
        started = perf_counter()
        z, x = transformed(fold, arch, episode.cov, episode.valid, episode.cov[s], PRIOR)
        alignment_seconds = perf_counter() - started
        if budget == 20:
            b20 = (z, x, alignment_seconds)
        fitted = {}
        for d in dims:
            design = matrix(z, x, d)
            start = perf_counter()
            fit = fit_readout(design[s], z[s], y, min_scale=d not in (0, 1))
            seconds = perf_counter() - start
            if not fit.converged:
                raise RuntimeError(f"Nested fit did not converge at B{budget} d{d}")
            fitted[d] = (design @ fit.coef, fit)
            for panel, q in (("common_future", query if primary else None),
                             ("long_common_future", long_query if run_long and d in (4, 32) else None)):
                if q is None:
                    continue
                # The long panel uses its own predeclared balanced-coverage rule.
                use = panel != "long_common_future" or (len(q) >= 20 and min(np.bincount(episode.labels[q], minlength=2)) >= 8)
                rows.append(metric(episode, common, "E02" if panel == "common_future" else "E05",
                                   panel, budget, f"d{d}", q, z[q] + fitted[d][0][q], z[q], weak,
                                   nominal_d=design.shape[1], effective_d=fit.edf, support_rms=fit.amplitude,
                                   support_count=len(s), fit_seconds=seconds, alignment_seconds=alignment_seconds,
                                   iteration_count=fit.iterations, eligible=use,
                                   fallback=("too_few_query_per_hand" if not use else
                                             "no_two_support_classes" if weights(y) is None and d != 0 else "")))
        if primary:
            delta4, fit4 = fitted[4]
            prefix.append(common | dict(budget=budget, support_ids_sha256=ids_hash(episode.ids[s]),
                                        prefix_flip_d4=float(np.mean((z[s] >= 0) != (z[s] + delta4[s] >= 0))) if len(s) else 0,
                                        effective_d4=fit4.edf)
                          | labeled_diagnostics(episode, s, fold, z, x))
        if primary and 20 <= budget and arch == "CSP":
            arms = (4, 32, "Full")
            reference = min(fitted[d][1].amplitude for d in arms)
            for d in arms:
                delta, fit = fitted[d]
                scale = reference / fit.amplitude if fit.amplitude else 0
                rows.append(metric(episode, common, "E02", "amplitude_matched", budget, f"d{d}",
                                   query, z[query] + scale * delta[query], z[query], weak,
                                   nominal_d=len(fit.coef), effective_d=fit.edf, support_rms=reference,
                                   support_count=len(s), fit_seconds=0.0, alignment_seconds=alignment_seconds,
                                   eligible=True, fallback=""))
    return rows, prefix, b20


def gate_predictions(episode, z, x, s, q, labels, geometry):
    b = intercept(labels, z[s])
    zs, zq = z[s] + b, z[q] + b
    raw, profile, info = original_pair(zs, x[s, :D_RESIDUAL], labels, episode.ids[s],
                                       zq, x[q, :D_RESIDUAL], episode.ids[q])
    start = perf_counter()
    loo = loo_gain(episode, s, labels, geometry)
    loo_seconds = perf_counter() - start
    passed = loo is not None and loo > 0
    trust = np.clip(profile, -TRUST_CAP, TRUST_CAP)
    proposals = dict(stage12=zq, matched_map=zq + raw, erfc_profile=zq + profile,
                     loo_only=zq + raw * passed, trust_only=zq + trust, full_er_hfc=zq + trust * passed)
    return proposals, info | dict(loo_balanced_gain=loo, loo_pass=passed, loo_seconds=loo_seconds)


def selective_rows(episode, common, q, zq, name):
    rows = []
    for target in (0.80, 0.95):
        if len(q) == 0:
            continue
        k = int(np.floor(target * len(q)))
        if k == 0:
            continue
        good = (zq >= 0) == episode.labels[q]
        confidence = np.argsort(-abs(zq), kind="stable")[:k]
        generator = rng(episode.key, common["fold"], name, target, "abstain")
        random = [generator.choice(len(q), size=k, replace=False) for _ in range(32)]
        rows.append(common | dict(experiment="E12", arm=name, nominal_coverage=target, realized_coverage=k / len(q),
                                  confidence_error=float((~good[confidence]).mean()),
                                  random_error=float(np.mean([(~good[idx]).mean() for idx in random])),
                                  n_issued=k, n_total=len(q), scope="offline fixed-coverage diagnostic"))
    return rows


def stage_and_gate(episode, fold, arch, common, frozen, b20, *, noisy=False, temporal=False,
                   full_factorial=False, cutoff=None):
    cut = PANEL_CUTS[episode.cohort] if cutoff is None else cutoff
    q = episode.query(20 if temporal else cut)
    iq = episode.positions[q] > cut
    primary_q = q[iq]
    s = episode.support(20)
    y = episode.labels[s]
    weak = weak_side(y, frozen[s])
    z, feature, align_sec = b20
    started = perf_counter()
    geometry = loo_geometry(episode, fold, arch, s)
    geometry_seconds = perf_counter() - started
    estimates, diagnostics = gate_predictions(episode, z, feature, s, q, y, geometry)
    base = estimates["stage12"]
    b_raw = intercept(y, frozen[s])
    started = perf_counter()
    standard, _ = transformed(fold, arch, episode.cov, episode.valid, episode.cov[s], 0)
    standard_seconds = perf_counter() - started
    s0t = frozen[q] + b_raw
    s1t = z[q]
    baseline_methods = dict(frozen=frozen[q], standard_ea=standard[q], prior_ea=s1t,
                            threshold_only=s0t, standard_ea_threshold=standard[q] + intercept(y, standard[s]))
    methods = baseline_methods | estimates
    rows = [metric(episode, common, "E01", "labeled", 20, method, primary_q, v[iq], base[iq], weak,
                   support_count=len(s), eligible=True, fallback=diagnostics["fit_status"] if method in estimates else "")
            for method, v in methods.items()]

    gated = estimates["full_er_hfc"][iq] - base[iq]
    raw = estimates["matched_map"][iq] - base[iq]
    controls, random, k = matched_controls(raw, gated, base[iq], (episode.key, arch, common["fold"]))
    mass = float(abs(gated[abs(gated) > LOGIT_CHANGE]).sum())
    for name, delta in controls.items():
        if not np.isclose(abs(delta).sum(), mass, atol=1e-8):
            raise ValueError("Mass control differs from the dual gate")
        if name == "confidence_matched" and (abs(delta) > 0).sum() != k:
            raise ValueError("Matched confidence update count differs")
    gate_common = dict(support_count=len(s), eligible=True, fallback=diagnostics["fit_status"])
    for name, val in estimates.items():
        rows.append(metric(episode, common, "E03", "gates", 20, name, primary_q, val[iq], base[iq], weak, **gate_common))
    for name, delta in controls.items():
        rows.append(metric(episode, common, "E03", "gates", 20, name, primary_q, base[iq] + delta, base[iq], weak,
                           **gate_common))
    for repetition, delta in enumerate(random):
        if (abs(delta) > 0).sum() != k or not np.isclose(abs(delta).sum(), mass, atol=1e-8):
            raise ValueError("Random gate budget does not match")
        rows.append(metric(episode, common, "E03", "gates", 20, "random_matched", primary_q,
                           base[iq] + delta, base[iq], weak, draw=repetition, **gate_common))
    for intensity in (0.0, 0.25, 0.50, 0.75, 1.0):
        rows.append(metric(episode, common, "E03", "scalar_curve", 20, f"scalar{intensity:g}", primary_q,
                           base[iq] + intensity * raw, base[iq], weak, **gate_common))

    if full_factorial:
        raw_features = np.full_like(feature, np.nan)
        raw_features[episode.valid] = np.clip(fold.features(episode.cov[episode.valid]), -8, 8)
        raw_geometry = loo_geometry(episode, fold, arch, s, use_ea=False)
        for lev1, (margins, coords, geom) in enumerate(((frozen, raw_features, raw_geometry), (z, feature, geometry))):
            for lev2 in (0, 1):
                if (lev1, lev2) == (1, 1):
                    anchor = base[iq]
                    protected = estimates["full_er_hfc"][iq]
                else:
                    offset = intercept(y, margins[s]) if lev2 else 0.0
                    hs = margins[s] + offset
                    anchor = margins[primary_q] + offset
                    _, effect, _ = original_pair(hs, coords[s, :D_RESIDUAL], y, episode.ids[s],
                                                   anchor, coords[primary_q, :D_RESIDUAL], episode.ids[primary_q])
                    cv_gain = loo_gain(episode, s, y, geom, use_threshold=bool(lev2))
                    protected = anchor + np.clip(effect, -TRUST_CAP, TRUST_CAP) * (cv_gain is not None and cv_gain > 0)
                for lev3, values in enumerate((anchor, protected)):
                    rows.append(metric(episode, common, "E01", "factorial", 20, f"S{lev1}{lev2}{lev3}", primary_q,
                                       values, frozen[primary_q], weak, support_count=len(s), eligible=True, fallback=""))

    if temporal:
        ends = np.linspace(20, episode.n_opportunities, 4).astype(int)
        for i, (start, stop) in enumerate(zip(ends[:-1], ends[1:]), 1):
            tmp = (episode.positions[q] > start) & (episode.positions[q] <= stop)
            for name in ("frozen", "prior_ea", "stage12", "matched_map", "erfc_profile", "full_er_hfc"):
                rows.append(metric(episode, common, "E08", f"time{i}", 20, name, q[tmp], methods[name][tmp],
                                   base[tmp], weak, support_count=len(s), eligible=True, fallback=""))

    if noisy:
        generator = rng(episode.key, common["fold"], "label_noise")
        for contamination in (0, 10, 20, 30):
            for draw in range(1 if contamination == 0 else 3):
                corrupt = y.copy()
                k_noise = int(round(contamination / 100 * len(y)))
                mask = generator.choice(len(y), size=k_noise, replace=False)
                corrupt[mask] ^= 1
                if contamination == 0:
                    fitted = {name: val[iq] for name, val in estimates.items()}
                else:
                    fitted, _ = gate_predictions(episode, z, feature, s, primary_q, corrupt, geometry)
                for dimension in (1, 8, 32):
                    design = matrix(z, feature, dimension)
                    update = fit_readout(design[s], z[s], corrupt, min_scale=dimension > 1)
                    if not update.converged:
                        raise RuntimeError("Noisy nested optimization failed")
                    fitted[f"d{dimension}"] = z[primary_q] + design[primary_q] @ update.coef
                for name in ("d1", "d8", "d32", "stage12", "matched_map", "erfc_profile", "full_er_hfc"):
                    rows.append(metric(episode, common, "E07", f"noise{contamination}", 20, name, primary_q,
                                       fitted[name], base[iq], weak, draw=draw, corruption=k_noise / max(1, len(s)),
                                       corruption_ids_sha256=ids_hash(episode.ids[s][mask]), support_count=len(s),
                                       eligible=True, fallback="one_class" if weights(corrupt) is None else ""))

    certificate = common | dict(support_count=len(s), query_count=len(primary_q), proposed_query_count=len(q),
                                accepted_logit=k, dual_mass=mass, prior_ea_seconds=align_sec,
                                standard_ea_seconds=standard_seconds, loo_geometry_seconds=geometry_seconds,
                                support_ids_sha256=ids_hash(episode.ids[s]),
                                weak_side=weak) | diagnostics
    raw_output = dict(ids=episode.ids[primary_q].tolist(), labels=episode.labels[primary_q].tolist(),
                      scores={k: v[iq].tolist() for k, v in methods.items()})
    engine = selective_rows(episode, common, primary_q, base[iq], "stage12")
    engine += selective_rows(episode, common, primary_q, estimates["full_er_hfc"][iq], "full_er_hfc")
    return rows, certificate, raw_output, engine


def rest_experiment(episode, fold, arch, common, cue):
    q = episode.query(64)
    points = []
    rest = source_scores(fold, arch, episode.rest, episode.valid)
    for budget in (8, 20, 64):
        s = episode.support(budget)
        raw_z = cue[q]
        actual_count = len(s)
        for name, kappa in (("rest_standard_ea", 0), ("rest_prior_ea", PRIOR)):
            shifted = fold.transport(episode.cov[q], episode.rest[s], kappa)
            z = fold.score(shifted, arch)
            points.append(metric(episode, common, "E01", "unlabeled_rest", budget, name, q, z, raw_z,
                                 None, support_count=actual_count, eligible=True, fallback=""))
            if name == "rest_prior_ea":
                rest_same_geometry = fold.transport(episode.rest[s], episode.rest[s], PRIOR)
                b = fold.score(rest_same_geometry, arch).sum() / (PRIOR + actual_count)
                points.append(metric(episode, common, "E01", "unlabeled_rest", budget, "rest_prior_ea_center", q,
                                     z - b, raw_z, None, support_count=actual_count, eligible=True, fallback=""))
        for name, z in (("frozen", raw_z), ("rest_threshold", raw_z - rest[s].sum() / (PRIOR + actual_count))):
            points.append(metric(episode, common, "E01", "unlabeled_rest", budget, name, q, z, raw_z, None,
                                 support_count=actual_count, eligible=True, fallback=""))
        for alpha in ALPHAS:
            offset = ((1 - alpha) * cue[s].sum() + alpha * rest[s].sum()) / (PRIOR + actual_count)
            points.append(metric(episode, common, "E09", "natural_alpha", budget, f"alpha{alpha:g}", q,
                                 raw_z - offset, raw_z, None, support_count=actual_count,
                                 eligible=True, fallback=""))
        i = s[s > 0]
        following = i[(episode.native[i] == episode.native[i - 1] + 1)
                      & (episode.runs[i] == episode.runs[i - 1])]
        prior_trials = following - 1
        history = episode.labels[prior_trials]
        counts = np.bincount(history, minlength=2)
        if np.any(counts < 2):
            points.append(metric(episode, common, "E09", "stress_ineligible", budget, "audit", q, raw_z, raw_z,
                                 None, support_count=len(following), eligible=False, fallback="not_two_per_hand"))
            continue
        groups = {}
        for k, new in enumerate(following):
            g = (int(episode.runs[new]), int(episode.labels[new]), bool(episode.positions[new] > budget / 2))
            groups.setdefault(g, []).append(k)
        exchangeable = [g for g in groups.values() if len(set(history[g])) > 1]
        generator = rng(episode.key, budget, "linked_rest_shuffle")
        draws = np.tile(following, (16, 1))
        for group in exchangeable:
            draws[:, group] = generator.permuted(draws[:, group], axis=1)
        for ratio in (20, 50, 80):
            right = ratio / 100
            w = 10 * np.where(history == 1, right / counts[1], (1 - right) / counts[0])
            assert np.isclose(w.sum(), 10) and np.isclose(w[history == 1].sum(), right * 10)
            cue_offset = w @ cue[prior_trials] / (PRIOR + 10)
            rest_offset = w @ rest[following] / (PRIOR + 10)
            for alpha in ALPHAS:
                bias = (1 - alpha) * cue_offset + alpha * rest_offset
                points.append(metric(episode, common, "E09", "stress_alpha", budget, f"alpha{alpha:g}", q,
                                     raw_z - bias, raw_z, None, mixture=ratio, support_count=len(following),
                                     exchangeable=sum(map(len, exchangeable)), eligible=True, fallback=""))
            for draw, shuffle in enumerate(draws):
                bias = 0.5 * (cue_offset + w @ rest[shuffle] / (PRIOR + 10))
                points.append(metric(episode, common, "E09", "stress_alpha", budget, "shuffled_alpha0.5", q,
                                     raw_z - bias, raw_z, None, mixture=ratio, draw=draw,
                                     support_count=len(following), exchangeable=sum(map(len, exchangeable)),
                                     eligible=True, fallback=""))
    return points


def evaluate_job(episode, fold, arch, task, *, extensions, factorial):
    start = perf_counter()
    common = dict(cohort=episode.cohort, person=episode.person, session=episode.session, arch=arch, fold=fold.number)
    frozen = source_scores(fold, arch, episode.cov, episode.valid)
    score_seconds = perf_counter() - start
    result = dict(metrics=[], prefix=[], certificate=None, raw=None, coverage=[], duration_seconds=0)
    if task == "rest":
        result["metrics"] = rest_experiment(episode, fold, arch, common, frozen)
    else:
        long = extensions and episode.cohort == "Stieger" and episode.session == 4 and arch == "CSP"
        rows, prefix, b20 = evaluate_grid(episode, fold, arch, common, frozen, long)
        more, cert, raw, coverage = stage_and_gate(
            episode, fold, arch, common, frozen, b20,
            noisy=extensions and episode.cohort == "Stieger" and episode.session == 4 and arch == "CSP" and fold.number == 1,
            temporal=extensions and episode.cohort in ("Stieger", "OpenBMI"),
            full_factorial=factorial,
        )
        cert["source_scoring_seconds"] = score_seconds
        result.update(metrics=rows + more, prefix=prefix, certificate=cert, raw=raw, coverage=coverage)
    result["duration_seconds"] = perf_counter() - start
    return result
