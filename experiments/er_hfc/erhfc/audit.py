"""Schedule, window and identity checks before any effect interpretation."""

from collections import Counter, defaultdict
from hashlib import sha256

import numpy as np

from .data import PANEL_CUTS, ROSTERS
from .methods import rates


def audit_data(episodes, fold):
    ids = set()
    overlaps = defaultdict(dict)
    cov_seen = {}
    repeated = []
    schedule_totals = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for ep in episodes:
        if set(ep.ids).intersection(ids):
            raise ValueError("Trial identities repeat across canonical episodes")
        ids.update(ep.ids)
        overlaps[ep.cohort, ep.person][ep.session] = ep
        for i in np.flatnonzero(ep.valid):
            key = sha256(np.ascontiguousarray(ep.cov[i], dtype="<f8").tobytes()).hexdigest()
            identity = (ep.cohort, ep.person, ep.session, str(ep.ids[i]))
            if key in cov_seen:
                repeated.append(dict(first=cov_seen[key], repeat=identity))
            else:
                cov_seen[key] = identity
        totals = schedule_totals[ep.cohort, ep.session]
        for pos, y in zip(ep.positions, ep.labels, strict=True):
            totals[int(pos)][0] += int(y)
            totals[int(pos)][1] += 1

    coverage, schedules, crossday, phases = [], [], [], []
    for (cohort, person), days in sorted(overlaps.items()):
        for day, ep in sorted(days.items()):
            cut = PANEL_CUTS[cohort]
            q = ep.query(cut)
            core = dict(cohort=cohort, person=person, session=day)
            support = ep.support(20)
            coverage.append(core | dict(opportunities=ep.n_opportunities, retained=int(ep.valid.sum()),
                                        prefix20_n=len(support), prefix20_l=int((ep.labels[support] == 0).sum()),
                                        prefix20_r=int((ep.labels[support] == 1).sum()), cut=cut, query=len(q),
                                        query_l=int((ep.labels[q] == 0).sum()), query_r=int((ep.labels[q] == 1).sum()),
                                        same_position_current_clock=ep.clock is not None,
                                        rest_verified_window=ep.rest is not None))
            references = [day] + ([1] if cohort == "OpenBMI" and day == 2 else [])
            for training_day in references:
                own = days.get(training_day)
                own_labels = dict(zip(own.positions, own.labels, strict=True)) if own is not None else {}
                z, match = [], []
                for pos in ep.positions[q]:
                    right, count = schedule_totals[cohort, training_day][int(pos)]
                    if pos in own_labels:
                        right -= int(own_labels[pos])
                        count -= 1
                    z.append((right + 0.5) / (count + 1) - 0.5)
                    match.append(count > 0)
                z = np.asarray(z)
                metric = rates(ep.labels[q], z, z)
                schedules.append(core | dict(train_session=training_day, n=len(q), coverage=float(np.mean(match)),
                                             ba=metric["ba"], auc=metric["auc"]))
            if ep.rest is not None:
                y = ep.labels[q]
                z = fold.score(ep.rest[q], "MDM")
                measure = rates(y, z, z)
                phases.append(core | dict(fold=fold.number, panel="pre_cue_current_hand", n=len(q), auc=measure["auc"]))
            if ep.feedback is not None:
                probe = q[np.isfinite(ep.feedback[q]).all(axis=(1, 2))]
                for name, cov in (("cue_matched", ep.cov), ("feedback_matched", ep.feedback)):
                    z = fold.score(cov[probe], "MDM")
                    measure = rates(ep.labels[probe], z, z)
                    phases.append(core | dict(fold=fold.number, panel=name, n=len(probe), auc=measure["auc"]))
        if cohort == "OpenBMI" and set(days) == {1, 2}:
            first, second = days[1], days[2]
            i, j = np.intersect1d(first.positions, second.positions, return_indices=True)[1:]
            choices = first.labels[i] == second.labels[j]
            same_clock = bool(np.array_equal(first.clock[i], second.clock[j]))
            event_correct = all(np.array_equal(day.labels, (day.events == 1).astype(int)) for day in (first, second))
            crossday.append(dict(person=person, positions=len(i), matched_hand=int(sum(choices)),
                                 exact_full_cycle=bool(choices.all()), identical_onset_vector=same_clock,
                                 prepared_hand_code_verified=event_correct,
                                 exact_equal_valid_covariances=int(np.sum(
                                     (first.valid[i] & second.valid[j]) &
                                     np.all(first.cov[i] == second.cov[j], axis=(1, 2))))))

    rosters = Counter(cohort for cohort, person in overlaps)
    sessions = Counter(ep.cohort for ep in episodes)
    if dict(rosters) != ROSTERS:
        raise ValueError("A development roster differs from its immutable source metadata")
    summary = dict(rosters=rosters, sessions=sessions, unique_trial_ids=len(ids),
                   repeated_exact_covariance_count=len(repeated), structural_cross_person_identity="unverified across unrelated releases",
                   openbmi_identical_label_schedules=sum(r["exact_full_cycle"] for r in crossday),
                   openbmi_equal_onset_vectors=sum(r["identical_onset_vector"] for r in crossday),
                   scope="Metadata and exact-feature audit. Prepared IDs do not verify physical stimulus onset independently.",
                   foundation_pretraining_overlap="unresolved; no deep validation claimed")
    return {"Cohort-QC": coverage, "Schedule-Only": schedules, "OpenBMI-Cross-Day": crossday,
            "Window-Audit": phases, "Exact-Feature-Duplicates": repeated}, summary
