import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-comparison", type=Path)
    parser.add_argument("--resource-report", type=Path)
    parser.add_argument("--canary-validation", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--min-reduction-pct", type=float, default=20.0)
    parser.add_argument("--min-observations", type=int, default=1)
    return parser.parse_args()


def policy_comparison_check(args: argparse.Namespace) -> dict[str, Any]:
    if not args.policy_comparison:
        return {"name": "policy_projection", "passed": False, "reason": "--policy-comparison not provided"}
    parsed = read_json(args.policy_comparison)
    reduction = number_at(parsed, "total_reduction_pct")
    if reduction is None:
        return {"name": "policy_projection", "passed": False, "reason": "total_reduction_pct missing"}
    return {
        "name": "policy_projection",
        "passed": reduction >= args.min_reduction_pct,
        "evidence": f"{reduction:.1f}% projected reduction",
        **({} if reduction >= args.min_reduction_pct else {"reason": f"below {args.min_reduction_pct:.1f}%"}),
    }


def resource_observation_check(args: argparse.Namespace) -> dict[str, Any]:
    if not args.resource_report:
        return {"name": "resource_observations", "passed": False, "reason": "--resource-report not provided"}
    parsed = read_json(args.resource_report)
    count = number_at(parsed, "observation_count")
    if count is None:
        return {"name": "resource_observations", "passed": False, "reason": "observation_count missing"}
    return {
        "name": "resource_observations",
        "passed": count >= args.min_observations,
        "evidence": f"{int(count)} observations",
        **({} if count >= args.min_observations else {"reason": f"below {args.min_observations}"}),
    }


def canary_validation_check(args: argparse.Namespace) -> dict[str, Any]:
    if not args.canary_validation:
        return {"name": "remote_canary_validation", "passed": False, "reason": "--canary-validation not provided"}
    if not args.canary_validation.exists():
        return {"name": "remote_canary_validation", "passed": False, "reason": f"canary validation file not found: {args.canary_validation}"}
    parsed = read_json(args.canary_validation)
    passed = parsed.get("passed") if isinstance(parsed, dict) else None
    reduction = number_at(parsed, "total_reduction_pct")
    if passed is not True:
        return {
            "name": "remote_canary_validation",
            "passed": False,
            **({"evidence": f"{reduction:.1f}% actual reduction"} if reduction is not None else {}),
            "reason": "canary validator did not pass",
        }
    if reduction is None or reduction < args.min_reduction_pct:
        return {
            "name": "remote_canary_validation",
            "passed": False,
            **({"evidence": f"{reduction:.1f}% actual reduction"} if reduction is not None else {}),
            "reason": f"actual reduction below {args.min_reduction_pct:.1f}%",
        }
    return {"name": "remote_canary_validation", "passed": True, "evidence": f"{reduction:.1f}% actual reduction"}


def markdown_report(checks: list[dict[str, Any]], args: argparse.Namespace) -> str:
    return "\n".join(
        [
            "# Cost Reduction Goal Audit",
            "",
            f"Generated: {iso_now()}",
            "",
            f"Minimum reduction: {args.min_reduction_pct:.1f}%",
            f"Minimum observations: {args.min_observations}",
            "",
            "check | status | evidence | reason",
            "--- | --- | --- | ---",
            *[
                " | ".join([check["name"], "pass" if check["passed"] else "fail", check.get("evidence") or "-", check.get("reason") or "-"])
                for check in checks
            ],
            "",
            f"Overall: {'pass' if all(check['passed'] for check in checks) else 'fail'}",
            "",
        ]
    )


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return parsed


def number_at(value: Any, key: str) -> float | None:
    item = value.get(key) if isinstance(value, dict) else None
    return float(item) if isinstance(item, (int, float)) and math.isfinite(item) else None


def write_output(path: Path | None, content: str) -> None:
    if path is None:
        print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    args = parse_args()
    checks = [policy_comparison_check(args), resource_observation_check(args), canary_validation_check(args)]
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "min_reduction_pct": args.min_reduction_pct,
        "min_observations": args.min_observations,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    content = json.dumps(payload, indent=2) + "\n" if args.format == "json" else markdown_report(checks, args)
    write_output(args.output, content)
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
