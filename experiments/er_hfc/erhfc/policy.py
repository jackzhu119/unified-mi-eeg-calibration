"""Exploratory nested leave-one-cohort-out complexity and risk prediction."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from .statistics import estimate, holm

CHOICES = ("d0", "d1", "d4", "d8", "d16", "d32")
COVARIATES = [
    "budget", "n_support", "n_left", "n_right", "support_loss", "mean_margin", "std_margin", "mean_confidence",
    "predicted_right", "separation", "eff_rank", "log_condition", "source_dist", "fisher_trace", "fisher_leading",
    "prefix_flip_d4", "effective_d4", "loo_value", "loo_available",
]
SESSION_KEYS = ["cohort", "person", "session", "budget"]


def person_weights(table):
    count = table.groupby(["cohort", "person"])["person"].transform("size").to_numpy()
    normalized = 1 / count
    return normalized / normalized.mean()


def ridge_fit(table, target, strength):
    values = table[COVARIATES].to_numpy()
    w = person_weights(table)
    scaler = StandardScaler().fit(values, sample_weight=w)
    model = Ridge(alpha=strength).fit(scaler.transform(values), target, sample_weight=w)
    return scaler, model


def policy_dataset(episodes, prefixes, certificates):
    observed = episodes[(episodes.experiment == "E02") & (episodes.panel == "common_future")
                        & (episodes.arch == "CSP") & episodes.budget.between(4, 64) & episodes.arm.isin(CHOICES)]
    if observed.empty:
        return pd.DataFrame(), pd.DataFrame()
    tracked = prefixes[prefixes.arch == "CSP"].groupby(SESSION_KEYS, sort=True).mean(numeric_only=True)
    cert = certificates[certificates.arch == "CSP"].groupby(SESSION_KEYS[:-1])["loo_balanced_gain"].mean()
    tracked["loo_value"] = cert.reindex(tracked.index.droplevel("budget")).to_numpy()
    tracked.loc[tracked.index.get_level_values("budget") != 20, "loo_value"] = np.nan
    tracked["loo_available"] = tracked.loo_value.notna().astype(int)
    tracked["loo_value"] = tracked.loo_value.fillna(0)
    seen = observed.pivot(index=SESSION_KEYS, columns="arm", values=["ba", "nll", "effective_d"])
    need = pd.MultiIndex.from_product((("ba", "nll", "effective_d"), CHOICES))
    seen = seen.reindex(columns=need).dropna()
    tracked = tracked.reindex(seen.index)
    return tracked.reset_index(), seen


def predict_policies(episodes, prefixes, certificates):
    table, observed = policy_dataset(episodes, prefixes, certificates)
    if table.empty or table.cohort.nunique() < 3:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    true_ba = observed["ba"].to_numpy()
    true_nll = observed["nll"].to_numpy()
    gains = true_ba - true_ba[:, :1]
    nll_gain = true_nll[:, :1] - true_nll
    predictors = np.c_[gains, nll_gain]
    output, risks = [], []
    groups = table.cohort.to_numpy()
    for site in sorted(set(groups)):
        training = np.flatnonzero(groups != site)
        held = np.flatnonzero(groups == site)
        scores = {}
        for penalty in (0.1, 1, 10):
            loss = []
            for inner in sorted(set(groups[training])):
                eligible = training[groups[training] != inner]
                valid = training[groups[training] == inner]
                scaler, model = ridge_fit(table.iloc[eligible], predictors[eligible], penalty)
                guess = model.predict(scaler.transform(table.iloc[valid][COVARIATES].to_numpy()))
                error = np.mean((guess - predictors[valid]) ** 2, axis=1)
                loss.append(np.average(error, weights=person_weights(table.iloc[valid])))
            scores[penalty] = np.mean(loss)
        selected = min(scores, key=scores.get)
        scaler, model = ridge_fit(table.iloc[training], predictors[training], selected)
        forecast = model.predict(scaler.transform(table.iloc[held][COVARIATES].to_numpy()))
        forecast[:, 0] = 0
        held_meta = table.iloc[held]
        margin = held_meta.mean_confidence.to_numpy()
        budget = held_meta.budget.to_numpy()
        cert_accepted = (held_meta.loo_value.to_numpy() > 0) & (held_meta.loo_available.to_numpy() > 0)
        policies = {
            "frozen_readout": np.zeros(len(held), dtype=int),
            "fixed_d4": np.full(len(held), 2),
            "fixed_budget": np.where(budget <= 8, 1, np.where(budget <= 32, 2, 3)),
            "confidence": np.where(margin > 0.65, 1, 2),
            "loo": np.where(cert_accepted, 3, 1),
            "adaptive": np.argmax(forecast[:, :len(CHOICES)], axis=1),
            "oracle": np.argmax(true_ba[held], axis=1),
        }
        for policy, chosen in policies.items():
            for i, (key, record) in enumerate(held_meta.iterrows()):
                d = chosen[i]
                output.append({k: record[k] for k in SESSION_KEYS} |
                              dict(policy=policy, arm=CHOICES[d], penalty=selected, ba=true_ba[key, d],
                                   nll=true_nll[key, d], ba_gain=gains[key, d], nll_gain=nll_gain[key, d],
                                   predicted_ba_gain=forecast[i, d], predicted_nll_gain=forecast[i, len(CHOICES) + d],
                                   severe_negative=int(gains[key, d] < -0.02),
                                   training_cohorts=",".join(sorted(set(groups[training]))),
                                   available_at_deployment=policy != "oracle"))

        # Test whether regularized effective dimension adds out-of-cohort risk information to log(B).
        dims = observed["effective_d"].to_numpy()[:, 1:]
        width = dims.shape[1]
        repeats = table.loc[table.index.repeat(width), SESSION_KEYS].reset_index(drop=True)
        edf = dims.ravel()
        base = np.log1p(repeats.budget.to_numpy())[:, None]
        ratio = edf / np.maximum(1, np.repeat(table.n_support.to_numpy(), width))
        target = (gains[:, 1:] < -0.02).ravel().astype(int)
        tr = np.flatnonzero(repeats.cohort != site)
        te = np.flatnonzero(repeats.cohort == site)
        if np.unique(target[tr]).size < 2:
            continue
        for model_name, x in (("budget", base), ("budget_and_effective_dimension", np.c_[base, edf, ratio])):
            w = person_weights(repeats.iloc[tr])
            sc = StandardScaler().fit(x[tr], sample_weight=w)
            risk_model = LogisticRegression(C=1, max_iter=200).fit(sc.transform(x[tr]), target[tr], sample_weight=w)
            probabilities = risk_model.predict_proba(sc.transform(x[te]))[:, 1]
            for i, (row, probability) in enumerate(zip(te, probabilities, strict=True)):
                risks.append(repeats.iloc[row].to_dict() | dict(model=model_name, observed=int(target[row]),
                            estimated=float(probability), arm=CHOICES[1 + row % width]))

    predictions = pd.DataFrame(output)
    risk = pd.DataFrame(risks)
    summary = []
    for site, part in predictions.groupby("cohort"):
        wc = part.groupby(["person", "policy"])[["ba", "nll", "severe_negative"]].mean().reset_index()
        for endpoint in ("ba", "nll", "severe_negative"):
            common = wc.pivot(index="person", columns="policy", values=endpoint)
            for reference in ("fixed_d4", "fixed_budget", "confidence", "loo"):
                stat = estimate(common.adaptive - common[reference], ("E06", site, endpoint, reference))
                summary.append(dict(cohort=site, metric=endpoint, comparison=f"adaptive-{reference}", **stat))
        if len(risk):
            for tag, block in risk[risk.cohort == site].groupby("model"):
                w = person_weights(block)
                auc = roc_auc_score(block.observed, block.estimated, sample_weight=w) if block.observed.nunique() == 2 else np.nan
                summary.append(dict(cohort=site, metric="risk_auc", comparison=tag, n=block.person.nunique(), delta=auc))
                summary.append(dict(cohort=site, metric="risk_log_loss", comparison=tag, n=block.person.nunique(),
                                    delta=log_loss(block.observed, block.estimated, labels=[0, 1], sample_weight=w)))
    summary = pd.DataFrame(summary)
    summary["p_holm"] = holm(summary["p"].to_numpy()) if "p" in summary else np.nan
    return predictions, risk, summary
