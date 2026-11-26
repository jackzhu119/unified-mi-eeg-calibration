"""Aggregate checkpointed development jobs and write auditable statistical outputs."""

from pathlib import Path
import os
import tempfile

import numpy as np
import pandas as pd

from .policy import predict_policies
from .statistics import contrasts, crossing_analysis, estimate, holm, merged_people


def atomic_copy_table(frame, path):
    path = Path(path)
    suffix = ".csv.gz" if path.suffix == ".gz" else ".csv"
    handle = tempfile.NamedTemporaryFile(prefix="." + path.stem + "-", suffix=suffix, dir=path.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        frame.to_csv(temporary, index=False, compression={"method": "gzip", "mtime": 0} if suffix.endswith(".gz") else None)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def save_plot(fig, path):
    from matplotlib import pyplot as plt

    tmp = path.with_name("." + path.name + ".tmp")
    fig.savefig(tmp, format="png", dpi=160, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    tmp.replace(path)


def paired_development_noise(people):
    frame = people[people.experiment == "E07"]
    rows = []
    for (site, arch, method), selection in frame.groupby(["cohort", "arch", "arm"]):
        for metric in ("ba", "nll", "severe_negative"):
            pivot = selection.pivot(index="person", columns="panel", values=metric)
            for corrupt in ("noise10", "noise20", "noise30"):
                both = pivot.reindex(columns=[corrupt, "noise0"]).dropna()
                if both.empty:
                    continue
                result = estimate(both[corrupt] - both["noise0"], ("noise", site, arch, method, corrupt, metric))
                rows.append(dict(cohort=site, arch=arch, method=method, corruption=corrupt, metric=metric, **result))
    result = pd.DataFrame(rows)
    if not result.empty:
        result["p_holm"] = holm(result.p)
    return result


def head_comparison(raw):
    rows = []
    frame = raw[(raw.experiment == "E02") & (raw.panel == "common_future") &
                (raw.budget == 20) & (raw.arm.isin(("d4", "d32"))) & (raw.fold.isin((1, 3)))]
    for site, data in frame.groupby("cohort"):
        for metric in ("ba", "nll", "severe_negative"):
            paired = data.pivot(index=["person", "session", "fold"], columns=["arch", "arm"], values=metric)
            needed = [(a, arm) for a in ("CSP", "MDM") for arm in ("d4", "d32")]
            pair = paired.reindex(columns=pd.MultiIndex.from_tuples(needed)).dropna()
            if pair.empty:
                continue
            csp, mdm = [pair[(a, "d4")] - pair[(a, "d32")] for a in ("CSP", "MDM")]
            mean = pd.DataFrame(dict(csp=csp, mdm=mdm)).groupby("person").mean()
            rows.append(dict(cohort=site, metric=metric, csp_effect=mean.csp.mean(), mdm_effect=mean.mdm.mean(),
                             **estimate(mean.mdm - mean.csp, ("E11", site, metric))))
    table = pd.DataFrame(rows)
    if not table.empty:
        table["p_holm"] = holm(table.p)
    return table


def compare_certificate(raw, cert):
    query = raw[(raw.experiment == "E03") & (raw.panel == "gates") & raw.arm.isin(["matched_map", "stage12"])]
    keys = ["cohort", "person", "session", "arch", "fold"]
    values = query.pivot(index=keys, columns="arm", values=["ba", "nll"])
    better = values.index.to_frame(index=False)
    better["future_ba_gain"] = (values["ba"]["matched_map"] - values["ba"]["stage12"]).to_numpy()
    better["future_nll_gain"] = (values["nll"]["stage12"] - values["nll"]["matched_map"]).to_numpy()
    paired = cert.merge(better, on=keys, validate="one_to_one")
    bins = [-np.inf, 0., .002, .010, np.inf]
    paired["loo_bin"] = pd.cut(paired.loo_balanced_gain, bins, right=False)
    rows = []
    for (site, arch, bin_tag), block in paired.groupby(["cohort", "arch", "loo_bin"], observed=True):
        avg = block.groupby("person")[["future_ba_gain", "future_nll_gain", "loo_balanced_gain"]].mean()
        for metric in ("future_ba_gain", "future_nll_gain"):
            rows.append(dict(cohort=site, arch=arch, loo_bin=str(bin_tag), metric=metric,
                             mean_certificate=avg.loo_balanced_gain.mean(),
                             **estimate(avg[metric], ("loo_reliability", site, arch, str(bin_tag), metric))))
    result = pd.DataFrame(rows)
    if not result.empty:
        result["p_holm"] = holm(result.p)
    return paired, result


def visualizations(out, people, effects, curve, policy_summary, reliability):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    site_names = sorted(people.cohort.unique())
    grid = people[(people.experiment == "E02") & (people.panel == "common_future") & (people.arch == "CSP")]
    fig, axes = plt.subplots(1, len(site_names), figsize=(5 * len(site_names), 4.0), squeeze=False, layout="constrained")
    for ax, site in zip(axes[0], site_names, strict=True):
        table = grid[grid.cohort == site].groupby(["budget", "arm"])["delta_ba"].mean().unstack("arm")
        arm_order = [d for d in ("d0", "d1", "d2", "d4", "d8", "d16", "d32", "d64", "dFull") if d in table.columns]
        chart = ax.imshow(100 * table[arm_order].to_numpy().T, cmap="RdBu", vmin=-8, vmax=8, aspect="auto")
        ax.set(xticks=list(range(len(table))), xticklabels=table.index, yticks=list(range(len(arm_order))),
               yticklabels=arm_order, xlabel="Acquired trial positions", title=site)
    fig.colorbar(chart, ax=axes.ravel().tolist(), shrink=.78, label="Balanced accuracy change, pp")
    fig.suptitle("CSP/LDA calibration vs aligned frozen readout")
    save_plot(fig, out / "Budget-Dimension.png")

    if len(curve):
        fig, ax = plt.subplots(figsize=(6.6, 3.6), layout="constrained")
        for (site, arch), data in curve.groupby(["cohort", "arch"]):
            ax.plot(data.budget, 100 * data.delta, color="#186799", marker="o", label=f"{site} {arch}")
            ax.fill_between(data.budget, 100 * data.lo95, 100 * data.hi95, color="#186799", alpha=.18)
        ax.axhline(0, color="#777777", ls="--")
        ax.set(xlabel="Acquired trial positions", ylabel="Difference, pp", title="Long probe: d32 minus d4 BA")
        ax.legend(loc="best")
        save_plot(fig, out / "Long-Prefix.png")

    if len(effects):
        forest = effects[(effects.experiment == "E01") & (effects.panel == "labeled") &
                         (effects.metric == "ba") & (effects.method == "full_er_hfc") & (effects.reference == "stage12")]
        if len(forest):
            fig, ax = plt.subplots(figsize=(6.8, max(3.2, len(forest) * .45 + 1.0)), layout="constrained")
            for idx, (_, row) in enumerate(forest.iterrows()):
                ax.plot([100 * row.lo95, 100 * row.hi95], [idx, idx], color="#327086")
                ax.scatter(100 * row.delta, idx, color="#17485B")
            ax.axvline(0, color="#7A8389", ls="--")
            ax.set(yticks=np.arange(len(forest)), yticklabels=[f"{r.cohort}  {r.arch}  n={r.n}" for r in forest.itertuples()],
                   xlabel="Paired BA change, percentage points", title="ER-HFC dual versus alignment and threshold")
            save_plot(fig, out / "Cohort-Forest.png")

    profiles = people[(people.experiment == "E03") & people.panel.isin(("gates", "scalar_curve")) & (people.arch == "CSP")]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.7), layout="constrained")
    for site, subset in profiles[profiles.panel == "scalar_curve"].groupby("cohort"):
        curve = subset.groupby("arm")[["prob_update", "delta_ba", "severe_negative"]].mean().sort_index()
        for ax, outcome in zip(axes, ("delta_ba", "severe_negative"), strict=True):
            ax.plot(100 * curve.prob_update, 100 * curve[outcome], linestyle=":", linewidth=1.2, alpha=.65)
    for (site, arm), subset in profiles.groupby(["cohort", "arm"]):
        if arm.startswith("scalar") and arm != "scalar_mass":
            continue
        fill = "o" if arm == "full_er_hfc" else "x"
        for ax, column in zip(axes, ("delta_ba", "severe_negative"), strict=True):
            ax.scatter(100 * subset.prob_update.mean(), 100 * subset[column].mean(), marker=fill, alpha=.65,
                       label=site if arm == "full_er_hfc" else None)
    axes[0].set(xlabel="Probability changes ≥ 0.0001, %", ylabel="Balanced accuracy change, pp")
    axes[1].set(xlabel="Probability changes ≥ 0.0001, %", ylabel="Sessions with BA loss > 2 pp, %")
    axes[1].legend(fontsize=8)
    fig.suptitle("Gate coverage, accuracy and negative transfer (CSP/LDA)")
    save_plot(fig, out / "Gate-Tradeoff.png")

    comparison = profiles[(profiles.panel == "gates") & profiles.arm.isin(["matched_map", "full_er_hfc"])]
    if len(comparison):
        fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.6), layout="constrained")
        for ax, (arm, values) in zip(axes, comparison.groupby("arm", sort=True), strict=True):
            for site, group in values.groupby("cohort"):
                ax.scatter(100 * group.introduced, 100 * group.corrected, alpha=.55, label=site)
            maximum = max(0.5, 100 * values[["introduced", "corrected"]].max().max())
            ax.plot([0, maximum], [0, maximum], color="#888888", linestyle="--")
            ax.set(xlabel="Introduced errors, pp", ylabel="Corrected errors, pp", title=arm.replace("_", " "))
        axes[0].legend(fontsize=8)
        save_plot(fig, out / "Error-Transitions.png")

    if len(reliability):
        fig, ax = plt.subplots(figsize=(6.6, 3.8), layout="constrained")
        panel = reliability[(reliability.arch == "CSP") & (reliability.metric == "future_nll_gain")]
        for site, group in panel.groupby("cohort"):
            selection = group.sort_values("mean_certificate")
            ax.plot(selection.mean_certificate, selection.delta, marker="o", label=site)
        ax.axhline(0, color="#888888", ls="--")
        ax.set(xlabel="Mean support-only LOO gain, nats", ylabel="Observed future gain, nats", title="Certificate reliability")
        ax.legend(fontsize=8)
        save_plot(fig, out / "Certificate-Reliability.png")

    if len(policy_summary) and (policy_summary.metric == "ba").any():
        panel = policy_summary[(policy_summary.metric == "ba") & (policy_summary.comparison == "adaptive-fixed_d4")]
        fig, ax = plt.subplots(figsize=(6.6, 3.5), layout="constrained")
        ax.bar(panel.cohort, 100 * panel.delta, color="#2B617B")
        ax.vlines(panel.cohort, 100 * panel.lo95, 100 * panel.hi95, color="#142A38")
        ax.axhline(0, color="#888888", ls="--")
        ax.set(ylabel="Paired BA change, pp", title="Cross-cohort complexity policy versus fixed d4")
        save_plot(fig, out / "Policy-Prediction.png")


