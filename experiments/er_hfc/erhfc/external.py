"""Confirmation intake. No external trial archive is opened before release validation."""

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from .data import CHANNELS, Episode, fingerprint, read_npz
from .experiments import gate_predictions
from .methods import PRIOR, loo_geometry, rates, transformed
from .statistics import estimate, holm

EXPOSED = {"stieger", "stieger2021", "openbmi", "cho", "cho2017", "pan2023", "pan2025", "weibo",
           "forenzo", "forenzo2024", "dreyer", "dreyer2023", "graz", "bnci2014_001", "nm000300", "nm000339",
           "physionet", "brandl", "kumar", "yang2025", "ma2022"}
EXPOSED_DOIS = {"10.7910/dvn/gh74zg", "10.7910/dvn/251now", "10.1093/gigascience/giz002",
                "10.1093/gigascience/gix034", "10.1109/tbme.2023.3298957"}


def verify_release(document, method_lock):
    must_match = {
        "protocol_hash": method_lock,
        "primary_arm": "full_er_hfc",
        "primary_reference": "stage12",
        "budget": 20,
        "architecture": "CSP",
        "query_cutoff": 20,
        "ba_min_superiority_pp": 1.0,
        "ba_noninferiority_pp": 1.0,
        "severe_loss_pp": 2.0,
        "severe_risk_min_reduction_pp": 3.0,
    }
    if any(document.get(k) != v for k, v in must_match.items()):
        raise ValueError("Confirmation release does not match the frozen algorithm and analysis plan")
    if (not document.get("cohort") or document["cohort"].lower() in EXPOSED or not document.get("dataset_doi")
            or str(document["dataset_doi"]).lower().removeprefix("https://doi.org/") in EXPOSED_DOIS
            or str(document["dataset_doi"]).lower().startswith("10.6084/m9.figshare.13123148")
            or not document.get("version") or not document.get("license")
            or not document.get("independence_receipt") or not document.get("protocol_registration")
            or document.get("outcomes_read_for_tuning") is not False or document.get("n_expected_people", 0) < 15):
        raise ValueError("External lineage and independent pre-outcome registration must be documented")
    return document


def read_external(archive_path, release_path, method_lock):
    release = verify_release(json.loads(Path(release_path).read_text()), method_lock)
    if fingerprint(archive_path) != release.get("data_sha256"):
        raise ValueError("The external package differs from its preregistered fingerprint")
    episodes, ids, person_sessions = [], set(), set()
    with ZipFile(archive_path) as archive:
        roster = json.loads(archive.read("Ledger.json"))
        files = roster["files"]
        if (roster["schema"] != "erhfc-covariance-confirmation-v1" or roster["dataset_doi"] != release["dataset_doi"]
                or roster["license"] != release["license"] or list(roster["channels"]) != CHANNELS
                or set(archive.namelist()) != {"Ledger.json", *files}):
            raise ValueError("External manifest or 14-channel geometry is incompatible")
        for name, expected in sorted(files.items()):
            member = archive.read(name)
            if sha256(member).hexdigest() != expected:
                raise ValueError(f"Checksum failed for external member {name}")
            arr = read_npz(member)
            participant, session = str(arr["person"].item()), int(arr["session"])
            if (participant, session) in person_sessions:
                raise ValueError("A confirmation person-session has two registered entries")
            person_sessions.add((participant, session))
            data = Episode(release["cohort"], participant, session, arr["ids"], arr["positions"], arr["labels"],
                           arr["valid"].astype(bool), arr["cov"], arr["native"], arr["runs"], int(arr["n_opportunities"]))
            data.checked()
            if (set(data.ids).intersection(ids) or data.n_opportunities < 50
                    or np.any(np.abs(np.trace(data.cov[data.valid], axis1=1, axis2=2) - 1) > 1e-6)
                    or not np.allclose(data.cov[data.valid], data.cov[data.valid].swapaxes(-2, -1), atol=1e-7)
                    or np.any(np.linalg.eigvalsh(data.cov[data.valid]) < -1e-6)):
                raise ValueError("Invalid external trial identity, opportunities or covariance normalization")
            ids.update(data.ids)
            episodes.append(data)
    if len({r.person for r in episodes}) != release["n_expected_people"]:
        raise ValueError("External roster count differs from the release")
    return release, episodes


def evaluate_confirmation(episodes, models):
    rows, qc = [], []
    for ep in episodes:
        support, query = ep.support(20), ep.query(20)
        both = min(np.bincount(ep.labels[query], minlength=2))
        qc.append(dict(person=ep.person, session=ep.session, valid_prefix=len(support), valid_future=len(query),
                       min_query_per_class=int(both), eligible=bool(both >= 10)))
        if both < 10:
            continue
        for n, source in models.items():
            scores, features = transformed(source, "CSP", ep.cov, ep.valid, ep.cov[support], PRIOR)
            history = loo_geometry(ep, source, "CSP", support)
            arms, _ = gate_predictions(ep, scores, features, support, query, ep.labels[support], history)
            for name in ("stage12", "matched_map", "full_er_hfc"):
                rows.append(dict(person=ep.person, session=ep.session, fold=n, arm=name,
                                 **rates(ep.labels[query], arms[name], arms["stage12"])))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame, pd.DataFrame(qc), pd.DataFrame(), dict(state="unavailable", reason="no_eligible_matched_probes")
    episodes = frame.groupby(["person", "session", "arm"])[["ba", "severe_negative"]].mean().reset_index()
    people = episodes.groupby(["person", "arm"])[["ba", "severe_negative"]].mean()
    ba = people.ba.unstack("arm")
    risk = people.severe_negative.unstack("arm")
    values = [
        ("BA_superiority_vs_stage12", ba.full_er_hfc - ba.stage12, 0.0),
        ("BA_noninferiority_vs_matched_MAP", ba.full_er_hfc - ba.matched_map, -0.01),
        ("severe_loss_reduction_vs_matched_MAP", risk.matched_map - risk.full_er_hfc, 0.0),
    ]
    inference = pd.DataFrame(
        dict(endpoint=name, null=null, **estimate(diff, ("E04", name), null=null, alternative="greater"))
        for name, diff, null in values
    )
    inference["p_holm"] = holm(inference.p)
    primary, ni, risk_claim = list(inference.itertuples())
    n_ok = int(ba.shape[0]) >= 15
    decisions = dict(state="complete", paired_people=int(ba.shape[0]),
                     primary_met=bool(n_ok and primary.delta >= .01 and primary.lo95 > 0 and primary.p_holm < .05),
                     protection_met=bool(n_ok and ni.lo95 > -.01 and ni.p_holm < .05 and
                                         risk_claim.delta >= .03 and risk_claim.lo95 > 0 and risk_claim.p_holm < .05))
    return frame, pd.DataFrame(qc), inference, decisions
