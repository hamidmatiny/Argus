"""Evidently AI DataDriftPreset reports alongside hand-rolled KS tests."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import DRIFT_FEATURES, REPORTS_DIR

logger = logging.getLogger("argus.drift_monitor.evidently")


def run_evidently_drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    reports_dir: Path | None = None,
) -> tuple[Path | None, dict[str, float]]:
    """
    Generate an Evidently DataDriftPreset report.

    Returns (html_path | None, feature_drift_scores).
    Scores fall back to empty dict if Evidently is unavailable.
    """
    out_dir = reports_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = [c for c in DRIFT_FEATURES if c in reference.columns and c in current.columns]
    if not cols:
        return None, {}

    ref = reference[cols].copy()
    cur = current[cols].copy()

    try:
        scores, html_path = _run_evidently_v1(ref, cur, out_dir)
        return html_path, scores
    except Exception as exc:  # noqa: BLE001
        logger.warning("evidently_report_failed", extra={"error": str(exc)})
        return None, {}


def _run_evidently_v1(
    ref: pd.DataFrame, cur: pd.DataFrame, out_dir: Path
) -> tuple[dict[str, float], Path]:
    """Support Evidently 0.4+ Report API and newer Report Builder if present."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    html_path = out_dir / f"data_drift_{stamp}.html"
    scores: dict[str, float] = {}

    try:
        # Evidently >= 0.4 classic API
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report

        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=ref, current_data=cur)
        report.save_html(str(html_path))
        payload = report.as_dict()
        scores = _extract_scores_from_report_dict(payload)
        return scores, html_path
    except ImportError:
        pass

    # Evidently 0.5+ / 0.6 Report builder style (best-effort)
    from evidently import Report as NewReport
    from evidently.presets import DataDriftPreset as NewPreset

    report = NewReport(metrics=[NewPreset()])
    my_eval = report.run(reference_data=ref, current_data=cur)
    # Persist HTML if API supports it
    if hasattr(my_eval, "save_html"):
        my_eval.save_html(str(html_path))
    elif hasattr(report, "save_html"):
        report.save_html(str(html_path))
    else:
        html_path.write_text(
            f"<html><body><pre>{my_eval}</pre></body></html>", encoding="utf-8"
        )
    if hasattr(my_eval, "dict"):
        scores = _extract_scores_from_report_dict(my_eval.dict())
    return scores, html_path


def _extract_scores_from_report_dict(payload: dict[str, Any]) -> dict[str, float]:
    """Best-effort parse of Evidently report JSON into per-feature drift scores."""
    scores: dict[str, float] = {}
    metrics = payload.get("metrics") or []
    for metric in metrics:
        result = metric.get("result") or {}
        # Common shape: result.drift_by_columns[col].drift_score / stattest_score
        drift_by_columns = result.get("drift_by_columns") or {}
        for col, info in drift_by_columns.items():
            if not isinstance(info, dict):
                continue
            score = info.get("drift_score")
            if score is None:
                score = info.get("stattest_score")
            if score is None and info.get("drift_detected") is not None:
                score = 1.0 if info["drift_detected"] else 0.0
            if score is not None:
                scores[str(col)] = float(score)
        # Fallback: dataset-level share of drifted features
        if not scores and "share_of_drifted_columns" in result:
            share = float(result["share_of_drifted_columns"])
            for col in DRIFT_FEATURES:
                scores[col] = share
    return scores
