"""Frozen source CSP/LDA, a source-only MDM replicate and nested tangent features."""

from dataclasses import dataclass
from io import BytesIO
import json
from zipfile import ZipFile

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from .data import CAR, CHANNELS, checked_member, normalize, project, read_npz

RIDGE_SPD = 0.10
I = np.eye(13)
TRIANGLE = np.triu_indices(13)
SQRT2 = np.where(TRIANGLE[0] == TRIANGLE[1], 1, np.sqrt(2))


def sym(a):
    return 0.5 * (a + a.swapaxes(-1, -2))


def matrix_func(a, f):
    values, vectors = np.linalg.eigh(sym(a))
    positive = np.maximum(values, 1e-12)
    return (vectors * f(positive)[..., None, :]) @ vectors.swapaxes(-1, -2)


def root(a):
    return matrix_func(a, np.sqrt)


def inverse_root(a):
    return matrix_func(a, lambda x: x ** -0.5)


def shrink(cov):
    return (1 - RIDGE_SPD) * cov + RIDGE_SPD * I / len(I)


def affine_mean(matrices, weights):
    current = np.average(matrices, axis=0, weights=weights)
    for _ in range(80):
        inv = inverse_root(current)
        change = np.average(matrix_func(inv @ matrices @ inv, np.log), axis=0, weights=weights)
        if np.linalg.norm(change) < 1e-8:
            return current
        scale = root(current)
        v, u = np.linalg.eigh(sym(change))
        current = sym(scale @ (u * np.exp(v)[None, :]) @ u.T @ scale)
    raise ValueError("Source MDM affine mean did not converge")


def split_weights(source, people, hand):
    matrices = [source[p][0][source[p][1] == hand] for p in people]
    return np.concatenate(matrices), np.concatenate([np.full(len(x), 1 / (len(people) * len(x))) for x in matrices])


def tangent(cov, reference_inv):
    mapped = matrix_func(reference_inv @ shrink(cov) @ reference_inv, np.log)
    return mapped[:, TRIANGLE[0], TRIANGLE[1]] * SQRT2


@dataclass(frozen=True)
class SourceFold:
    number: int
    ref: np.ndarray
    ref_root: np.ndarray
    inv_ref: np.ndarray
    csp_filters: np.ndarray
    csp_w: np.ndarray
    csp_b: float
    mdm_centers: np.ndarray
    mean_pc: np.ndarray
    basis: np.ndarray
    pc_scale: np.ndarray
    score_scale: dict
    training: tuple
    calibration: tuple
    heldout: tuple

    def raw_score(self, x, arch):
        if arch == "CSP":
            power = np.einsum("ci,ncd,di->ni", self.csp_filters, x, self.csp_filters, optimize=True)
            return np.log(np.maximum(power, 1e-10)) @ self.csp_w + self.csp_b
        if arch == "MDM":
            x = shrink(x)
            distances = []
            for m in self.mdm_centers:
                values = np.linalg.eigvalsh(m @ x @ m)
                distances.append(np.square(np.log(np.maximum(values, 1e-12))).sum(axis=1))
            return distances[0] - distances[1]
        raise ValueError(f"Unsupported source architecture {arch}")

    def score(self, x, arch):
        return np.clip(self.raw_score(x, arch) / self.score_scale[arch], -20.0, 20.0)

    def features(self, cov):
        return (tangent(cov, self.inv_ref) - self.mean_pc) @ self.basis / self.pc_scale

    def transport(self, cov, history, prior):
        if len(history) == 0:
            return cov.copy()
        reference = (history.sum(axis=0) + prior * self.ref) / (len(history) + prior)
        transform = self.ref_root @ inverse_root(reference)
        return normalize(transform @ cov @ transform.T)


