"""
Median Aggregator for BGP Route Analysis
=========================================
Reads three CSV files (each from a single-classifier LLM) and aggregates them
into a final CSV by taking the ordinal median of their benign_level verdicts
per route — no LLM call involved.

Why not an LLM judge: on a 45-route expert-labeled sample, an LLM judge
(gpt-oss-120b, prompted to synthesise the three classifiers' outputs) scored
worse than every individual classifier (quadratic-weighted kappa vs. expert
judgment: 0.133, "slight" agreement) and worse than this plain median (0.784,
"substantial" agreement). Inspecting the judge's own output showed it was
hallucinating disagreement between the three classifiers that didn't exist —
e.g. claiming "Model 2 assessed it as Medium" when all three had actually
agreed on High — and defaulting to a hedged Medium as a result. The median
has no such failure mode: it's deterministic, free, and reproducible.

Expected CSV columns
--------------------
prefix, AS_path, origin_AS, authorized_ASes_in_ROAs, benign_level,
explanation, possible_reason, factors

Example row
-----------
190.26.0.0/16,,AS32034,AS19429,Low,"AS32034 is an ARIN-registered...","An accidental...","['Hijacks', 'Others: Misconfiguration']"

Usage
-----
python llm_aggregator.py \
    --inputs model1_output.csv model2_output.csv model3_output.csv \
    --output aggregated_output.csv \
    [--verbose]

Example
-------
python3 llm_aggregator.py --inputs ./deepseek-ai_reasoning_origin_conflicting_routes.txt ./Nemotron_reasoning_origin_conflicting_routes.txt ./qwen_reasoning_origin_conflicting_routes.txt

The script matches entries across the three files by (prefix, origin_AS) and
takes the median benign_level per route.
"""

import argparse
import csv
import logging
from pathlib import Path
from typing import Any

LEVEL_ORDER = ["Low", "Medium", "High"]
LEVEL_RANK = {level: i for i, level in enumerate(LEVEL_ORDER)}

CSV_COLUMNS = [
    "prefix", "AS_path", "origin_AS", "authorized_ASes_in_ROAs",
    "benign_level", "explanation", "possible_reason", "factors",
]

OUTPUT_COLUMNS = CSV_COLUMNS + ["aggregation_confidence", "model_agreement_summary"]


