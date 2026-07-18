from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bioeval import opencode_runner, providers
from bioeval.catalog import load_catalog
from bioeval.curation import (
    DENIED_RE,
    GrantPlan,
    is_public_source_request,
    select_instructions_by_keywords,
    stage_and_grant,
)
from bioeval.experiment_validation import validate_experiment
from bioeval.problems import load_problem_spec
from bioeval.run_record import append_jsonl, utc_now
from bioeval.search_proxy import (
    contains_hidden_identifier,
    restricted_fetch_webpage,
    restricted_research_papers,
    restricted_web_search,
)
from bioeval.schemas import (
    CatalogEntry,
    DatasetGrant,
    DatasetRequest,
    ExperimentRequest,
    ExperimentResult,
    ExperimentValidation,
    ValidationCheck,
)

DEFAULT_EXPERIMENT_AGENT_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_EXPERIMENT_AGENT_API_BASE = "bedrock:us-east-1"
RESTRICTED_EXPERIMENT_MESSAGE = (
    "This experiment names a restricted paper, identifier, repository, code artifact, "
    "or answer-like resource. Submit an independently specified experiment instead."
)


class ExperimentAgentSettings(BaseModel):
    problems_root: Path
    staging_root: Path
    sandbox_data_root: str = "/workspace/data"
    default_problem_id: str | None = None
    model: str = DEFAULT_EXPERIMENT_AGENT_MODEL
    api_base: str = DEFAULT_EXPERIMENT_AGENT_API_BASE
    run_id: str = "default"
    run_root: Path | None = None
    enforce_problem_status: bool = True


class ResearchPapersToolRequest(BaseModel):
    operation: str
    query: str
    limit: int = 10


class WebSearchToolRequest(BaseModel):
    query: str
    limit: int = 8
    allowed_domain: list[str] = []
    blocked_domain: list[str] = []


