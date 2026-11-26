"""Reproducible entry point used by the ER-HFC Colab notebook."""

import argparse
from collections import Counter
from hashlib import sha256
import gzip
import json
import math
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import tempfile
from time import perf_counter

import numpy as np
import pandas as pd
import scipy
import sklearn
from threadpoolctl import threadpool_limits

from erhfc.audit import audit_data
from erhfc.data import ASSETS, fingerprint, load_assets
from erhfc.experiments import evaluate_job
from erhfc.models import build_source
from erhfc.report import atomic_copy_table, prepare_report

VERSION = "er-hfc-development-v1"
ROOT = Path(__file__).resolve().parent
PLAN_FILES = ["EXPERIMENT_DESIGN.md", "STATISTICAL_ANALYSIS_PLAN.md", "HYPOTHESIS_REGISTRY.json",
              "DATA_LINEAGE_MANIFEST.json", "EXPERIMENT_MATRIX.csv"]


def plain(value):
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_bytes(path, payload):
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".swap-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def atomic_json(path, document, compressed=False):
    contents = (json.dumps(plain(document), indent=None if compressed else 2,
                           allow_nan=False, ensure_ascii=False) + "\n").encode()
    atomic_bytes(path, gzip.compress(contents, compresslevel=4, mtime=0) if compressed else contents)


def code_receipt():
    entries = sorted(ROOT.glob("erhfc/*.py")) + [ROOT / "run_experiments.py", ROOT / "selftest.py"]
    entries += [ROOT / f for f in PLAN_FILES]
    files = {str(f.relative_to(ROOT)): fingerprint(f) for f in entries}
    lock = sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return lock, files


def runtime_info(path):
    import shutil

    gpu = []
    if shutil.which("nvidia-smi"):
        try:
            completed = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
                                       "--format=csv,noheader"], capture_output=True, text=True, timeout=8)
            gpu = completed.stdout.strip().splitlines() if completed.returncode == 0 else []
        except (OSError, subprocess.TimeoutExpired):
            gpu = ["GPU telemetry unavailable"]
    _, _, free = shutil.disk_usage(path)
    ram = Path("/proc/meminfo")
    first = ram.read_text().splitlines()[0] if ram.is_file() else ""
    return dict(python=platform.python_version(), platform=platform.platform(), cpu_count=os.cpu_count(),
                installed=dict(numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                               sklearn=sklearn.__version__), gpu_nvidia_smi=gpu, gpu_used_by_experiment=False,
                free_result_volume_bytes=free, host_memory=first,
                drive_quota_note="Mounted filesystem free space is not a billing quota. Check Google Drive separately if WRITE fails.")


def resource_snapshot():
    current = resource.getrusage(resource.RUSAGE_SELF)
    return dict(max_process_rss_mib=current.ru_maxrss / 1024, user_cpu_seconds=current.ru_utime,
                system_cpu_seconds=current.ru_stime)


def build_queue(episodes, mode):
    tasks = []
    for ep in sorted(episodes, key=lambda r: (r.cohort, r.person, r.session)):
        if mode == "pilot" and int(ep.person[1:]) not in (1, 2):
            continue
        for arch, registered in (("CSP", (1, 2, 3, 4, 5)), ("MDM", (1, 3))):
            for fold in registered if mode != "pilot" else (1,):
                tasks.append((ep, arch, fold, "calibration"))
                if ep.cohort == "Stieger" and arch == "MDM":
                    tasks.append((ep, arch, fold, "rest"))
    return tasks


def json_if_good(path, expected_signature, key):
    if not path.is_file():
        return None
    try:
        data = json.loads(gzip.decompress(path.read_bytes()))
        if (data["signature"] == expected_signature and data["key"] == key
                and isinstance(data["result"]["metrics"], list) and data["result"]["metrics"]):
            return data["result"]
    except (OSError, ValueError, KeyError, EOFError):
        return None
    return None