def load_csv_file(path: str) -> list[dict]:
    """Load a CSV file and return a list of row dicts."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader]
    if not rows:
        raise ValueError(f"No data found in {path}")
    missing = [c for c in CSV_COLUMNS if c not in rows[0]]
    if missing:
        raise ValueError(f"Missing columns in {path}: {missing}")
    return rows


def index_by_prefix(entries: list[dict]) -> dict[tuple[str, str], dict]:
    """Return a dict keyed by (prefix, origin_AS).

    Keying by prefix alone silently drops distinct events: the same prefix
    can be hijacked/misannounced by different origin ASes at different
    times, and each such row would otherwise overwrite the previous one.
    """
    return {(e["prefix"], e["origin_AS"]): e for e in entries}


def _union_factors(entries: list[dict]) -> list[str]:
    """Union the (string-repr) factors lists from each entry, de-duplicated, order-preserved."""
    seen: list[str] = []
    for e in entries:
        raw = e.get("factors", "")
        # factors are stored as a Python-list repr string, e.g. "['Hijacks', 'Others']"
        for item in raw.strip("[]").split(","):
            item = item.strip().strip("'\"")
            if item and item not in seen:
                seen.append(item)
    return seen


def aggregate_by_median(key: tuple[str, str], present: list[dict]) -> dict:
    """Aggregate one route's entries by the ordinal median of benign_level.

    - 3 present: true median (the middle value once sorted; no tie-breaking needed).
    - 2 present, disagreeing: takes the lower (more cautious) of the two, since
      erring toward flagging a route for review is the safer operational default.
    - 1 present: pass through as-is, at Low confidence.
    """
    prefix, origin_as = key
    ranked = sorted(present, key=lambda e: LEVEL_RANK.get(e["benign_level"].strip(), 1))
    levels = [e["benign_level"].strip() for e in ranked]

    if len(present) == 1:
        median_entry = ranked[0]
        confidence = "Low"
        summary = "Only one of three models provided an analysis for this route."
    elif len(present) == 2:
        median_entry = ranked[0]  # lower of the two
        confidence = "Medium" if levels[0] == levels[1] else "Low"
        summary = (
            f"Only two of three models covered this route ({levels[0]} vs {levels[1]}); "
            f"took the more cautious ({levels[0]})."
            if levels[0] != levels[1]
            else f"Both available models agreed on {levels[0]}."
        )
    else:
        median_entry = ranked[1]  # true median of 3
        if levels[0] == levels[1] == levels[2]:
            confidence = "High"
            summary = f"All three models agreed on {levels[0]}."
        elif len(set(levels)) == 2:
            confidence = "Medium"
            summary = f"Two of three models agreed on {ranked[1]['benign_level'].strip()} ({', '.join(levels)}); median used."
        else:
            confidence = "Low"
            summary = f"All three models disagreed ({', '.join(levels)}); median ({levels[1]}) used."

    result = {
        "prefix": prefix,
        "AS_path": median_entry.get("AS_path", "N/A"),
        "origin_AS": origin_as,
        "authorized_ASes_in_ROAs": median_entry.get("authorized_ASes_in_ROAs", ""),
        "benign_level": median_entry["benign_level"].strip(),
        "explanation": median_entry.get("explanation", ""),
        "possible_reason": median_entry.get("possible_reason", ""),
        "factors": _union_factors(present),
        "aggregation_confidence": confidence,
        "model_agreement_summary": summary,
    }
    return result


def aggregate_all(model_files: list[str], verbose: bool = False) -> list[dict]:
    """Main aggregation loop."""
    if len(model_files) != 3:
        raise ValueError("Exactly three model output files are required.")

    indexed: list[dict[tuple[str, str], dict]] = []
    for path in model_files:
        entries = load_csv_file(path)
        indexed.append(index_by_prefix(entries))
        logging.info("Loaded %d entries from %s", len(entries), path)

    all_keys: set[tuple[str, str]] = set()
    for idx in indexed:
        all_keys.update(idx.keys())

    logging.info("Total unique (prefix, origin_AS) pairs to aggregate: %d", len(all_keys))

    aggregated: list[dict] = []
    for key in sorted(all_keys):
        entries_for_key = [idx.get(key) for idx in indexed]
        present = [e for e in entries_for_key if e is not None]

        if len(present) < 3:
            logging.warning("Prefix %s (origin %s) found in only %d of 3 model outputs.", key[0], key[1], len(present))

        result = aggregate_by_median(key, present)
        aggregated.append(result)

        if verbose:
            print(f"[{key[0]} / {key[1]}] -> {result['benign_level']} (confidence={result['aggregation_confidence']}) — {result['model_agreement_summary']}")

    return aggregated


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate BGP analyses from three classifier LLMs by ordinal median (no LLM judge)."
    )
    parser.add_argument(
        "--inputs",
        nargs=3,
        metavar="FILE",
        required=True,
        help="Exactly three CSV output files from the single-classifier LLMs.",
    )
    parser.add_argument(
        "--output",
        default="aggregated_output.csv",
        help="Path for the aggregated CSV output (default: aggregated_output.csv).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each route's aggregation result to stdout.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Demo helpers — generate sample input files so the script can be tested
# without real model outputs.
# ---------------------------------------------------------------------------
SAMPLE_ENTRIES: list[dict[str, Any]] = [
    {
        "prefix": "190.26.0.0/16",
        "AS_path": "",
        "origin_AS": "AS32034",
        "authorized_ASes_in_ROAs": "AS19429",
        "benign_level": "Low",
        "explanation": (
            "AS32034 is an ARIN-registered operator (Newcom-Intl Speedcast LATAM Inc.) "
            "located in the US/Western IGI region, whereas the ROA is issued for AS19429, "
            "a Colombian telecom (ETB). The two ASes have no documented economic or policy "
            "link, no shared ownership, and the prefix was historically advertised only by "
            "AS19429. No AS-path information is available to confirm a customer/peer "
            "relationship, and the transfer history shows no re-allocation of the prefix "
            "to AS32034. Thus the announcement likely stems from an inadvertent "
            "misconfiguration or malicious hijack rather than a benign multi-origin scenario."
        ),
        "possible_reason": (
            "An accidental mis-announcement of the entire /16 by AS32034—possibly due to "
            "a configuration error on a transit connection or an attempt to advertise a "
            "service edge without proper RPKI coverage."
        ),
        "factors": ["Hijacks", "Others: Misconfiguration"],
    },
    {
        "prefix": "203.0.113.0/24",
        "AS_path": "AS64496 AS64497",
        "origin_AS": "AS64497",
        "authorized_ASes_in_ROAs": "AS64497",
        "benign_level": "High",
        "explanation": (
            "The origin AS matches the ROA-authorized AS exactly. "
            "The AS-path is short and consistent with normal transit routing."
        ),
        "possible_reason": "Legitimate advertisement by the authorised origin AS.",
        "factors": ["Legitimate"],
    },
]


def write_sample_inputs(base_dir: Path) -> list[str]:
    """Write three slightly varied sample CSV files for demo/testing."""
    paths = []
    for i in range(1, 4):
        entries = []
        for entry in SAMPLE_ENTRIES:
            e = entry.copy()
            if isinstance(e["factors"], list):
                e["factors"] = str(e["factors"])
            if i == 2 and e["prefix"] == "190.26.0.0/16":
                e["benign_level"] = "Medium"
                e["explanation"] = e["explanation"] + " (Model 2: slightly less certain about intent.)"
            if i == 3 and e["prefix"] == "190.26.0.0/16":
                e["factors"] = "['Hijacks']"
            entries.append(e)

        path = base_dir / f"model{i}_output.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(entries)
        paths.append(str(path))
        print(f"  Written sample input: {path}")
    return paths


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    input_files = args.inputs
    for f in input_files:
        if not Path(f).exists():
            logging.warning("Input file not found: %s — switching to demo mode.", f)
            sample_dir = Path(args.output).parent
            input_files = write_sample_inputs(sample_dir)
            break

    results = aggregate_all(input_files, verbose=args.verbose)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            if isinstance(row.get("factors"), list):
                row["factors"] = str(row["factors"])
            writer.writerow(row)
    print(f"\nAggregated {len(results)} route(s) -> {output_path}")


if __name__ == "__main__":
    main()
