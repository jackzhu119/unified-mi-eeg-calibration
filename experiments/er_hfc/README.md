# ER-HFC experiments

The Colab notebook runs the development queue from hash-pinned covariance archives in Drive. It performs self-tests, resumes per-person/session/fold checkpoints and exports the scientific outputs to Drive. Default mode is `all`. Use `pilot` for a small real-data systems check or `core` for the primary CPU jobs. Source assets stay in their registered folders.

`run_experiments.py --help` lists the CLI paths. `selftest.py` runs without scientific data. Results should be interpreted with the analysis plan and known exposure. The proposed dual gate and the archived ERFC profile are different estimands.

External scoring uses `--mode external --external ... --release ...` only after a timestamped, independently audited data release. The archive contains exactly the `Ledger.json` member and registered NPZ sessions. Ledger schema is `erhfc-covariance-confirmation-v1`; it declares DOI, license, channel order and member hashes. Each session needs scalar `person`, `session`, `n_opportunities` and arrays `ids`, `positions`, `labels`, `valid`, `cov`, `native`, `runs`. Covariance uses the registered trace-one 13-D CAR format of scaled 14-channel cue-phase inputs. The ready package and release document are not available for the current run. Read `erhfc/external.py` for required fields, role validation and endpoint definitions.

The original ERFC solver is retained unchanged from the source repository and fingerprint in the lineage manifest. This release does not package EEG, weights or participant outputs with code. Review `Publication-Candidate-Aggregates.csv` before releasing any derived results.
