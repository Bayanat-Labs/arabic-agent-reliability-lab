"""Read-only local RTL dashboard for generated passports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bayanat_lab.settings import ARTIFACT_ROOT, PACKAGE_ROOT

SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def _passport_rows(artifact_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    runs_root = artifact_root / "runs"
    if not runs_root.exists():
        return rows
    for path in sorted(
        runs_root.glob("*/passport.json"), key=lambda item: item.stat().st_mtime, reverse=True
    ):
        try:
            passport = json.loads(path.read_text(encoding="utf-8"))
            metrics = passport["metrics"]
            safety = metrics.get("safety_evaluation", {})
            safety_families = safety.get("family_denominators", {})
            proposals = safety.get(
                "families_with_prohibited_proposal",
                metrics.get("forbidden_action_attempt", {"rate": 0.0}),
            )
            rows.append(
                {
                    "run_id": passport["run_id"],
                    "generated_at": passport["generated_at"],
                    "agent": passport["system_snapshot"].get("agent"),
                    "model": passport["system_snapshot"].get("model"),
                    "success": metrics.get(
                        "operational_completion", metrics["task_success"]
                    )["rate"],
                    "communication": metrics.get("communication_quality", {}).get(
                        "rate"
                    ),
                    "prohibited_proposal": proposals["rate"],
                    "safety_evaluable": safety_families.get(
                        "at_least_one_rule_tool_available"
                    ),
                    "safety_rules": safety_families.get("rules_declared"),
                    "counts": passport["counts"],
                }
            )
        except (OSError, KeyError, json.JSONDecodeError):
            continue
    return rows


def create_dashboard_app(artifact_root: Path = ARTIFACT_ROOT) -> FastAPI:
    templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))
    app = FastAPI(title="Bayanat Reliability Passports", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "mode": "read-only", "external_assets": False}

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"passports": _passport_rows(artifact_root)},
        )

    @app.get("/api/passports")
    def api_passports() -> dict[str, Any]:
        return {"passports": _passport_rows(artifact_root)}

    @app.get("/passport/{run_id}")
    def passport(run_id: str):
        if not SAFE_RUN_ID.fullmatch(run_id):
            raise HTTPException(status_code=404)
        candidate = (artifact_root / "runs" / run_id / "passport.html").resolve()
        allowed_root = (artifact_root / "runs").resolve()
        if allowed_root not in candidate.parents or not candidate.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(candidate, media_type="text/html; charset=utf-8")

    return app


app = create_dashboard_app()
