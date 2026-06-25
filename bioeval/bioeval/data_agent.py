from __future__ import annotations

import argparse
import os
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bioeval import opencode_runner
from bioeval.catalog import load_catalog
from bioeval.curation import GrantPlan, select_instructions_by_keywords, stage_and_grant
from bioeval.problems import load_problem_spec
from bioeval.run_record import append_jsonl, utc_now
from bioeval.schemas import DatasetGrant, DatasetRequest

DEFAULT_DATA_AGENT_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_DATA_AGENT_API_BASE = "bedrock:us-east-1"


class DataAgentSettings(BaseModel):
    problems_root: Path
    staging_root: Path
    sandbox_data_root: str = "/workspace/data"
    default_problem_id: str | None = None
    model: str = DEFAULT_DATA_AGENT_MODEL
    api_base: str = DEFAULT_DATA_AGENT_API_BASE
    run_id: str = "default"
    run_root: Path | None = None


UEA_VISIBLE_PATHS = (
    Path("/workspace"),
    Path("/submit"),
    Path("/logs"),
)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _private_audit_log_path(run_root: Path) -> Path:
    path = run_root / "data_requests.jsonl"
    if any(_is_relative_to(path, visible) for visible in UEA_VISIBLE_PATHS):
        raise RuntimeError(
            "Refusing to write data-agent planner log inside a UEA-visible mount."
        )
    return path


def _plan_record(plan: GrantPlan) -> dict:
    return {
        "deny": plan.deny,
        "deny_reason": plan.deny_reason,
        "message": plan.message,
        "instructions": [
            {
                "entry_id": instr.entry_id,
                "rows": instr.rows,
                "columns": instr.columns,
                "use_online": instr.use_online,
            }
            for instr in plan.instructions
        ],
    }


def _identifiers_for(problem_id: str) -> list[str]:
    """Hidden paper/repo markers the leak guard scans for."""
    try:
        spec = load_problem_spec(problem_id)
    except Exception:
        return []
    idents = [spec.title, spec.doi, *spec.leak_markers]
    if spec.doi:
        idents.append(f"doi.org/{spec.doi}")
    return [i for i in idents if i]


def make_plan(catalog, request: DatasetRequest, model: str, api_base: str) -> GrantPlan:
    catalog_public = catalog.public_view()
    request_payload = {
        "question": request.question,
        "desired_modalities": request.desired_modalities,
        "max_bytes": request.max_bytes,
    }
    if opencode_runner.is_bedrock_api_base(api_base):
        # 1) Native AWS Bedrock Converse, matching skydiscover's credential flow.
        plan = opencode_runner.plan_with_bedrock(
            catalog_public,
            request_payload,
            model=model,
            api_base=api_base,
        )
        if plan is not None and (plan.instructions or plan.deny):
            return plan
    else:
        # 1) opencode in a locked-down workspace for OpenAI-compatible models.
        ws = Path(tempfile.mkdtemp(prefix="bioeval_ws_"))
        try:
            opencode_runner.build_workspace(ws, catalog_public, request_payload)
            plan = opencode_runner.plan_with_opencode(ws, model=f"openai/{model}")
            if plan is not None and (plan.instructions or plan.deny):
                return plan
        finally:
            import shutil

            shutil.rmtree(ws, ignore_errors=True)

    # 2) direct OpenAI structured-output call for OpenAI-compatible configs.
    plan = None
    if not opencode_runner.is_bedrock_api_base(api_base):
        plan = opencode_runner.plan_with_openai(catalog_public, request_payload, model=model)
    if plan is not None and (plan.instructions or plan.deny):
        return plan
    # 3) deterministic keyword fallback.
    return GrantPlan(
        instructions=select_instructions_by_keywords(catalog, request),
        message="Selected datasets by keyword match (no LLM planner available).",
    )


def create_app(settings: DataAgentSettings) -> FastAPI:
    app = FastAPI(title="bioeval data-agent", version="0.2.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/request-data", response_model=DatasetGrant)
    def request_data(request: DatasetRequest) -> DatasetGrant:
        problem_id = request.problem_id or settings.default_problem_id
        if not problem_id:
            raise HTTPException(status_code=400, detail="No problem_id configured for data-agent.")

        problem_root = settings.problems_root / problem_id
        if not problem_root.exists():
            raise HTTPException(status_code=404, detail=f"Unknown problem_id: {problem_id}")

        try:
            catalog = load_catalog(problem_root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        request = request.model_copy(update={"problem_id": problem_id})
        request_id = uuid.uuid4().hex[:12]

        planner_error = None
        try:
            plan = make_plan(catalog, request, settings.model, settings.api_base)
        except Exception as exc:  # noqa: BLE001 - never crash the endpoint
            planner_error = str(exc)
            plan = GrantPlan(
                instructions=select_instructions_by_keywords(catalog, request),
                message=f"Planner error; used keyword fallback ({exc}).",
            )

        grant = stage_and_grant(
            problem_root=problem_root,
            catalog=catalog,
            identifiers=_identifiers_for(problem_id),
            staging_root=settings.staging_root,
            sandbox_data_root=settings.sandbox_data_root,
            request=request,
            request_id=request_id,
            plan=plan,
        )
        if opencode_runner.is_bedrock_api_base(settings.api_base):
            from bioeval.bedrock_cost import finalize_cost_tracker

            finalize_cost_tracker(component="data-agent", model=settings.model)
        if settings.run_root is not None:
            append_jsonl(
                _private_audit_log_path(settings.run_root),
                {
                    "event": "data_request",
                    "timestamp": utc_now(),
                    "run_id": settings.run_id,
                    "problem_id": problem_id,
                    "request_id": request_id,
                    "data_agent_model": settings.model,
                    "data_agent_api_base": settings.api_base,
                    "request": request.model_dump(),
                    "planner_error": planner_error,
                    "plan": _plan_record(plan),
                    "grant": grant.model_dump(),
                },
            )
        return grant

    return app


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the host-side bioeval data-agent.")
    parser.add_argument("--problems-root", type=Path, default=Path("../problems_complete"))
    parser.add_argument("--staging-root", type=Path, default=Path("./runs/data_grants"))
    parser.add_argument("--sandbox-data-root", default="/workspace/data")
    parser.add_argument("--problem-id", default=os.getenv("BIOEVAL_PROBLEM_ID"))
    parser.add_argument("--model", default=os.getenv("DATA_AGENT_MODEL", DEFAULT_DATA_AGENT_MODEL))
    parser.add_argument(
        "--api-base",
        default=os.getenv("DATA_AGENT_API_BASE", DEFAULT_DATA_AGENT_API_BASE),
    )
    parser.add_argument("--run-id", default=os.getenv("BIOEVAL_RUN_ID", "default"))
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("DATA_AGENT_PORT", "8765")))
    return parser


def main() -> None:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args()
    settings = DataAgentSettings(
        problems_root=args.problems_root.resolve(),
        staging_root=args.staging_root.resolve(),
        sandbox_data_root=args.sandbox_data_root,
        default_problem_id=args.problem_id,
        model=args.model,
        api_base=args.api_base,
        run_id=args.run_id,
        run_root=args.run_root.resolve() if args.run_root else None,
    )
    settings.staging_root.mkdir(parents=True, exist_ok=True)
    if settings.run_root is not None:
        settings.run_root.mkdir(parents=True, exist_ok=True)

    import uvicorn

    uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
