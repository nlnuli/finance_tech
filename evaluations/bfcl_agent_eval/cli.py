from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rich.console import Console
from rich.progress import track

from .agent_runner import run_case
from .case_loader import load_cases
from .models import AgentTrace
from .report import write_reports
from .scorer import score_case


DEFAULT_CONFIG_PATH = Path("evaluations/configs/bfcl_subset.json")
DEFAULT_OUTPUT_DIR = Path("evaluations/results/react_agent_bfcl_subset")


console = Console()


def split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Evaluation config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the project ReAct agent on a BFCL subset.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run BFCL subset evaluation.")
    run_parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to evaluation config JSON.",
    )
    run_parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for summary and detail reports.",
    )
    run_parser.add_argument(
        "--categories",
        help="Comma-separated BFCL categories, e.g. simple_python,irrelevance.",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum cases per category. Overrides config limit_per_category.",
    )
    run_parser.add_argument(
        "--run-ids",
        help="Comma-separated exact BFCL case ids. Overrides per-category limit.",
    )
    run_parser.add_argument(
        "--recursion-limit",
        type=int,
        help="LangGraph recursion limit. Overrides config recursion_limit.",
    )
    run_parser.add_argument(
        "--case-timeout-seconds",
        type=float,
        help="Per-case timeout in seconds. Overrides config case_timeout_seconds.",
    )
    return parser


async def run_case_with_timeout(case, recursion_limit: int, timeout_seconds: float):
    try:
        return await asyncio.wait_for(
            run_case(case, recursion_limit=recursion_limit),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        return AgentTrace(
            case_id=case.id,
            category=case.category,
            latency_seconds=timeout_seconds,
            error=f"case timed out after {timeout_seconds} seconds",
        )


async def run_evaluation(args: argparse.Namespace) -> None:
    config = load_config(Path(args.config))
    categories = split_csv(args.categories) or config.get("categories", [])
    run_ids = split_csv(args.run_ids) or config.get("run_ids", [])
    limit = args.limit
    if limit is None:
        limit = config.get("limit_per_category")
    recursion_limit = args.recursion_limit or config.get("recursion_limit", 8)
    case_timeout_seconds = (
        args.case_timeout_seconds
        or config.get("case_timeout_seconds", 90)
    )

    if not categories:
        raise ValueError("No categories configured for evaluation.")

    console.print(
        f"[bold]Loading BFCL cases[/bold]: categories={categories}, "
        f"limit={limit}, run_ids={run_ids or '[]'}"
    )
    cases = load_cases(
        categories=categories,
        limit_per_category=limit,
        run_ids=run_ids,
    )
    console.print(f"Loaded [bold]{len(cases)}[/bold] cases.")

    scores = []
    for case in track(cases, description="Running ReAct agent"):
        trace = await run_case_with_timeout(
            case,
            recursion_limit=recursion_limit,
            timeout_seconds=case_timeout_seconds,
        )
        scores.append(score_case(case, trace))

    summary = write_reports(Path(args.output_dir), scores)
    console.print(f"[green]Evaluation complete.[/green] Output: {args.output_dir}")
    console.print_json(json.dumps(summary["overall"], ensure_ascii=False))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
