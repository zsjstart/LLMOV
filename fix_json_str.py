import re
import json
from json_repair import repair_json


def extract_and_fix_json(text):
    # Extract JSON block
    start = text.find('{')
    end = text.rfind('}') + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON found in text")

    json_str = text[start:end]
    json_str = json_str.strip().replace("```json", "").replace("```", "").strip()

    # Fix 1: escaped underscores  "origin\_AS" -> "origin_AS"
    json_str = re.sub(r'\\\_', '_', json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return json.loads(repair_json(json_str))
