"""Load hash-pinned covariance assets and preserve original trial opportunities."""

from dataclasses import dataclass
from hashlib import sha256, file_digest
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.linalg import helmert

CHANNELS = "FC3 FC1 FC2 FC4 C3 C1 CZ C2 C4 CP3 CP1 CPZ CP2 CP4".split()
CAR = helmert(14, full=False)
BUDGETS = (0, 4, 8, 12, 16, 20, 32, 64, 128)
DIMENSIONS = (0, 1, 2, 4, 8, 16, 32, 64, "Full")
PANEL_CUTS = {"Stieger": 64, "OpenBMI": 64, "Cho2017": 128}
ASSETS = {
    "Prefix": ("EEG Flagship Study/Prefix Calibration/Inputs.zip",
               "4bec315a7b0d7297b9b93e76f50b6b8ee1bae949adc295d811273351abe992fc"),
    "Stieger3": ("Research10-Merged/R9/R9-Features.zip",
                 "3d59f7da745fb8a9b324eeb9a8c1a080bfff8235ac58bd996e76c3218bc03a36"),
    "Stieger4": ("Research10-Merged/R10/R10-Features.zip",
                 "e53a705e208fda52b3ef8b7416fa9ee8cb7715793ee4aabd29bc5cdfc8d285e0"),
}
ROSTERS = {"Stieger": 62, "OpenBMI": 54, "Cho2017": 52}