def report_text(out, stat, mode, completed, planned, missing, summary, crossing, policy_summary):
    pilot = mode == "pilot"
    heading = "# ER-HFC 科研结果核对" if not pilot else "# ER-HFC 真实数据试跑"
    lines = [heading, "", f"{completed}/{planned} 个作业完成。{len(missing)} 个作业失败。",
             f"当前输出用于{'实现与资源核验' if pilot else '既有队列的开发与跨库压力测试'}。独立确认性证据待 E04。",
             "", "## 沿用历史支持什么", "",
             "R9 与 R10 支持提示前状态与紧邻试次有关。历史等权混合的短前缀压力效应低于实用门槛。",
             "", "## B20 全方法与简单基线", ""]
    table = stat[(stat.experiment == "E01") & (stat.panel == "labeled") & (stat.metric == "ba") &
                 (stat.method == "full_er_hfc") & (stat.reference == "stage12")] if len(stat) else stat
    if not pilot and len(table):
        lines.extend(["| 队列 | 读出 | 人数 | BA 差，百分点 | 95% CI | Holm p |", "|---|---|---:|---:|---|---:|"])
        for row in table.itertuples():
            lines.append(f"| {row.cohort} | {row.arch} | {row.n} | {100*row.delta:+.3f} | {100*row.lo95:+.3f} 至 {100*row.hi95:+.3f} | {row.p_holm:.4g} |")
    else:
        lines.append("试跑只检查评分流程和覆盖稳定性。主比较将在全矩阵完成后解释。")
    if not pilot and len(stat):
        lines.extend(["", "## 自由度、保护及可预测性", "",
                      "下表的正差代表表头所述指标增加。负迁移率及 NLL 降低时为改善。所有推断限于已使用的队列。",
                      "", "| 实验 | 数据 | 读出 | 比较 | 指标 | 配对人数 | 差值 | Holm p |",
                      "|---|---|---|---|---|---:|---:|---:|"])
        focus = stat[((stat.experiment == "E02") & stat.metric.isin(["ba", "severe_negative"])) |
                     ((stat.experiment == "E03") & stat.method.eq("full_er_hfc") &
                      stat.reference.isin(["matched_map", "random_matched", "confidence_matched"]) &
                      stat.metric.isin(["ba", "severe_negative"]))]
        for row in focus.itertuples():
            lines.append(f"| {row.experiment} {row.panel} | {row.cohort} | {row.arch} | {row.method} − {row.reference} | "
                         f"{row.metric}，pp | {row.n} | {100*row.delta:+.3f} | {row.p_holm:.4g} |")
        if len(crossing):
            stable = crossing[crossing.interval == "no_persistent_crossing"]
            for row in stable.itertuples():
                lines.append(f"\n{row.cohort} 长探针上，bootstrap 无持续转折的比例为 {row.probability:.1%}，配对 {row.n} 人。")
        if len(policy_summary):
            rows = policy_summary[(policy_summary.metric == "ba") & (policy_summary.comparison == "adaptive-fixed_d4")]
            for row in rows.itertuples():
                lines.append(f"\n留出 {row.cohort} 时，自适应策略相对固定 d4 的 BA 差为 {100*row.delta:+.2f} 个百分点，"
                             f"95% CI [{100*row.lo95:+.2f}, {100*row.hi95:+.2f}]。")
        lines.extend(["", "标签污染、安全和时间窗结果分别见 Noise-Effects、Paired-Effects 及各队列工程表。查阅全部对照时同时保留阴性与不确定结果。"])
    lines.extend(["", "## 后续解释边界", "",
                  "数据谱系、阴性效应与排程敏感性应和所有阳性效应一起读。E04 才能支持独立复验。"
                  "S3 只有在同锚、匹配更新预算下提供额外净收益，才适合作为主要算法贡献。"
                  "低自由度表现需结合样本数、支持有效维度、会话风险和跨读出一致性解释。",
                  "", f"OpenBMI 两天位置标签完全重复人数为 {summary['openbmi_identical_label_schedules']}。",
                  "基础模型重复使用与预训练来源需另行确认，当前主矩阵只比较 CSP/LDA 与 MDM。",
                  ""])
    (out / "SCIENTIFIC_DISCOVERY_REPORT_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "PAPER_INNOVATION_UPDATE_ZH.md").write_text(
        "# ER-HFC 贡献核对\n\n"
        "首先用 E01 查完整方法相对强简单基线的净收益，用 E03 检验同等更新预算下的保护增益。"
        "若两项欠缺，保留 S3 为可选机制，并查看 E02、E05 和 E06 是否支持明确的复杂度与风险关系。"
        "结果范围取决于独立 E04；现有开发数据不足以声称跨人群普适。\n", encoding="utf-8")
    negative = stat[(stat.metric.isin(["ba", "worst_ba"])) & ((stat.hi95 <= 0) | (stat.lo95 <= 0))] if len(stat) else stat
    atomic_copy_table(negative, out / "Nonpositive-or-Uncertain-Contrasts.csv")


