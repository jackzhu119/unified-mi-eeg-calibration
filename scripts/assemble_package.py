#!/usr/bin/env python3
"""
Assembles the complete unified repository structure:
1. Extracts locked result files from the three source repositories into evidence_archive/
2. Generates DATA_LINEAGE_MANIFEST.json with exact Git branch, commit SHA, and SHA-256 provenance
3. Organizes manuscript/{en,zh,supplementary}/, docs/, figures/{png,pdf,svg}/, and scripts/
4. Compiles EN/ZH manuscript and Supplementary Materials DOCX/PDF deliverables
"""

import csv
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("UNIFIED_PACKAGE_ROOT", Path(__file__).resolve().parent.parent))
REPOS_BASE = Path(os.environ.get("MI_EEG_REPOS_DIR", ROOT.parent))
REPOS = {
    "cross-subject-mi-eeg": {
        "local": REPOS_BASE / "cross-subject-mi-eeg",
        "url": "https://github.com/jackzhu119/cross-subject-mi-eeg",
    },
    "few-shot-mi-eeg": {
        "local": REPOS_BASE / "few-shot-mi-eeg",
        "url": "https://github.com/jackzhu119/few-shot-mi-eeg",
    },
    "research3": {
        "local": REPOS_BASE / "research3",
        "url": "https://github.com/jackzhu119/research3",
    },
}

