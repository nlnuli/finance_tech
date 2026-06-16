from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import track

from .agent_runner import run_case
from .case_generator import generate_cases, generate_cases_in_batches
from .case_loader import load_cases, split_csv
from .document_loader import split_csv_paths
from .models import AgentTrace
from .ragas_scorer import score_cases
from .report import write_reports
from .retriever_runner import run_retrieval


DEFAULT_CONFIG_PATH = Path("evaluations/configs/ragas_rag_eval.json")

console = Console()


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Ragas evaluation config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def config_value(args, config: dict, name: str, default=None):
    value = getattr(args, name, None)
    if value is not None:
        return value
    return config.get(name, default)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and run Ragas RAG evaluations for the project agent.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate reusable Ragas cases from local files or directories.",
    )
    generate_parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    generate_parser.add_argument(
        "--source-paths",
        help="Comma-separated file or directory paths.",
    )
    generate_parser.add_argument(
        "--case-count",
        type=int,
        help="Number of cases to generate.",
    )
    generate_parser.add_argument(
        "--output",
        help="Generated JSONL case path.",
    )
    generate_parser.add_argument(
        "--batch-size",
        type=int,
        help="Enable batched generation with this many files per batch.",
    )
    generate_parser.add_argument(
        "--cases-per-batch",
        type=int,
        default=2,
        help="Cases to generate from each batch when --batch-size is set.",
    )
    generate_parser.add_argument(
        "--target-case-count",
        type=int,
        help="Total cases to collect in batched generation. Defaults to --case-count.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run Ragas evaluation on generated cases.",
    )
    run_parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    run_parser.add_argument("--cases", help="Generated JSONL case path.")
    run_parser.add_argument("--output-dir", help="Report output directory.")
    run_parser.add_argument("--assistant-id", help="Assistant id payload filter.")
    run_parser.add_argument("--retrieval-k", type=int, help="Top-k retrieval size.")
    run_parser.add_argument(
        "--recursion-limit",
        type=int,
        help="LangGraph recursion limit.",
    )
    run_parser.add_argument(
        "--case-timeout-seconds",
        type=float,
        help="Per-case timeout in seconds.",
    )
    run_parser.add_argument("--limit", type=int, help="Maximum cases to run.")
    run_parser.add_argument("--case-ids", help="Comma-separated exact case ids.")
    run_parser.add_argument(
        "--run-name",
        help="Human-readable experiment run name. Defaults to an auto-generated name.",
    )
    run_parser.add_argument(
        "--variant",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Controlled variable to archive with this run. "
            "Repeatable, for example --variant chunk_size=1000 --variant prompt=v2."
        ),
    )
    run_parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Write reports directly to --output-dir instead of creating a run subdirectory.",
    )

    return parser


def normalize_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._=-]+", "-", value.strip())
    slug = slug.strip("-._")
    return slug or "run"