class FetchWebpageToolRequest(BaseModel):
    url: str
    max_chars: int = 80000


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
    path = run_root / "experiment_requests.jsonl"
    if any(_is_relative_to(path, visible) for visible in UEA_VISIBLE_PATHS):
        raise RuntimeError(
            "Refusing to write experiment-agent planner log inside a UEA-visible mount."
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
    except Exception as exc:
        raise RuntimeError(
            f"Cannot enforce hidden-identifier guard for problem {problem_id!r}."
        ) from exc
    idents = [spec.title, spec.doi, *spec.leak_markers]
    if spec.doi:
        idents.append(f"doi.org/{spec.doi}")
    return [i for i in idents if i]


def _external_cutoff_for(problem_id: str) -> str | None:
    try:
        cutoff = load_problem_spec(problem_id).external_source_cutoff
    except Exception as exc:
        raise RuntimeError(
            f"Cannot enforce external-source cutoff for problem {problem_id!r}."
        ) from exc
    return cutoff.isoformat() if cutoff else None


def make_plan(catalog, request: DatasetRequest, model: str, api_base: str) -> GrantPlan:
    catalog_public = catalog.public_view()
    request_payload = {
        "experiment": request.experiment,
        "matching_text": request.question,
        "desired_modalities": request.desired_modalities,
        "desired_columns": request.desired_columns,
        "max_rows": request.max_rows,
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
    # A structured experiment requires semantic compatibility. Keyword matching
    # cannot establish that boundary, so planner outages must fail closed.
    if request.structured_experiment:
        return GrantPlan(
            deny=True,
            deny_reason="semantic_matcher_unavailable",
            message="Experiment execution could not be safely matched.",
        )
    # Legacy internal callers may still use the conservative keyword fallback.
    instructions = select_instructions_by_keywords(catalog, request)
    return GrantPlan(
        instructions=instructions,
        message="Selected datasets by keyword match (no LLM planner available).",
        deny=not instructions,
        deny_reason=None if instructions else "no_positive_keyword_match",
    )


def create_app(settings: ExperimentAgentSettings) -> FastAPI:
    unsafe_flags = [
        name
        for name in (
            "BIOEVAL_STRICT_DATA_REQUESTS",
            "BIOEVAL_TRAFFIC_GUARD_ENABLED",
            "BIOEVAL_TRAFFIC_GUARD_FAIL_CLOSED",
        )
        if os.getenv(name, "1").lower() in {"0", "false", "off", "none"}
    ]
    if unsafe_flags and os.getenv("BIOEVAL_DEVELOPMENT_MODE", "0") != "1":
        raise RuntimeError(
            "Unsafe benchmark guard configuration requires "
            f"BIOEVAL_DEVELOPMENT_MODE=1: {', '.join(unsafe_flags)}"
        )
    app = FastAPI(title="bioeval experiment-agent", version="1.0.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/experiments", response_model=ExperimentResult)
    def design_experiment(request: ExperimentRequest) -> ExperimentResult:
        problem_id = request.problem_id or settings.default_problem_id
        if not problem_id:
            raise HTTPException(status_code=400, detail="No problem_id configured for experiment-agent.")
        if settings.enforce_problem_status:
            try:
                spec = load_problem_spec(problem_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=404, detail=f"Unknown problem_id: {problem_id}"
                ) from exc
            if spec.benchmark_status == "acquisition_only":
                raise HTTPException(
                    status_code=403, detail="Acquisition-only problems are not runnable."
                )
            if (
                spec.benchmark_status == "conditional"
                and os.getenv("BIOEVAL_ALLOW_CONDITIONAL", "0") != "1"
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Conditional problem requires explicit runtime approval.",
                )

        problem_root = settings.problems_root / problem_id
        if not problem_root.exists():
            raise HTTPException(status_code=404, detail=f"Unknown problem_id: {problem_id}")

        request = request.model_copy(update={"problem_id": problem_id})
        request_id = uuid.uuid4().hex[:12]
        identifiers = _identifiers_for(problem_id)
        request_text = request.model_dump_json(exclude={"problem_id"})
        deterministic_deny = (
            "experiment contains a held-out identifier"
            if contains_hidden_identifier(request_text, identifiers)
            else "request asks for a restricted paper, code, or answer artifact"
            if DENIED_RE.search(request_text)
            else None
        )
        if deterministic_deny:
            validation = ExperimentValidation(
                status="restricted",
                summary="The experiment specification contains restricted material.",
                checks=[
                    ValidationCheck(
                        category="restricted",
                        severity="error",
                        path="$",
                        message="Remove paper, repository, code, or held-out identifiers.",
                    )
                ],
            )
            result = ExperimentResult(
                request_id=request_id,
                validation=validation,
                execution_status="not_attempted",
                message=RESTRICTED_EXPERIMENT_MESSAGE,
            )
            if settings.run_root is not None:
                append_jsonl(
                    _private_audit_log_path(settings.run_root),
                    {
                        "event": "experiment_request",
                        "timestamp": utc_now(),
                        "run_id": settings.run_id,
                        "problem_id": problem_id,
                        "request_id": request_id,
                        "experiment_agent_model": settings.model,
                        "experiment_agent_api_base": settings.api_base,
                        "request": request.model_dump(exclude={"problem_id"}),
                        "validation": validation.model_dump(),
                        "planner_error": None,
                        "plan": None,
                        "result": result.model_dump(),
                    },
                )
            return result

        validation = validate_experiment(
            request,
            model=settings.model,
            api_base=settings.api_base,
        )
        if opencode_runner.is_bedrock_api_base(settings.api_base):
            from bioeval.bedrock_cost import finalize_cost_tracker

            finalize_cost_tracker(
                component="experiment-agent-validation",
                model=settings.model,
            )
        if validation.status != "feasible":
            result = ExperimentResult(
                request_id=request_id,
                validation=validation,
                execution_status="not_attempted",
                message=validation.summary,
            )
            if settings.run_root is not None:
                append_jsonl(
                    _private_audit_log_path(settings.run_root),
                    {
                        "event": "experiment_request",
                        "timestamp": utc_now(),
                        "run_id": settings.run_id,
                        "problem_id": problem_id,
                        "request_id": request_id,
                        "experiment_agent_model": settings.model,
                        "experiment_agent_api_base": settings.api_base,
                        "request": request.model_dump(exclude={"problem_id"}),
                        "validation": validation.model_dump(),
                        "planner_error": None,
                        "plan": None,
                        "result": result.model_dump(),
                    },
                )
            return result

        # Availability is deliberately checked only after independent feasibility.
        try:
            catalog = load_catalog(problem_root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        data_request = request.as_dataset_request()

        planner_error = None
        try:
            plan = make_plan(catalog, data_request, settings.model, settings.api_base)
        except Exception as exc:  # noqa: BLE001 - never crash the endpoint
            planner_error = str(exc)
            plan = GrantPlan(
                deny=True,
                deny_reason="semantic_matcher_error",
                message="Experiment execution could not be safely matched.",
            )

        grant = stage_and_grant(
            problem_root=problem_root,
            catalog=catalog,
            identifiers=identifiers,
            staging_root=settings.staging_root,
            sandbox_data_root=settings.sandbox_data_root,
            request=data_request,
            request_id=request_id,
            plan=plan,
        )
        online_candidates: list[dict] = []
        if grant.status == "denied" and is_public_source_request(data_request.question):
            online_candidates = [
                candidate
                for candidate in providers.discover_dataset_specs(request.matching_text())
                if not contains_hidden_identifier(
                    " ".join(
                        [
                            str(candidate.get("description") or ""),
                            json.dumps(candidate.get("online") or {}, sort_keys=True),
                        ]
                    ),
                    identifiers,
                )
            ]
            if online_candidates:
                expanded_catalog = catalog.model_copy(
                    update={
                        "entries": [
                            *catalog.entries,
                            *[
                                CatalogEntry(
                                    id=candidate["id"],
                                    description=candidate["description"],
                                    kind="online",
                                    modalities=candidate["modalities"],
                                    approx_bytes=candidate["approx_bytes"],
                                    online=candidate["online"],
                                )
                                for candidate in online_candidates
                            ],
                        ]
                    }
                )
                try:
                    online_plan = make_plan(
                        expanded_catalog,
                        data_request,
                        settings.model,
                        settings.api_base,
                    )
                    online_grant = stage_and_grant(
                        problem_root=problem_root,
                        catalog=expanded_catalog,
                        identifiers=identifiers,
                        staging_root=settings.staging_root,
                        sandbox_data_root=settings.sandbox_data_root,
                        request=data_request,
                        request_id=request_id,
                        plan=online_plan,
                    )
                    if online_grant.status != "denied":
                        plan = online_plan
                        grant = online_grant
                except Exception as exc:  # noqa: BLE001 - preserve local failure result
                    planner_error = (
                        f"{planner_error}; online discovery: {exc}"
                        if planner_error
                        else f"online discovery: {exc}"
                    )
        if opencode_runner.is_bedrock_api_base(settings.api_base):
            from bioeval.bedrock_cost import finalize_cost_tracker

            finalize_cost_tracker(component="experiment-agent", model=settings.model)
        if grant.status == "granted":
            execution_status = "completed"
            public_message = (
                "The experiment completed successfully. Its measurements are available "
                "in the sandbox data directory."
            )
        elif grant.status == "partial":
            execution_status = "partially_completed"
            public_message = (
                "The experiment completed partially. The measurements that were "
                "successfully produced are available in the sandbox data directory."
            )
        else:
            execution_status = "could_not_execute"
            public_message = (
                "The experiment was feasible in principle but could not be executed "
                "with the available facilities and resources."
            )
        result = ExperimentResult(
            request_id=request_id,
            validation=validation,
            execution_status=execution_status,
            message=public_message,
            files=grant.files,
            rejected=(
                ["Some planned measurements could not be produced."]
                if grant.status == "partial"
                else []
            ),
            manifest_path=grant.manifest_path,
        )
        if settings.run_root is not None:
            append_jsonl(
                _private_audit_log_path(settings.run_root),
                {
                    "event": "experiment_request",
                    "timestamp": utc_now(),
                    "run_id": settings.run_id,
                    "problem_id": problem_id,
                    "request_id": request_id,
                    "experiment_agent_model": settings.model,
                    "experiment_agent_api_base": settings.api_base,
                    "request": request.model_dump(exclude={"problem_id"}),
                    "validation": validation.model_dump(),
                    "planner_error": planner_error,
                    "plan": _plan_record(plan),
                    "online_candidates": online_candidates,
                    "grant": grant.model_dump(),
                    "stager": {"denial_reason": grant.denial_reason},
                    "result": result.model_dump(),
                },
            )
        return result

    @app.post("/tools/research-papers")
    def research_papers_tool(request: ResearchPapersToolRequest) -> dict:
        problem_id = settings.default_problem_id
        if not problem_id:
            raise HTTPException(status_code=400, detail="No problem_id configured for experiment-agent.")
        if request.operation not in {"search", "snippet_search"}:
            raise HTTPException(status_code=400, detail="Unsupported research_papers operation.")
        guard_model = os.getenv("BIOEVAL_TRAFFIC_GUARD_MODEL") or settings.model
        try:
            return restricted_research_papers(
                operation=request.operation,
                query=request.query,
                limit=request.limit,
                identifiers=_identifiers_for(problem_id),
                external_source_cutoff=_external_cutoff_for(problem_id),
                guard_model=guard_model,
                guard_api_base=os.getenv("BIOEVAL_TRAFFIC_GUARD_API_BASE") or settings.api_base,
            )
        finally:
            if opencode_runner.is_bedrock_api_base(os.getenv("BIOEVAL_TRAFFIC_GUARD_API_BASE") or settings.api_base):
                from bioeval.bedrock_cost import finalize_cost_tracker

                finalize_cost_tracker(component="traffic-guard", model=guard_model)

    @app.post("/tools/web-search")
    def web_search_tool(request: WebSearchToolRequest) -> dict:
        problem_id = settings.default_problem_id
        if not problem_id:
            raise HTTPException(status_code=400, detail="No problem_id configured for experiment-agent.")
        guard_model = os.getenv("BIOEVAL_TRAFFIC_GUARD_MODEL") or settings.model
        try:
            return restricted_web_search(
                query=request.query,
                limit=request.limit,
                allowed_domain=request.allowed_domain,
                blocked_domain=request.blocked_domain,
                identifiers=_identifiers_for(problem_id),
                external_source_cutoff=_external_cutoff_for(problem_id),
                guard_model=guard_model,
                guard_api_base=os.getenv("BIOEVAL_TRAFFIC_GUARD_API_BASE") or settings.api_base,
            )
        finally:
            if opencode_runner.is_bedrock_api_base(os.getenv("BIOEVAL_TRAFFIC_GUARD_API_BASE") or settings.api_base):
                from bioeval.bedrock_cost import finalize_cost_tracker

                finalize_cost_tracker(component="traffic-guard", model=guard_model)

    @app.post("/tools/fetch-webpage")
    def fetch_webpage_tool(request: FetchWebpageToolRequest) -> dict:
        problem_id = settings.default_problem_id
        if not problem_id:
            raise HTTPException(status_code=400, detail="No problem_id configured for experiment-agent.")
        guard_model = os.getenv("BIOEVAL_TRAFFIC_GUARD_MODEL") or settings.model
        try:
            return restricted_fetch_webpage(
                url=request.url,
                max_chars=request.max_chars,
                identifiers=_identifiers_for(problem_id),
                external_source_cutoff=_external_cutoff_for(problem_id),
                guard_model=guard_model,
                guard_api_base=os.getenv("BIOEVAL_TRAFFIC_GUARD_API_BASE") or settings.api_base,
            )
        except Exception as exc:  # noqa: BLE001 - preserve tool-style errors
            return {"status": "error", "error": str(exc)}
        finally:
            if opencode_runner.is_bedrock_api_base(os.getenv("BIOEVAL_TRAFFIC_GUARD_API_BASE") or settings.api_base):
                from bioeval.bedrock_cost import finalize_cost_tracker

                finalize_cost_tracker(component="traffic-guard", model=guard_model)

    return app


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the host-side bioeval experiment-agent.")
    parser.add_argument("--problems-root", type=Path, default=Path("../problems_complete"))
    parser.add_argument("--staging-root", type=Path, default=Path("./runs/data_grants"))
    parser.add_argument("--sandbox-data-root", default="/workspace/data")
    parser.add_argument("--problem-id", default=os.getenv("BIOEVAL_PROBLEM_ID"))
    parser.add_argument(
        "--model",
        default=os.getenv("EXPERIMENT_AGENT_MODEL", DEFAULT_EXPERIMENT_AGENT_MODEL),
    )
    parser.add_argument(
        "--api-base",
        default=os.getenv("EXPERIMENT_AGENT_API_BASE", DEFAULT_EXPERIMENT_AGENT_API_BASE),
    )
    parser.add_argument("--run-id", default=os.getenv("BIOEVAL_RUN_ID", "default"))
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("EXPERIMENT_AGENT_PORT", "8765")))
    return parser


def main() -> None:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args()
    settings = ExperimentAgentSettings(
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
