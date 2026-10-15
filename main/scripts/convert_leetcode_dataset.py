"""Select and normalize a topic-balanced subset from the supplied licensed JSONL."""
from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend/app/data/coding_problems"
SOURCE = DATA / "LeetCodeDataset-train.jsonl"
TARGET = DATA / "catalog.json"
MAX_PER_TOPIC = 22
TARGET_COUNT = 150
TOPICS = {
    "array": "arrays/strings", "string": "arrays/strings", "hash table": "hash maps",
    "two pointers": "two pointers", "sliding window": "sliding window", "linked list": "linked lists",
    "tree": "trees", "binary tree": "trees", "graph": "graphs", "dynamic programming": "dynamic programming",
    "binary search": "binary search", "stack": "stacks/queues", "queue": "stacks/queues",
    "heap": "heaps", "heap (priority queue)": "heaps", "priority queue": "heaps", "greedy": "greedy", "backtracking": "backtracking",
    "depth-first search": "graphs", "breadth-first search": "graphs", "monotonic stack": "stacks/queues",
}


def parse_cases(source: str, signature: list[str]) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare) or len(node.test.ops) != 1:
            continue
        if not isinstance(node.test.ops[0], ast.Eq) or not isinstance(node.test.left, ast.Call):
            continue
        call = node.test.left
        expected_node = node.test.comparators[0]
        if isinstance(call.func, ast.Name) and call.func.id == "is_same_list" and call.args:
            candidate_call = next((child for child in ast.walk(call.args[0]) if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "candidate"), None)
            if candidate_call is None or len(call.args) < 2:
                continue
            call = candidate_call
            expected_node = call.args[1] if False else node.test.left.args[1]
        if not isinstance(call.func, ast.Name) or call.func.id != "candidate":
            continue
        def value(node: ast.AST) -> Any:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "list_node" and node.args:
                return {"__vue_type__": "ListNode", "values": ast.literal_eval(node.args[0])}
            return ast.literal_eval(node)
        values: dict[str, Any] = {}
        try:
            for kw in call.keywords:
                if kw.arg is not None:
                    values[kw.arg] = value(kw.value)
            for i, arg in enumerate(call.args):
                if i < len(signature):
                    values[signature[i]] = value(arg)
            expected = value(expected_node)
            if isinstance(expected, dict) and expected.get("__vue_type__") == "ListNode":
                expected = expected["values"]
        except (ValueError, TypeError, SyntaxError):
            continue
        if not values or any(not isinstance(v, (str, int, float, bool, list, dict, type(None))) for v in values.values()):
            continue
        out.append({"input": [values[name] for name in signature if name in values], "expected": expected})
    # Keep unique cases only, preserving source order.
    unique = []
    seen = set()
    for case in out:
        key = json.dumps(case, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            unique.append(case)
            seen.add(key)
    return unique


def function_signature(starter: str, method: str) -> list[str]:
    try:
        tree = ast.parse(starter.rstrip() + "\n            pass\n")
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method:
            args = node.args.args
            return [arg.arg for arg in args if arg.arg != "self"]
    return []


def clean_text(text: str) -> str:
    return text.replace("Â ", " ").replace("\xa0", " ").replace("\r\n", "\n").strip()


def edge_tags(value: Any) -> list[str]:
    tags: set[str] = set()
    def visit(item: Any) -> None:
        if isinstance(item, list):
            if not item:
                tags.add("empty input")
            if len(item) == 1:
                tags.add("single element")
            scalars = [x for x in item if not isinstance(x, (list, dict))]
            try:
                if len(set(scalars)) < len(scalars):
                    tags.add("duplicates")
            except TypeError:
                pass
            for child in item:
                visit(child)
        elif isinstance(item, dict):
            if item.get("__vue_type__") == "ListNode":
                if not item.get("values"):
                    tags.add("empty linked list")
                if len(item.get("values", [])) == 1:
                    tags.add("single node")
                visit(item.get("values", []))
            else:
                for child in item.values():
                    visit(child)
        elif isinstance(item, str) and not item:
            tags.add("empty string")
        elif isinstance(item, (int, float)):
            if item == 0:
                tags.add("zero boundary")
            if abs(item) >= 10**9:
                tags.add("large numeric boundary")
    visit(value)
    return sorted(tags)


def main() -> None:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with SOURCE.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
                task_id = row["task_id"]
                if not re.fullmatch(r"[a-z0-9-]+", task_id):
                    continue
                mapped = list(dict.fromkeys(TOPICS[tag.casefold()] for tag in row.get("tags", []) if tag.casefold() in TOPICS))
                if not mapped:
                    continue
                entry = row.get("entry_point", "")
                method = entry.rsplit(".", 1)[-1]
                signature = function_signature(row.get("starter_code", ""), method)
                if not signature:
                    continue
                cases = parse_cases(row.get("test", ""), signature)
                if task_id == "two-sum" and {"nums", "target"}.issubset(signature):
                    cases = [case for case in cases if any(
                        case["input"][0][i] + case["input"][0][j] == case["input"][1]
                        for i in range(len(case["input"][0])) for j in range(i + 1, len(case["input"][0]))
                    )]
                if len(cases) < 3 or not any(edge_tags(case["input"]) for case in cases):
                    continue
                solution = clean_text(row.get("completion", ""))
                if solution.startswith("```"):
                    solution = re.sub(r"^```(?:python)?\s*|\s*```$", "", solution)
                if "class Solution" not in solution or not solution.strip():
                    continue
                for topic in mapped:
                    candidates[topic].append({"row": row, "topic": topic, "method": method,
                                              "signature": signature, "cases": cases, "solution": solution})
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                continue
    selected: dict[str, dict[str, Any]] = {}
    # Round-robin across topic categories, deduplicating problems tagged in multiple groups.
    categories = list(dict.fromkeys(TOPICS.values()))
    category_items = {topic: candidates.get(topic, []) for topic in categories}
    topic_positions = defaultdict(int)
    while len(selected) < TARGET_COUNT:
        progressed = False
        for topic in categories:
            bucket = category_items[topic]
            if sum(topic in [TOPICS[tag.casefold()] for tag in p["row"].get("tags", []) if tag.casefold() in TOPICS]
                   for p in selected.values()) >= MAX_PER_TOPIC:
                continue
            while topic_positions[topic] < len(bucket):
                candidate = bucket[topic_positions[topic]]
                topic_positions[topic] += 1
                row = candidate["row"]
                if row["task_id"] in selected:
                    continue
                selected[row["task_id"]] = candidate
                progressed = True
                break
            if len(selected) >= TARGET_COUNT:
                break
        if not progressed:
            break
    problems = []
    for task_id, item in selected.items():
        row = item["row"]
        cases = item["cases"][:30]
        edge_tags_seen: set[str] = set()
        for i, case in enumerate(cases):
            tags = edge_tags(case["input"])
            if tags:
                case["tags"] = tags
                edge_tags_seen.update(tags)
        difficulty = row.get("difficulty", "Medium")
        difficulty = difficulty if difficulty in {"Easy", "Medium", "Hard"} else "Medium"
        description = clean_text(row.get("problem_description", ""))
        examples = [{"input": c["input"], "output": c["expected"]} for c in cases[:3]]
        problems.append({
            "id": task_id, "title": row["task_id"].replace("-", " ").title(), "difficulty": difficulty,
            "topics": list(dict.fromkeys([item["topic"]] + [TOPICS[tag.casefold()] for tag in row.get("tags", []) if tag.casefold() in TOPICS])),
            "statement": description, "constraints": [line.strip(" •") for line in description.splitlines() if re.search(r"<=|≤|constraint", line, re.I)][:20] or ["Follow the input bounds described in the statement."],
            "examples": examples, "reference_solution": item["solution"],
            "entry_point": item["method"], "parameter_names": item["signature"],
            "test_cases": cases, "sample_test_cases": cases[:min(3, len(cases))],
            "edge_case_tags": sorted(edge_tags_seen), "verified": False,
            "source": {"name": "newfacade/LeetCodeDataset", "license": "Apache-2.0", "url": "https://github.com/newfacade/LeetCodeDataset", "task_id": row["task_id"], "question_id": row.get("question_id")},
        })
    TARGET.write_text(json.dumps({"schema_version": 1, "problems": problems}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected": len(problems), "topic_counts": {topic: sum(topic in p["topics"] for p in problems) for topic in categories if any(topic in p["topics"] for p in problems)}, "difficulty_counts": {d: sum(p["difficulty"] == d for p in problems) for d in ("Easy", "Medium", "Hard")}}, indent=2))


if __name__ == "__main__":
    main()