def parse_variants(values: list[str]) -> dict[str, str]:
    variants: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"--variant must use KEY=VALUE format: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--variant key cannot be empty: {item}")
        variants[key] = value.strip()
    return variants


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def build_run_metadata(
    *,
    case_path: Path,
    cases_count: int,
    base_output_dir: Path,
    assistant_id: str,
    retrieval_k: int,
    recursion_limit: int,
    timeout_seconds: float,
    run_name: str | None,
    variants: dict[str, str],
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    model = env_first("OPENAI_RELAY_MODEL", "OPENAI_MODEL") or "unknown"
    embedding_model = env_first("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    metadata = {
        "run_name": run_name,
        "started_at": started_at,
        "case_path": str(case_path),
        "case_file_sha256": file_sha256(case_path),
        "case_count": cases_count,
        "base_output_dir": str(base_output_dir),
        "assistant_id": assistant_id,
        "retrieval_k": retrieval_k,
        "recursion_limit": recursion_limit,
        "case_timeout_seconds": timeout_seconds,
        "llm_model": model,
        "embedding_model": embedding_model,
        "variants": variants,
    }
    if not metadata["run_name"]:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        metadata["run_name"] = (
            f"{timestamp}__model-{model}__assistant-{assistant_id}"
            f"__k{retrieval_k}__rl{recursion_limit}__cases{cases_count}"
        )
    return metadata


def resolve_run_output_dir(
    base_output_dir: Path,
    run_metadata: dict[str, Any],
    archive: bool,
) -> Path:
    if not archive:
        return base_output_dir
    return base_output_dir / "runs" / safe_slug(str(run_metadata["run_name"]))


def append_run_index(
    base_output_dir: Path,
    run_output_dir: Path,
    summary: dict[str, Any],
    run_metadata: dict[str, Any],
) -> None:
    base_output_dir.mkdir(parents=True, exist_ok=True)
    index_jsonl = base_output_dir / "runs_index.jsonl"
    custom = summary.get("custom_metrics", {})
    ragas = summary.get("ragas_metrics", {})
    row = {
        "run_name": run_metadata.get("run_name"),
        "started_at": run_metadata.get("started_at"),
        "output_dir": str(run_output_dir),
        "case_count": summary.get("case_count"),
        "assistant_id": run_metadata.get("assistant_id"),
        "retrieval_k": run_metadata.get("retrieval_k"),
        "recursion_limit": run_metadata.get("recursion_limit"),
        "llm_model": run_metadata.get("llm_model"),
        "embedding_model": run_metadata.get("embedding_model"),
        "retrieval_hit_rate": custom.get("retrieval_hit_rate"),
        "agent_retrieval_hit_rate": custom.get("agent_retrieval_hit_rate"),
        "rag_tool_use_rate": custom.get("rag_tool_use_rate"),
        "empty_retrieval_rate": custom.get("empty_retrieval_rate"),
        "avg_latency_seconds": custom.get("avg_latency_seconds"),
        "faithfulness": ragas.get("faithfulness"),
        "answer_relevancy": ragas.get("answer_relevancy"),
        "context_recall": ragas.get("context_recall"),
        "context_precision": ragas.get("llm_context_precision_with_reference"),
        "factual_correctness": ragas.get("factual_correctness"),
        "variants": run_metadata.get("variants", {}),
    }
    with index_jsonl.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")

    index_csv = base_output_dir / "runs_index.csv"
    flat_row = {
        **{key: value for key, value in row.items() if key != "variants"},
        **{
            f"variant_{key}": value
            for key, value in (run_metadata.get("variants") or {}).items()
        },
    }
    write_header = not index_csv.exists()
    with index_csv.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(flat_row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(flat_row)


async def run_case_with_timeout(
    case,
    assistant_id: str,
    retrieval_k: int,
    recursion_limit: int,
    timeout_seconds: float,
) -> AgentTrace:
    try:
        return await asyncio.wait_for(
            run_case(
                case=case,
                assistant_id=assistant_id,
                retrieval_k=retrieval_k,
                recursion_limit=recursion_limit,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        return AgentTrace(
            case_id=case.id,
            latency_seconds=timeout_seconds,
            error=f"case timed out after {timeout_seconds} seconds",
            timed_out=True,
        )


def run_generate(args: argparse.Namespace) -> None:
    config = load_config(Path(args.config))
    source_paths = split_csv_paths(args.source_paths) or config.get("source_paths", [])
    case_count = config_value(args, config, "case_count", 30)
    output_path = normalize_path(
        args.output or config.get("case_output_path")
    )

    if not source_paths:
        raise ValueError("No --source-paths provided and config source_paths is empty.")

    if args.batch_size:
        target_case_count = args.target_case_count or case_count
        console.print(
            f"[bold]Generating Ragas cases in batches[/bold]: "
            f"sources={source_paths}, target_case_count={target_case_count}, "
            f"batch_size={args.batch_size}, cases_per_batch={args.cases_per_batch}"
        )
        cases = generate_cases_in_batches(
            source_paths=source_paths,
            target_case_count=target_case_count,
            output_path=output_path,
            batch_size=args.batch_size,
            cases_per_batch=args.cases_per_batch,
        )
    else:
        console.print(
            f"[bold]Generating Ragas cases[/bold]: "
            f"sources={source_paths}, case_count={case_count}"
        )
        cases = generate_cases(
            source_paths=source_paths,
            case_count=case_count,
            output_path=output_path,
        )
    console.print(
        f"[green]Generated {len(cases)} cases.[/green] Output: {output_path}"
    )


async def run_evaluation(args: argparse.Namespace) -> None:
    config = load_config(Path(args.config))
    case_path = normalize_path(args.cases or config.get("case_output_path"))
    output_dir = normalize_path(args.output_dir or config.get("result_output_dir"))
    assistant_id = config_value(args, config, "assistant_id", "default")
    retrieval_k = config_value(args, config, "retrieval_k", 4)
    recursion_limit = config_value(args, config, "recursion_limit", 8)
    timeout_seconds = config_value(args, config, "case_timeout_seconds", 120)

    cases = load_cases(
        path=case_path,
        limit=args.limit,
        case_ids=split_csv(args.case_ids),
    )
    if not cases:
        raise ValueError(f"No cases loaded from {case_path}")

    variants = parse_variants(args.variant)
    archive = not args.no_archive and config.get("archive_runs", True)
    run_metadata = build_run_metadata(
        case_path=case_path,
        cases_count=len(cases),
        base_output_dir=output_dir,
        assistant_id=assistant_id,
        retrieval_k=retrieval_k,
        recursion_limit=recursion_limit,
        timeout_seconds=timeout_seconds,
        run_name=args.run_name,
        variants=variants,
    )
    run_output_dir = resolve_run_output_dir(
        base_output_dir=output_dir,
        run_metadata=run_metadata,
        archive=archive,
    )

    console.print(
        f"[bold]Running Ragas RAG eval[/bold]: cases={len(cases)}, "
        f"assistant_id={assistant_id}, retrieval_k={retrieval_k}, "
        f"output={run_output_dir}"
    )

    direct_contexts_by_case = {}
    traces = []
    for case in track(cases, description="Running retrieval and agent"):
        try:
            direct_contexts_by_case[case.id] = run_retrieval(
                query=case.question,
                assistant_id=assistant_id,
                retrieval_k=retrieval_k,
            )
        except Exception:
            direct_contexts_by_case[case.id] = []

        trace = await run_case_with_timeout(
            case=case,
            assistant_id=assistant_id,
            retrieval_k=retrieval_k,
            recursion_limit=recursion_limit,
            timeout_seconds=timeout_seconds,
        )
        traces.append(trace)

    scores = score_cases(
        cases=cases,
        traces=traces,
        direct_contexts_by_case=direct_contexts_by_case,
    )
    summary = write_reports(run_output_dir, scores, run_metadata=run_metadata)
    if archive:
        append_run_index(
            base_output_dir=output_dir,
            run_output_dir=run_output_dir,
            summary=summary,
            run_metadata=run_metadata,
        )
    console.print(f"[green]Evaluation complete.[/green] Output: {run_output_dir}")
    console.print_json(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        run_generate(args)
    elif args.command == "run":
        asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