EXTRACTIONS = [
    # Regime I: Zero-Shot Cross-Subject Transfer (cross-subject-mi-eeg)
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/ELIGIBLE_V3_RESULTS_20261018/audits/external/neural_recomputed_condition_summaries.csv",
     "Study1A_ELIGIBLE_V3_neural_condition_summaries.csv"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/ELIGIBLE_V3_RESULTS_20261018/audits/external/neural_recomputed_comparisons.csv",
     "Study1A_ELIGIBLE_V3_neural_comparisons.csv"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/ELIGIBLE_V3_RESULTS_20261018/audits/external/neural_recomputed_paired_differences.csv",
     "Study1A_ELIGIBLE_V3_neural_paired_differences.csv"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/ELIGIBLE_V3_RESULTS_20261018/audits/external/csp_recomputed_condition_summaries.csv",
     "Study1A_ELIGIBLE_V3_csp_condition_summaries.csv"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/ELIGIBLE_V3_RESULTS_20261018/RESULTS_REVIEW_zh.md",
     "Study1A_ELIGIBLE_V3_RESULTS_REVIEW_zh.md"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/PAPER1_IJBET_20261029/evidence/objective_results_table.json",
     "Study1B_risk_v1_objective_results_table.json"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/PAPER1_IJBET_20261029/figure_data/Fig1_primary_participant_changes.csv",
     "Study1A_Dreyer85_primary_participant_changes.csv"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/PAPER1_IJBET_20261029/figure_data/Fig2_objective_profiles.csv",
     "Study1B_risk_v1_objective_profiles.csv"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/PAPER1_IJBET_20261029/figure_data/Study2_nested_outer_source.json",
     "Study1B_risk_v1_nested_outer_source.json"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/PAPER1_IJBET_20261029/figure_data/Study2_external_fixed40_source.json",
     "Study1B_risk_v1_external_fixed40_source.json"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/main",
     "research_runs/PAPER1_IJBET_20261029/supporting_data/Study1_frozen_comparisons.csv",
     "Study1A_frozen_comparisons.csv"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/hpc/paper1-composition-v2",
     "hpc_status/paper1-composition-v2/status.json",
     "Study1C_composition_v2_status.json"),
    ("regime1_zero_shot", "cross-subject-mi-eeg", "origin/hpc/paper1-composition-v2",
     "research_runs/PAPER1_COMPOSITION_20261027/PROTOCOL.md",
     "Study1C_composition_v2_PROTOCOL.md"),

    # Regime II: Few-Label Longitudinal Cross-Session Recalibration (few-shot-mi-eeg)
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/bmt_alignment_integrated_20261104/figures/Fig2_performance.csv",
     "Study2A_Fig2_component_performance.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/bmt_alignment_integrated_20261104/figures/Fig3_error_coverage.csv",
     "Study2B_Fig3_error_redistribution_coverage.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/bmt_alignment_integrated_20261104/figures/Fig4_budget.csv",
     "Study2_Fig4_budget_curves.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/bmt_alignment_integrated_20261104/figures/Fig5_mechanisms.csv",
     "Study2CD_Fig5_geometry_and_window_mechanisms.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/jne_alignment_20261104/UPLOAD_FILES/Supplementary_Results.csv",
     "Study2_Supplementary_Results_All_Contrasts.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/jne_alignment_20261104/UPLOAD_FILES/Supplementary_Saved_Records.csv",
     "Study2_Supplementary_Saved_Records.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/bmt_submission_20261028/figures/Fig2_geometry_source_data.csv",
     "Study2C_geometry_source_data.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "manuscript/bmt_submission_20261028/figures/Fig3_neural_normalization_source_data.csv",
     "Study2E_DiscoveryV3_neural_normalization_source_data.csv"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "training_status/paper2-discovery-v3/STATUS.json",
     "Study2E_DiscoveryV3_126tasks_STATUS.json"),
    ("regime2_longitudinal", "few-shot-mi-eeg", "origin/research/paper2-alignment-integrated-revision",
     "training_status/paper2-recalibration-v2/STATUS.json",
     "Study2E_DiscoveryV2_24tasks_STATUS.json"),

    # Regime III: Prefix Neural, Manifold, & ERFC Functional Calibration (research3)
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/bmte-error-redistribution-20261029/tables/cohort_summary.csv",
     "BMTE_cohort_summary.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/bmte-error-redistribution-20261029/tables/component_summary.csv",
     "BMTE_component_summary.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/bmte-error-redistribution-20261029/tables/key_claims.json",
     "BMTE_51condition_error_redistribution_key_claims.json"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/bmte-error-redistribution-20261029/tables/neural_distributions_B20.csv",
     "BMTE_51condition_neural_distributions_B20.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/bmte-error-redistribution-20261029/tables/neural_paired_contrasts.csv",
     "BMTE_neural_paired_contrasts.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/bmte-error-redistribution-20261029/tables/source_extension_seed_metrics.csv",
     "BMTE_source_extension_seed_metrics.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/Table1_cohorts.csv",
     "ERFC_Table1_cohorts.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/Table2_accuracy.csv",
     "ERFC_Table2_accuracy.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/Table3_mechanism.csv",
     "ERFC_Table3_selectivity_mechanism.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r10_method_budget_summaries_verified.csv",
     "Round10_ERFC_method_budget_summaries_verified.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r10_primary_comparisons_verified.csv",
     "Round10_ERFC_primary_comparisons_verified.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r10_exploratory_matched_map_mechanisms.csv",
     "Round10_ERFC_18mechanisms_vs_matched_map.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r10_profile_configuration.json",
     "Round10_ERFC_profile_configuration.json"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r3_primary_comparisons_verified.csv",
     "Round03_Schur_protection_primary_comparisons_verified.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r3_protection_participant_differences.csv",
     "Round03_Schur_protection_participant_differences.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r7_primary_comparisons_verified.csv",
     "Round07_spatiotemporal_Lie_primary_comparisons.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r12_verified_primary_comparisons.csv",
     "Round12_evidence_ranking_primary_comparisons.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "manuscripts/brain-sciences-erfc-20261029/tables/r13_verified_primary_statistics.csv",
     "Round13_session_persistence_primary_statistics.csv"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "docs/EXPERIMENT_STATUS.json",
     "Rounds01_to_09_EXPERIMENT_STATUS.json"),
    ("regime3_prefix_erfc", "research3", "origin/main",
     "docs/LIVE_STATUS.json",
     "Rounds01_to_13_LIVE_STATUS.json"),
]


