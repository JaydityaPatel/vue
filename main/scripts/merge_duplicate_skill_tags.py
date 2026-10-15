"""Merge the four Phase 10 near-duplicate tags into two stable taxonomy rows.

Defaults to a read-only preview. Apply once with:
  python scripts/merge_duplicate_skill_tags.py --apply
The script makes a SQLite backup in the system temp directory before mutation.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1] / "backend"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import InterviewSession, SkillTag, TurnScore  # noqa: E402

# Keep the earlier established spelling as each canonical label. Topic titles
# remain untouched; only taxonomy references are consolidated.
MERGES = {
    "PostgreSQL Data Modeling and Query Optimization": "PostgreSQL Performance Tuning and Indexing",
    "Containerization and Docker Workflow": "Containerization and CI/CD Workflows",
}


def backup_sqlite() -> Path:
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Automatic safety backup currently supports the configured SQLite database only")
    source_path = Path(engine.url.database or "").resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Configured SQLite database not found: {source_path}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = Path(tempfile.gettempdir()) / f"vue-before-skill-tag-merge-{stamp}.sqlite3"
    with sqlite3.connect(source_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    return backup_path


def _replace_ids(value, id_map: dict[str, str], name_map: dict[str, str]):
    if isinstance(value, list):
        return [_replace_ids(item, id_map, name_map) for item in value]
    if isinstance(value, dict):
        updated = {}
        for key, item in value.items():
            if key == "skill_tag_id" and isinstance(item, str):
                updated[key] = id_map.get(item, item)
            elif key == "skill_tag" and isinstance(item, str):
                updated[key] = name_map.get(item, item)
            else:
                updated[key] = _replace_ids(item, id_map, name_map)
        return updated
    return value


def migrate(db: Session, *, apply: bool) -> dict:
    tags = {tag.name: tag for tag in db.scalars(select(SkillTag))}
    id_map: dict[str, str] = {}
    active_merges = {duplicate: canonical for duplicate, canonical in MERGES.items() if duplicate in tags}
    missing_canonicals = [canonical for canonical in MERGES.values() if canonical not in tags]
    if missing_canonicals:
        raise RuntimeError("Expected canonical tags are missing: " + ", ".join(missing_canonicals))
    already_merged = [duplicate for duplicate in MERGES if duplicate not in tags]
    name_map = dict(active_merges)
    for duplicate_name, canonical_name in active_merges.items():
        duplicate, canonical = tags[duplicate_name], tags[canonical_name]
        id_map[duplicate.id] = canonical.id
        if canonical.category is None and duplicate.category is not None:
            canonical.category = duplicate.category

    score_rows = list(db.scalars(select(TurnScore)))
    changed_scores = 0
    for score in score_rows:
        before = list(score.skill_tags or [])
        after = list(dict.fromkeys(name_map.get(name, name) for name in before))
        if after != before:
            changed_scores += 1
            if apply:
                score.skill_tags = after

    sessions = list(db.scalars(select(InterviewSession)))
    changed_sessions = 0
    for session in sessions:
        config = _replace_ids(session.config or {}, id_map, name_map)
        if config != (session.config or {}):
            changed_sessions += 1
            if apply:
                session.config = config

    before_tags = sorted(tags)
    if apply:
        for duplicate_name in active_merges:
            db.delete(tags[duplicate_name])
        db.flush()
        after_tags = sorted(tag.name for tag in db.scalars(select(SkillTag)))
    else:
        after_tags = sorted(set(before_tags) - set(active_merges))
    return {
        "mode": "apply" if apply else "dry-run",
        "before_count": len(before_tags),
        "after_count": len(after_tags),
        "before_tags": before_tags,
        "after_tags": after_tags,
        "merges": active_merges,
        "already_merged": already_merged,
        "turn_score_rows_updated": changed_scores,
        "session_configs_updated": changed_sessions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply the merge; default only previews it")
    args = parser.parse_args()
    backup = backup_sqlite() if args.apply else None
    with SessionLocal.begin() as db:
        result = migrate(db, apply=args.apply)
    if backup:
        result["backup_path"] = str(backup)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