def prepare_report(out, results, *, mode, planned, missing, audit_summary):
    raw = pd.DataFrame(r for saved in results for r in saved["metrics"])
    prefix = pd.DataFrame(r for saved in results for r in saved["prefix"])
    cert = pd.DataFrame(saved["certificate"] for saved in results if saved["certificate"] is not None)
    coverage = pd.DataFrame(r for saved in results for r in saved["coverage"])
    episodes, people = merged_people(raw)
    effects = contrasts(people)
    crossing, curve = crossing_analysis(people)
    policy, risk, policy_summary = predict_policies(episodes, prefix, cert)
    reliability_data, reliability = compare_certificate(raw, cert)
    engineering = cert.groupby(["cohort", "arch"])[
        ["support_count", "query_count", "accepted_logit", "dual_mass", "source_scoring_seconds", "prior_ea_seconds",
         "standard_ea_seconds", "fit_seconds", "predict_seconds", "loo_geometry_seconds", "loo_seconds"]].agg(["median", "mean"])
    engineering.columns = ["_".join(pair) for pair in engineering.columns]
    public = effects.drop(columns=["higher", "lower", "tied"], errors="ignore").copy()
    if len(public):
        public = public[public.n >= 10]
    entries = {
        "Fold-Metrics.csv.gz": raw, "Participant-Metrics.csv.gz": people, "Session-Metrics.csv.gz": episodes,
        "Paired-Effects.csv": effects, "Prefix-Features.csv.gz": prefix, "Certificate-Observations.csv.gz": reliability_data,
        "Certificate-Reliability.csv": reliability, "Crossing-Intervals.csv": crossing, "Crossing-Curve.csv": curve,
        "Noise-Effects.csv": paired_development_noise(people), "Cross-Readout-Effects.csv": head_comparison(raw),
        "Policy-Per-Session.csv.gz": policy, "Negative-Transfer-Predictions.csv.gz": risk,
        "Policy-Paired-Effects.csv": policy_summary, "Engineering.csv": engineering.reset_index(),
        "Fixed-Coverage.csv": coverage, "Publication-Candidate-Aggregates.csv": public,
        "Full-Method-Ablation.csv": people[(people.experiment == "E01") & (people.panel == "factorial")],
    }
    for name, table in entries.items():
        atomic_copy_table(table, out / name)
    visualizations(out, people, effects, curve, policy_summary, reliability)
    report_text(out, effects, mode, len(results), planned, missing, audit_summary, crossing, policy_summary)
    return len(raw), len(people), len(effects)