def build_source(source_archive, chosen=(1, 2, 3, 4, 5)):
    from dataclasses import replace

    people = {}
    folds = {}
    with ZipFile(BytesIO(source_archive)) as archive:
        registry = json.loads(archive.read("models/Source-Models.json"))
        held = pd.read_csv(BytesIO(archive.read("models/Forenzo-Held-Out.csv")))
        if registry["channels"] != CHANNELS:
            raise ValueError("Source montage order changed")
        for p in range(1, 26):
            data = read_npz(checked_member(archive, f"features/F{p:02d}.npz", registry["features_sha256"][f"F{p:02d}"]))
            if list(data["channels"]) != CHANNELS or not np.all(data["subject"] == p):
                raise ValueError("Archived source position metadata disagree")
            use = data["valid"] & (data["task"] == "MI") & np.isin(data["hand"], (0, 1))
            people[p] = project(data["cov"][use]), data["hand"][use]
            if set(people[p][1]) != {0, 1}:
                raise ValueError("A source training member has only one label")

        receipts = []
        for spec in registry["folds"]:
            fold = int(spec["fold"])
            if fold not in chosen:
                continue
            model = read_npz(checked_member(archive, "models/" + spec["file"], spec["sha256"]))
            train, cal, test = (tuple(sorted(map(int, model[k]))) for k in ("train", "calibration", "test"))
            all_people = train + cal + test
            if (set(all_people) != set(people) or len(all_people) != len(set(all_people))
                    or list(model["channels"]) != CHANNELS or int(model["fold"]) != fold
                    or any(sorted(spec[k]) != list(v) for k, v in zip(("train", "calibration", "test"), (train, cal, test), strict=True))):
                raise ValueError(f"Source fold {fold} split changed")
            grouped = [split_weights(people, train, hand) for hand in (0, 1)]
            reference = 0.5 * sum(np.average(x, axis=0, weights=w) for x, w in grouped)
            inv = inverse_root(shrink(reference))
            distances = np.stack([inverse_root(affine_mean(shrink(x), w)) for x, w in grouped])
            features = np.concatenate([tangent(x, inv) for x, w in grouped])
            weights = np.concatenate([0.5 * w for x, w in grouped])
            mean = np.average(features, axis=0, weights=weights)
            centered = (features - mean) * np.sqrt(weights[:, None])
            vals, vecs = np.linalg.eigh(centered.T @ centered)
            vecs = vecs[:, ::-1]
            vals = vals[::-1]
            # Canonical PC orientation makes one-dimensional arms stable in reruns.
            top = np.argmax(abs(vecs), axis=0)
            vecs *= np.sign(vecs[top, np.arange(vecs.shape[1])])
            result = SourceFold(
                fold, reference, root(reference), inv, CAR @ model["filters"], model["w"], float(model["b"]),
                distances, mean, vecs, np.sqrt(np.maximum(vals, 1e-5)), {}, train, cal, test,
            )
            scales = {}
            for arch in ("CSP", "MDM"):
                scores = np.concatenate([result.raw_score(people[p][0], arch) for p in train])
                scales[arch] = max(1e-3, float(np.sqrt(np.mean(scores ** 2))))
            result = replace(result, score_scale=scales)
            for p in test:
                x, y = people[p]
                z = result.raw_score(x, "CSP")
                order = rankdata(z)
                nright = int(y.sum())
                ba = (np.mean(z[y == 0] < 0) + np.mean(z[y == 1] >= 0)) / 2
                auc = (order[y == 1].sum() - nright * (nright + 1) / 2) / (nright * (len(y) - nright))
                row = held[(held.source_fold == fold) & (held.subject == p)]
                if (len(row) != 1 or len(x) != int(row.n_valid.iloc[0])
                        or not np.allclose([ba, auc], row[["ba", "auc"]].iloc[0], atol=1e-8)):
                    raise ValueError(f"Frozen CSP held-out receipt differs for fold {fold}, source participant {p}")
            folds[fold] = result
            receipts.append(dict(fold=fold, archived_csp_sha256=spec["sha256"], train=list(train),
                                 source_calibration=list(cal), source_test=list(test), rank=int((vals > 1e-5).sum()),
                                 scales=scales, reference="source-train only"))
    if set(folds) != set(chosen):
        raise ValueError("Requested frozen source folds not found")
    return folds, receipts
