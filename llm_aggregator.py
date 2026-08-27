"""
LLM Aggregator for BGP Route Analysis
======================================
Reads three CSV files (each from a smaller LLM), then uses a larger LLM to aggregate and synthesise the results into a
final CSV output.

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
------
python3 ../../llm_aggregator.py --inputs ./deepseek-ai_reasoning_origin_conflicting_routes.txt ./Nemotron_reasoning_origin_conflicting_routes.txt ./qwen_reasoning_origin_conflicting_routes.txt --api-key EMPATY --provider openai

The script matches entries across the three files by "prefix" (primary key)
and sends each group to the large LLM for aggregation.
"""

import argparse
import csv
import json
import logging
import os
import time
from io import StringIO
from pathlib import Path
from typing import Any
import google.generativeai as genai
import requests
from fix_json_str import extract_and_fix_json
from openai import OpenAI
#from deepseek_agent import analyze_with_ChatOpenAI_model

# ---------------------------------------------------------------------------
# CSV schema
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# LLM Provider Configuration
# ---------------------------------------------------------------------------
# Supported providers: "gemini", "deepseek"
# Set via --provider argument or LLM_PROVIDER env var
# ---------------------------------------------------------------------------

PROVIDERS = {
    "gemini": {
        #"url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent",
        "model": "models/gemini-2.5-flash",
        "env_key": "GEMINI_API_KEY",
    },
    "deepseek": {
        "url": "http://localhost:8000/v1/chat/completions",
        "model": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
        "env_key": "DEEPSEEK_API_KEY",
    },
    
    "openai": {
        "url": "http://localhost:8000/v1",
        "model": "openai/gpt-oss-120b",
        "env_key": "EMPTY",
    },
}

MAX_TOKENS = 2048

SYSTEM_PROMPT = """
BGP hijacks occur when an adversary AS announces the same prefix or a more specific prefix of a victim AS. 

RPKI enforces Route Origin Validation (ROV) on BGP announcements to help prevent such hijacks. However, some RPKI-invalid routes result from operator misconfigurations between closely related ASes (e.g., same organization, IRR, known relationship), and are known as benign conflicts.

You are given three independent LLM analyses of the same RPKI-invalid BGP prefix. Your task is to aggregate them into a single, authoritative JSON output.

Objective

Determine whether the route is likely a benign conflict by inferring the relationship between the origin AS and the authorized AS(es) in ROAs, considering factors like business relationships, organizational ties, geographic proximity, etc. Note that more specific prefixes are commonly used in hijacks and cannot be considered reliable indicators of benign behavior on their own.

Instructions
- Output strictly in JSON format (no explanations, no markdown, no extra text).
- Preserve and include all required fields:
    "prefix"
    "AS_path" → always set to "N/A"
    "origin_AS"
    "authorized_ASes_in_ROAs"
    "benign_level"
    "explanation"
    "possible_reason"
    "factors"
    
- Ignore AS_path entirely and set it to "N/A".
- Merge explanations into one clear, non-redundant paragraph; remove weak or repetitive arguments.
- Reassess and assign a final benign_level based on combined evidence (ignore weak arguments by LLMs).
- Combine possible_reason into a single concise sentence.
- Union all unique factors from the three analyses (no duplicates).
- Add a new field "justification" and use only concise labels such as:
    "same region"
    "same organization"
    "strong relationship"
    "weak relationship"
    "no relationship"
    "others"

Benign Level Definition (3-Level Scale)
- High (Likely Benign Conflict with strong evidence of relationship):
    Same organization or subsidiaries,
    Customer–provider or sibling relationship,
    Shared infrastructure or tightly coupled operations,
    Very close geographic proximity.

- Medium (Possibly Benign with some indication of relationship, but not definitive):
    Same country or region,
    Indirect or inferred connections,
    Partial operational overlap.

- Low (Potential Hijack with little to no evidence of relationship):
    Different regions with no linkage,
    Unknown or unrelated ASes,
    Conflicting policies or suspicious patterns.


Output Schema
{
"prefix": "...",
"AS_path": "N/A",
"origin_AS": "...",
"authorized_ASes_in_ROAs": ["..."],
"benign_level": "...",
"explanation": "...",
"possible_reason": "...",
"factors": ["..."],
"justification": "..."
}
"""