def run(assets, results, mode, *, external=None, release=None, max_jobs=None):
    if external and (not release or mode != "external") or mode == "external" and (not external or not release):
        raise ValueError("An external run needs both an independently frozen release and a matching archive")
    began = perf_counter()
    results = Path(results)
    results.mkdir(parents=True, exist_ok=True)
    runtime = runtime_info(results)
    lock, files = code_receipt()
    stage_started = perf_counter()
    source, episodes = load_assets(assets)
    source_load = perf_counter() - stage_started
    stage_started = perf_counter()
    with threadpool_limits(limits=1):
        folds, sources = build_source(source, (1,) if mode == "pilot" else (1, 2, 3, 4, 5))
    source_build = perf_counter() - stage_started
    signature = sha256(json.dumps(dict(version=VERSION, lock=lock, mode=mode,
                                      inputs={k: t[1] for k, t in ASSETS.items()}), sort_keys=True).encode()).hexdigest()
    identity = signature[:12]
    if mode == "external":
        from erhfc.external import evaluate_confirmation, read_external
        receipt, test_episodes = read_external(external, release, lock)
        run_path = results / f"E04-{receipt['data_sha256'][:12]}-{identity}"
        run_path.mkdir(exist_ok=True)
        with threadpool_limits(limits=1):
            fold, qc, inference, decision = evaluate_confirmation(test_episodes, folds)
        for name, table in (("E04-Fold-Metrics.csv.gz", fold), ("E04-Coverage.csv", qc), ("E04-Effects.csv", inference)):
            atomic_copy_table(table, run_path / name)
        atomic_json(run_path / "E04-Decision.json", decision)
        atomic_json(run_path / "E04-Receipt.json", receipt | {"runtime": runtime})
        return run_path

    run_path = results / f"{mode}-{identity}"
    run_path.mkdir(exist_ok=True)
    cache = run_path / "Checkpoints"
    cache.mkdir(exist_ok=True)
    status = run_path / "PROGRESS.json"
    manifest = dict(protocol=VERSION, mode=mode, signature=signature, code_lock=lock, files=files,
                    inputs={k: v[1] for k, v in ASSETS.items()}, source_models=sources, environment=runtime,
                    source_load_seconds=source_load, source_build_seconds=source_build,
                    scientific_role="pilot_only" if mode == "pilot" else "development_only",
                    E04="awaiting independence and pre-outcome archive receipt",
                    neural_E11="not scored, cohort/window parity and pretraining lineage pending")
    atomic_json(run_path / "Run-Manifest.json", manifest)
    stage_started = perf_counter()
    with threadpool_limits(limits=1):
        audits, audit_summary = audit_data(episodes, folds[1])
        from selftest import test_real_no_label_leak
        fixture = next(e for e in episodes if e.cohort == "Stieger" and e.session == 4)
        audit_summary["future_label_inversion"] = test_real_no_label_leak(fixture, folds[1])
    for name, rows in audits.items():
        atomic_copy_table(pd.DataFrame(rows), run_path / f"{name}.csv")
    atomic_json(run_path / "Data-Audit.json", audit_summary)
    audit_seconds = perf_counter() - stage_started

    tasks = build_queue(episodes, mode)
    queue = [(f"{ep.key}-{arch}-F{fold}-{task}", ep, arch, fold, task) for ep, arch, fold, task in tasks]
    registered = pd.read_csv(ROOT / "EXPERIMENT_MATRIX.csv")
    registered = set(registered.loc[registered.default == "run", "task_id"])
    calculated = {job[0] for job in queue}
    if not calculated <= registered or mode != "pilot" and calculated != registered:
        raise ValueError("Runtime queue differs from the locked matrix")
    atomic_copy_table(pd.DataFrame(dict(task_id=k, cohort=ep.cohort, person=ep.person, session=ep.session,
                                       architecture=arch, fold=fold, kind=task)
                                   for k, ep, arch, fold, task in queue), run_path / "Actual-Queue.csv")
    task_times, done, failed = [], {}, {}
    resumed = 0
    computed = 0
    expanded = mode != "core"

    def checkpoint_summary(state):
        progress = dict(protocol=VERSION, mode=mode, state=state, signature=signature, jobs_planned=len(queue),
                        completed=len(done), resumed=resumed, computed_this_launch=computed, failures=failed,
                        external_confirmation="deferred", wall_seconds=perf_counter() - began, **resource_snapshot())
        atomic_json(status, progress)
        return progress

    checkpoint_summary("running")
    with threadpool_limits(limits=1):
        for index, (key, ep, arch, f, task) in enumerate(queue, 1):
            path = cache / (key + ".json.gz")
            saved = json_if_good(path, signature, key)
            if saved is not None:
                resumed += 1
                done[key] = saved
            elif max_jobs is None or computed < max_jobs:
                computed += 1
                try:
                    factorial = ep.cohort == "Stieger" and ep.session == 4 and arch == "CSP" and f == 1
                    value = evaluate_job(ep, folds[f], arch, task, extensions=expanded, factorial=factorial)
                    if not value["metrics"]:
                        raise ValueError("An experiment returned no metrics or eligibility ledger")
                    atomic_json(path, dict(signature=signature, key=key, result=value), compressed=True)
                    done[key] = value
                except Exception as error:
                    failed[key] = f"{type(error).__name__}: {str(error)[:350]}"
            if key in done:
                task_times.append(dict(cohort=ep.cohort, session=ep.session, arch=arch, fold=f, kind=task,
                                       label_noise=expanded and ep.cohort == "Stieger" and ep.session == 4
                                       and arch == "CSP" and f == 1 and task == "calibration",
                                       seconds=done[key]["duration_seconds"], payload_bytes=path.stat().st_size,
                                       reused=saved is not None))
            if index in (1, len(queue)) or index % 10 == 0:
                print(f"{index}/{len(queue)} queued · {len(done)} complete · {len(failed)} failures", flush=True)
                checkpoint_summary("running")
    atomic_copy_table(pd.DataFrame(task_times), run_path / "Task-Timing.csv")
    atomic_copy_table(pd.DataFrame([dict(task=k, error=v) for k, v in failed.items()], columns=["task", "error"]),
                      run_path / "Failed-Tasks.csv")
    # Do not emit participant-level inference from an incomplete scientific matrix.
    summary = {}
    if len(done) == len(queue):
        stage_started = perf_counter()
        with threadpool_limits(limits=1):
            raw_count, person_count, effect_count = prepare_report(
                run_path, list(done.values()), mode=mode, planned=len(queue),
                missing=failed, audit_summary=audit_summary,
            )
        summary = dict(raw_rows=raw_count, participant_rows=person_count, effect_rows=effect_count,
                       summarize_seconds=perf_counter() - stage_started)
    progress = checkpoint_summary("complete" if len(done) == len(queue) else "partial")
    atomic_json(run_path / "Timing.json", dict(progress=progress, audit_seconds=audit_seconds, **summary))
    return run_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--stieger3", type=Path, required=True)
    parser.add_argument("--stieger4", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--mode", choices=("pilot", "core", "all", "external"), default="all")
    parser.add_argument("--external", type=Path)
    parser.add_argument("--release", type=Path)
    args = parser.parse_args(argv)
    paths = {"Prefix": args.prefix, "Stieger3": args.stieger3, "Stieger4": args.stieger4}
    print(run(paths, args.results, args.mode, external=args.external, release=args.release), flush=True)


if __name__ == "__main__":
    main()