def get_commit_sha(repo_path: Path, branch: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", branch], cwd=repo_path, text=True
    ).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    # 1. Create categorized directories
    for d in [
        ROOT / "manuscript" / "en",
        ROOT / "manuscript" / "zh",
        ROOT / "manuscript" / "supplementary",
        ROOT / "docs",
        ROOT / "figures" / "png",
        ROOT / "figures" / "pdf",
        ROOT / "figures" / "svg",
        ROOT / "scripts",
        ROOT / "evidence_archive" / "regime1_zero_shot",
        ROOT / "evidence_archive" / "regime2_longitudinal",
        ROOT / "evidence_archive" / "regime3_prefix_erfc",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Move/organize manuscript, doc, figure, & script files
    moves = [
        (ROOT / "unified_manuscript_en.md", ROOT / "manuscript" / "en" / "Unified_MIEEG_Manuscript_EN.md"),
        (ROOT / "Unified_MIEEG_Manuscript_EN.pdf", ROOT / "manuscript" / "en" / "Unified_MIEEG_Manuscript_EN.pdf"),
        (ROOT / "Unified_MIEEG_Manuscript_EN.docx", ROOT / "manuscript" / "en" / "Unified_MIEEG_Manuscript_EN.docx"),
        (ROOT / "unified_manuscript_zh.md", ROOT / "manuscript" / "zh" / "Unified_MIEEG_Manuscript_ZH.md"),
        (ROOT / "Unified_MIEEG_Manuscript_ZH.docx", ROOT / "manuscript" / "zh" / "Unified_MIEEG_Manuscript_ZH.docx"),
        (ROOT / "Supplementary_Materials_EN.md", ROOT / "manuscript" / "supplementary" / "Supplementary_Materials_EN.md"),
        (ROOT / "Supplementary_Materials_EN.pdf", ROOT / "manuscript" / "supplementary" / "Supplementary_Materials_EN.pdf"),
        (ROOT / "Supplementary_Materials_EN.docx", ROOT / "manuscript" / "supplementary" / "Supplementary_Materials_EN.docx"),
        (ROOT / "master_experimental_synthesis_zh.md", ROOT / "docs" / "master_experimental_synthesis_zh.md"),
        (ROOT / "merger_master_plan_zh.md", ROOT / "docs" / "merger_master_plan_zh.md"),
        (ROOT / "build_svg_figures.py", ROOT / "scripts" / "build_svg_figures.py"),
    ]
    for src, dst in moves:
        if src.exists():
            shutil.copy2(src, dst)
            src.unlink()

    # Optional external plan copy when MERGER_PLAN_PATH is explicitly provided
    plan_env = os.environ.get("MERGER_PLAN_PATH", "")
    if plan_env and Path(plan_env).exists():
        (ROOT / "docs" / "merger_master_plan_zh.md").write_bytes(Path(plan_env).read_bytes())

    # Clean up temporary root files
    for tmp in [ROOT / "generate_figures.py", ROOT / "unified_manuscript_en_latex.md"]:
        if tmp.exists():
            tmp.unlink()

    # 3. Extract locked evidence files and build DATA_LINEAGE_MANIFEST.json (when local repos are available)
    if all(v["local"].exists() for v in REPOS.values()):
        manifest_entries = []
        branch_sha_cache = {}

        for regime_dir, repo_name, branch, src_rel, dst_name in EXTRACTIONS:
            repo_info = REPOS[repo_name]
            cache_key = (repo_name, branch)
            if cache_key not in branch_sha_cache:
                branch_sha_cache[cache_key] = get_commit_sha(repo_info["local"], branch)
            commit_sha = branch_sha_cache[cache_key]

            raw_bytes = subprocess.check_output(
                ["git", "show", f"{branch}:{src_rel}"],
                cwd=repo_info["local"],
            )
            dst_path = ROOT / "evidence_archive" / regime_dir / dst_name
            dst_path.write_bytes(raw_bytes)

            manifest_entries.append({
                "regime": regime_dir,
                "source_repository": repo_info["url"],
                "source_branch": branch,
                "commit_sha": commit_sha,
                "source_relative_path": src_rel,
                "archived_relative_path": f"evidence_archive/{regime_dir}/{dst_name}",
                "size_bytes": len(raw_bytes),
                "sha256": sha256_bytes(raw_bytes),
            })

        # Also generate a clean CSV table for Study 1C (15 external Dreyer85 cells + 15 dev summaries)
        comp_status_path = ROOT / "evidence_archive" / "regime1_zero_shot" / "Study1C_composition_v2_status.json"
        comp_data = json.loads(comp_status_path.read_text())
        comp_csv_path = ROOT / "evidence_archive" / "regime1_zero_shot" / "Study1C_composition_v2_classical_summary.csv"
        with comp_csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "phase", "cell_id", "family", "method", "n_participants",
                "completed_tasks", "planned_tasks", "mean_ba", "left_recall", "right_recall", "min_recall"
            ])
            for row in comp_data.get("descriptive_statistics", []):
                if row.get("family") == "classical":
                    m = row.get("metrics") or {}
                    writer.writerow([
                        row.get("phase"),
                        row.get("cell_id"),
                        row.get("family"),
                        row.get("method"),
                        row.get("n_participants"),
                        row.get("completed_tasks"),
                        row.get("planned_tasks"),
                        m.get("ba"),
                        m.get("recall_left"),
                        m.get("recall_right"),
                        m.get("min_recall"),
                    ])

        manifest_obj = {
            "project": "Unified Multi-Regime Motor Imagery EEG Calibration & Error-Redistribution Study",
            "authors": [
                {"name": "Ziyuan Zhu", "orcid": "0009-0005-1153-4926", "email": "zzy2630816871@gmail.com", "corresponding": True},
                {"name": "Sihao Liu"},
                {"name": "Haoyang Yu"},
            ],
            "affiliation": "College of Artificial Intelligence Medicine, Chongqing Medical University, Chongqing 400016, China",
            "source_repositories": {
                k: {
                    "url": v["url"],
                    "inspected_branches_count": len(
                        [b for b in subprocess.check_output(["git", "branch", "-r"], cwd=v["local"], text=True).splitlines() if "->" not in b]
                    ),
                }
                for k, v in REPOS.items()
            },
            "total_archived_files": len(manifest_entries),
            "files": manifest_entries,
        }
        manifest_path = ROOT / "evidence_archive" / "DATA_LINEAGE_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest_obj, indent=2, ensure_ascii=False) + "\n")
        print(f"[OK] Extracted {len(manifest_entries)} locked evidence files and wrote {manifest_path}")
    else:
        print("[INFO] Source repositories not mounted under MI_EEG_REPOS_DIR; skipping evidence extraction.")

    # 4. Compile EN/ZH manuscripts and Supplementary Materials DOCX/PDF deliverables
    replacements = {
        "−": "-",
        "•": r"$\bullet$",
        "×": r"$\times$",
        "≥": r"$\ge$",
        "≤": r"$\le$",
        "→": r"$\to$",
        "≈": r"$\approx$",
        "±": r"$\pm$",
        "∈": r"$\in$",
        "μ": r"$\mu$",
    }

    def compile_docx_pdf(doc_dir: Path, stem: str, build_pdf: bool = True):
        md_path = doc_dir / f"{stem}.md"
        docx_path = doc_dir / f"{stem}.docx"
        pdf_path = doc_dir / f"{stem}.pdf"

        subprocess.run(
            ["pandoc", md_path.name, "-o", docx_path.name],
            cwd=doc_dir,
            check=True,
        )
        msg = f"[OK] Compiled {docx_path.name} ({docx_path.stat().st_size} B)"

        if build_pdf:
            latex_text = md_path.read_text(encoding="utf-8")
            for k, v in replacements.items():
                latex_text = latex_text.replace(k, v)
            tmp_tex_md = doc_dir / f"_tmp_{stem}_latex.md"
            tmp_tex_md.write_text(latex_text, encoding="utf-8")
            try:
                subprocess.run(
                    [
                        "pandoc", tmp_tex_md.name,
                        "-o", pdf_path.name,
                        "--pdf-engine=pdflatex",
                        "-V", "geometry:margin=0.8in",
                        "-V", "fontsize=10pt",
                    ],
                    cwd=doc_dir,
                    check=True,
                )
            finally:
                if tmp_tex_md.exists():
                    tmp_tex_md.unlink()
            msg += f" and {pdf_path.name} ({pdf_path.stat().st_size} B)"
        print(msg)

    compile_docx_pdf(ROOT / "manuscript" / "en", "Unified_MIEEG_Manuscript_EN", build_pdf=True)
    compile_docx_pdf(ROOT / "manuscript" / "zh", "Unified_MIEEG_Manuscript_ZH", build_pdf=False)
    compile_docx_pdf(ROOT / "manuscript" / "supplementary", "Supplementary_Materials_EN", build_pdf=True)


if __name__ == "__main__":
    main()