def build_aggregation_prompt(entries: list[dict]) -> str:
    """Build the user prompt for aggregating three model outputs."""
    numbered = "\n\n".join(
        f"=== Model {i + 1} Output ===\n{json.dumps(e, indent=2)}"
        for i, e in enumerate(entries)
    )
    return (
        "Below are three separate analyses of the same BGP prefix produced by "
        "three different models. Aggregate them into a single authoritative "
        "JSON object following the rules in your system prompt.\n\n"
        + numbered
        + "\n\nReturn ONLY the aggregated JSON object."
    )


def _parse_llm_json(raw_text: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        parts = raw_text.split("```")
        raw_text = parts[1] if len(parts) > 1 else parts[0]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    return json.loads(raw_text.strip())

'''
def _call_gemini(prompt: str, api_key: str) -> dict:
   
    url = f"{PROVIDERS['gemini']['url']}?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + "\n\n" + prompt}
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": MAX_TOKENS,
            "temperature": 0.2,
        },
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_llm_json(raw_text)
'''




def _call_gemini(prompt: str, api_key: str) -> dict:
    genai.configure(api_key=api_key)
    # Step 3: Load model
    model = genai.GenerativeModel(PROVIDERS['gemini']['model'])
    
    # Step 4: Generate response
    response = model.generate_content(prompt)
    raw_text = response.text
    # Step 5: Return result
    return _parse_llm_json(raw_text)

'''
def _call_deepseek(prompt: str, api_key: str) -> dict:
    """Call DeepSeek API (OpenAI-compatible)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": PROVIDERS["deepseek"]["model"],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(PROVIDERS["deepseek"]["url"], headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    raw_text = data["choices"][0]["message"]["content"]
    return _parse_llm_json(raw_text)
'''


def _call_deepseek(prompt: str, api_key: str) -> dict:
    """Call DeepSeek API (OpenAI-compatible)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": PROVIDERS["deepseek"]["model"],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.6,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(PROVIDERS["deepseek"]["url"], headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    raw_text = data["choices"][0]["message"]["content"]
    clean_text = raw_text.replace("Ġ", " ").replace("Ċ", "\n").strip()
    # fix json string
    json_response = extract_and_fix_json(clean_text)
    print(json_response)
    #return _parse_llm_json(json_str)
    return json_response

def _call_openai(prompt: str, api_key: str) -> dict:
    
    client = OpenAI(
        base_url=PROVIDERS["openai"]["url"],
        api_key= api_key
    )
    
    result = client.chat.completions.create(
        model=PROVIDERS["openai"]["model"],
        temperature = 0.0,
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    
    
    response = result.choices[0].message.content
    # fix json string
    json_response = extract_and_fix_json(response)
    
    #return _parse_llm_json(json_str)
    return json_response





def call_large_llm(prompt: str, api_key: str, provider: str = "gemini", retries: int = 3) -> dict:
    """Call the selected LLM provider and return parsed JSON."""
    callers = {
        "gemini": _call_gemini,
        "deepseek": _call_deepseek,
        "openai": _call_openai
    }
    if provider not in callers:
        raise ValueError(f"Unknown provider '{provider}'. Choose from: {list(callers.keys())}")

    for attempt in range(1, retries + 1):
        try:
            return callers[provider](prompt, api_key)
        except requests.exceptions.HTTPError as exc:
            logging.warning("HTTP error on attempt %d/%d: %s", attempt, retries, exc)
            # Print response body for easier debugging
            try:
                logging.warning("Response body: %s", exc.response.text)
            except Exception:
                pass
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
        except json.JSONDecodeError as exc:
            logging.error("LLM returned non-JSON: %s", exc)
            raise


CSV_COLUMNS = [
    "prefix", "AS_path", "origin_AS", "authorized_ASes_in_ROAs",
    "benign_level", "explanation", "possible_reason", "factors",
]

OUTPUT_COLUMNS = CSV_COLUMNS + ["justification"]


def load_csv_file(path: str) -> list[dict]:
    """Load a CSV file and return a list of row dicts."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader]
    if not rows:
        raise ValueError(f"No data found in {path}")
    # Validate expected columns are present
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


def aggregate_all(
    model_files: list[str],
    api_key: str,
    provider: str = "gemini",
    verbose: bool = False,
) -> list[dict]:
    """Main aggregation loop."""
    if len(model_files) != 3:
        raise ValueError("Exactly three model output files are required.")

    # Load and index each file
    indexed: list[dict[tuple[str, str], dict]] = []
    for path in model_files:
        entries = load_csv_file(path)
        indexed.append(index_by_prefix(entries))
        logging.info("Loaded %d entries from %s", len(entries), path)

    # Union of all (prefix, origin_AS) keys
    all_keys: set[tuple[str, str]] = set()
    for idx in indexed:
        all_keys.update(idx.keys())

    logging.info("Total unique (prefix, origin_AS) pairs to aggregate: %d", len(all_keys))

    aggregated: list[dict] = []
    for key in sorted(all_keys):
        prefix, origin_as = key
        entries_for_key = [idx.get(key) for idx in indexed]
        present = [e for e in entries_for_key if e is not None]

        if len(present) == 1:
            # Only one model analysed this (prefix, origin_AS) — pass through with a note
            result = present[0].copy()
            result["aggregation_confidence"] = "Low"
            result["model_agreement_summary"] = (
                "Only one of three models provided an analysis for this route."
            )
            aggregated.append(result)
            logging.warning("Prefix %s (origin %s) found in only 1 model output; passing through.", prefix, origin_as)
            continue

        if len(present) == 2:
            logging.warning("Prefix %s (origin %s) found in only 2 of 3 model outputs.", prefix, origin_as)

        prompt = build_aggregation_prompt(present)

        if verbose:
            print(f"\n[Aggregating prefix: {prefix}, origin: {origin_as}]")
            print(prompt[:400], "...\n")

        try:
            result = call_large_llm(prompt, api_key, provider=provider)
            print(result)
            aggregated.append(result)
            logging.info("Aggregated prefix %s (origin %s)  confidence=%s", prefix, origin_as, result.get("aggregation_confidence"))
        except Exception as exc:
            logging.error("Failed to aggregate prefix %s (origin %s): %s", prefix, origin_as, exc)
            # Fall back: use the entry from the first model that has it
            fallback = present[0].copy()
            fallback["aggregation_confidence"] = "Low"
            fallback["model_agreement_summary"] = f"Aggregation failed: {exc}"
            aggregated.append(fallback)

    return aggregated


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate BGP analyses from three smaller LLMs using a larger LLM."
    )
    parser.add_argument(
        "--inputs",
        nargs=3,
        metavar="FILE",
        required=True,
        help="Exactly three CSV output files from smaller LLMs.",
    )
    parser.add_argument(
        "--output",
        default="aggregated_output.csv",
        help="Path for the aggregated CSV output (default: aggregated_output.csv).",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("LLM_PROVIDER", "gemini"),
        choices=["gemini", "deepseek", "openai"],
        help="LLM provider to use for aggregation (default: gemini).",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help=(
            "API key for the selected provider. "
            "Defaults to GEMINI_API_KEY or DEEPSEEK_API_KEY env var depending on --provider."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print prompts and partial outputs to stdout.",
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
            # Serialise factors list to string for CSV storage
            if isinstance(e["factors"], list):
                e["factors"] = str(e["factors"])
            # Add minor variation per model to simulate real disagreement
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

    # Resolve API key: --api-key flag > provider-specific env var
    api_key = args.api_key or os.environ.get(PROVIDERS[args.provider]["env_key"], "")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # ------------------------------------------------------------------
    # Demo mode: if no real input files are provided, generate samples
    # and run against the API (if a key is available) or just show structure
    # ------------------------------------------------------------------
    demo_mode = False
    input_files = args.inputs

    for f in input_files:
        if not Path(f).exists():
            logging.warning("Input file not found: %s — switching to demo mode.", f)
            demo_mode = True
            break

    if demo_mode:
        print("\n[Demo mode] Generating sample input files …")
        sample_dir = Path(args.output).parent
        input_files = write_sample_inputs(sample_dir)

    if not api_key:
        print(
            f"\n[Dry-run] No API key found for provider '{args.provider}'. "
            f"Please set the {PROVIDERS[args.provider]['env_key']} environment variable.\n"
            "Displaying the aggregation prompt for the first prefix group.\n"
        )
        all_indexed = [index_by_prefix(load_csv_file(f)) for f in input_files]
        all_prefixes = sorted(set().union(*[set(idx.keys()) for idx in all_indexed]))
        for prefix in all_prefixes[:1]:
            present = [idx[prefix] for idx in all_indexed if prefix in idx]
            print(build_aggregation_prompt(present))
        return

    logging.info("Using provider: %s", args.provider)

    # Full run
    results = aggregate_all(input_files, api_key, provider=args.provider, verbose=args.verbose)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            # Normalise factors: if it's a list, convert to string representation
            if isinstance(row.get("factors"), list):
                row["factors"] = str(row["factors"])
            writer.writerow(row)
    print(f"\nAggregated {len(results)} prefix(es) → {output_path}")


if __name__ == "__main__":
    main()