def fingerprint(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def read_npz(payload):
    with np.load(BytesIO(payload), allow_pickle=False) as arrays:
        return dict(arrays.items())


def checked_member(bundle, name, digest):
    content = bundle.read(name)
    if sha256(content).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch for {name}")
    return content


def normalize(x):
    return x / np.trace(x, axis1=-2, axis2=-1)[..., None, None]


def project(x):
    x = np.asarray(x, dtype=float)
    c = CAR @ x @ CAR.T
    if (not np.isfinite(c).all() or not np.allclose(c, c.swapaxes(-1, -2), atol=1e-7)
            or np.any(np.trace(c, axis1=-2, axis2=-1) <= 0)):
        raise ValueError("Covariance must be finite, symmetric and have positive CAR trace")
    return normalize(c)


@dataclass(frozen=True)
class Episode:
    cohort: str
    person: str
    session: int
    ids: np.ndarray
    positions: np.ndarray
    labels: np.ndarray
    valid: np.ndarray
    cov: np.ndarray
    native: np.ndarray
    runs: np.ndarray
    n_opportunities: int
    rest: np.ndarray | None = None
    feedback: np.ndarray | None = None
    clock: np.ndarray | None = None
    events: np.ndarray | None = None

    @property
    def key(self):
        return f"{self.cohort}-{self.person}-D{self.session}"

    def checked(self):
        n = len(self.labels)
        fields = (self.ids, self.positions, self.valid, self.native, self.runs)
        if any(len(value) != n for value in fields) or self.cov.shape != (n, 13, 13):
            raise ValueError(f"Inconsistent trial arrays in {self.key}")
        if (len(set(self.ids)) != n or not np.isin(self.labels, (0, 1)).all()
                or not (np.diff(self.positions) > 0).all()
                or not (np.diff(self.native) > 0).all()
                or not ((1 <= self.positions) & (self.positions <= self.n_opportunities)).all()
                or not np.isfinite(self.cov[self.valid]).all()):
            raise ValueError(f"Invalid IDs, order or covariances in {self.key}")
        if self.rest is not None and (self.rest.shape != self.cov.shape or not np.isfinite(self.rest[self.valid]).all()):
            raise ValueError(f"Invalid paired pre-cue data in {self.key}")
        if self.clock is not None and not (np.diff(self.clock) > 0).all():
            raise ValueError(f"Nonmonotone registered clock in {self.key}")
        return self

    def support(self, budget):
        return np.flatnonzero((self.positions <= budget) & self.valid)

    def query(self, cutoff):
        return np.flatnonzero((self.positions > cutoff) & self.valid)


def load_prefix(path):
    with ZipFile(path) as bundle:
        manifest = json.loads(bundle.read("Input-Manifest.json"))
        payload = {name: checked_member(bundle, name, row["sha256"])
                   for name, row in manifest["files"].items()}
    episodes = []
    for cohort, prefix, clock in (("Cho2017", "H", "source_sequence"),
                                  ("OpenBMI", "O", "event_sample_1based")):
        with ZipFile(BytesIO(payload[cohort + ".zip"])) as bundle:
            people = [f"{prefix}{k:02d}" for k in range(1, ROSTERS[cohort] + 1)]
            if set(bundle.namelist()) != {p + ".npz" for p in people}:
                raise ValueError(f"Unexpected roster in {cohort}")
            for person in people:
                data = read_npz(bundle.read(person + ".npz"))
                if list(data["channels"]) != CHANNELS or not np.all(data["subject"] == int(person[1:])):
                    raise ValueError(f"Invalid montage or subject identifier in {person}")
                sessions = np.unique(data["session"])
                if tuple(sessions) != ((1, 2) if cohort == "OpenBMI" else (1,)):
                    raise ValueError(f"Unexpected session roster in {person}")
                for day in sessions:
                    keep = (data["session"] == day) & (data["task"] == "MI") & np.isin(data["hand"], (0, 1))
                    valid = data["valid"][keep]
                    positions = np.arange(1, int(keep.sum()) + 1, dtype=int)
                    covariance = np.full((len(valid), 13, 13), np.nan)
                    covariance[valid] = project(data["cov"][keep][valid])
                    episodes.append(Episode(
                        cohort, person, int(day), data["trial_id"][keep], positions, data["hand"][keep],
                        valid, covariance, positions, data["run"][keep], len(positions),
                        clock=data[clock][keep],
                        events=data.get("event_code", data["hand"])[keep],
                    ).checked())
    return payload["Forenzo14-Source.zip"], episodes


def load_stieger(path, day):
    episodes = []
    with ZipFile(path) as bundle:
        if day == 3:
            hashes = json.loads(bundle.read("Features.json"))
        else:
            hashes = json.loads(bundle.read("Feature-Manifest.json"))["files"]
        names = [f"S{k:02d}-E{day:02d}.npz" for k in range(1, 63)]
        if set(hashes) != set(names):
            raise ValueError(f"Unexpected Stieger E{day} feature roster")
        for name in names:
            data = read_npz(checked_member(bundle, name, hashes[name]))
            subject, session = int(data["person"]), int(data["session"])
            native, runs = data["native_index"], data["run"]
            n_lr = int(data["native_lr"])
            if session != day or name != f"S{subject:02d}-E{day:02d}.npz":
                raise ValueError("Stieger person/session does not match the filename")
            if "lr_ordinal" in data:
                ordinal = data["lr_ordinal"]
            else:
                # E03 archives retain actual file positions and run membership.
                unique = np.unique(runs)
                if (len(unique) * 25 != n_lr or not np.all(native == data["run_trial"] - 1)
                        or not np.all(runs == native // 25 + 1)):
                    raise ValueError("Cannot reconstruct original LR slots in the E03 archive")
                ordinal = 25 * np.searchsorted(unique, runs) + native % 25 + 1
            ids = np.asarray([f"S{subject:02d}-E{day:02d}-N{n + 1:03d}" for n in native])
            cov = data["cov"]
            episodes.append(Episode("Stieger", f"S{subject:02d}", day, ids, ordinal, data["hand"],
                                    np.ones(len(ids), dtype=bool), cov[:, 1], native, runs, n_lr,
                                    rest=cov[:, 0], feedback=cov[:, 2]).checked())
    return episodes


def load_assets(paths):
    for key, (_, expected) in ASSETS.items():
        if fingerprint(paths[key]) != expected:
            raise ValueError(f"Drive asset hash differs for {key}")
    source, episodes = load_prefix(paths["Prefix"])
    return source, episodes + load_stieger(paths["Stieger3"], 3) + load_stieger(paths["Stieger4"], 4)
