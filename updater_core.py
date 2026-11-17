from __future__ import annotations

import json
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


@dataclass
class Match:
    path: Path
    score: float
    common_prefix: int


@dataclass
class FileProposal:
    new_path: Path
    relative_path: Path
    matches: list[Match] = field(default_factory=list)
    selected_match: Path | None = None
    suggested_directory: Path | None = None
    path_score: float = 0.0
    approved: bool = False
    action: str = "replace"
    unchanged: bool = False

    def __post_init__(self) -> None:
        if not hasattr(self, "unchanged"):
            self.unchanged = False

    @property
    def is_new_file(self) -> bool:
        return not self.matches

    @property
    def destination(self) -> Path | None:
        if self.unchanged:
            return None
        if self.action == "replace" and self.selected_match:
            return self.selected_match.parent / self.new_path.name
        if self.suggested_directory:
            return self.suggested_directory / self.new_path.name
        return None


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def common_prefix_length(left: str, right: str) -> int:
    length = min(len(left), len(right))
    for index in range(length):
        if left[index].casefold() != right[index].casefold():
            return index
    return length


def filename_score(left: Path, right: Path) -> float:
    left_stem = normalize(left.stem)
    right_stem = normalize(right.stem)
    if not left_stem or not right_stem:
        return 0.0
    stem_similarity = SequenceMatcher(None, left_stem, right_stem).ratio()
    extension_score = 1.0 if left.suffix.casefold() == right.suffix.casefold() else 0.0
    prefix_score = common_prefix_length(left_stem, right_stem) / max(
        len(left_stem), len(right_stem)
    )
    return (stem_similarity * 0.55) + (extension_score * 0.25) + (prefix_score * 0.20)


def _segment_score(left: str, right: str) -> float:
    left_normalized = normalize(left)
    right_normalized = normalize(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    if left_normalized.startswith(right_normalized) or right_normalized.startswith(left_normalized):
        return 0.85
    return SequenceMatcher(None, left_normalized, right_normalized).ratio()


def path_score(source_parent: Path, target_directory: Path) -> float:
    source_parts = source_parent.parts
    target_parts = target_directory.parts
    if not source_parts:
        return 0.0
    scores = [
        max((_segment_score(source, target) for target in target_parts), default=0.0)
        for source in source_parts
    ]
    depth_bonus = 0.15 if len(source_parts) == len(target_parts) else 0.0
    return min(1.0, (sum(scores) / len(scores)) + depth_bonus)


def _files_under(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*") if path.is_file())


def _directories_under(folder: Path) -> list[Path]:
    return [folder, *sorted(path for path in folder.rglob("*") if path.is_dir())]


def analyze(new_root: Path, target_root: Path, *, minimum_match_score: float = 0.45) -> list[FileProposal]:
    new_root = new_root.resolve()
    target_root = target_root.resolve()
    obsolete_root = target_root / "Obsoletos"
    target_files = [
        path for path in _files_under(target_root)
        if obsolete_root not in path.parents
    ]
    target_directories = [
        path for path in _directories_under(target_root)
        if path != obsolete_root and obsolete_root not in path.parents
    ]
    files_by_name: dict[str, list[Path]] = {}
    files_by_extension: dict[str, list[Path]] = {}
    for target_file in target_files:
        files_by_name.setdefault(normalize(target_file.name), []).append(target_file)
        files_by_extension.setdefault(target_file.suffix.casefold(), []).append(target_file)
    proposals: list[FileProposal] = []

    for new_file in _files_under(new_root):
        relative = new_file.relative_to(new_root)
        exact_matches = files_by_name.get(normalize(new_file.name), [])
        if exact_matches:
            proposals.append(
                FileProposal(
                    new_path=new_file,
                    relative_path=relative,
                    matches=[
                        Match(
                            path=target_file,
                            score=1.0,
                            common_prefix=len(new_file.stem),
                        )
                        for target_file in exact_matches
                    ],
                    selected_match=exact_matches[0],
                    action="skip",
                    unchanged=True,
                )
            )
            continue
        candidate_files = files_by_extension.get(new_file.suffix.casefold(), target_files)
        matches = [
            Match(
                path=target_file,
                score=filename_score(new_file, target_file),
                common_prefix=common_prefix_length(new_file.stem, target_file.stem),
            )
            for target_file in candidate_files
        ]
        matches = sorted(
            (match for match in matches if match.score >= minimum_match_score),
            key=lambda match: (-match.score, str(match.path).casefold()),
        )
        suggested_directory: Path | None = None
        best_path_score = 0.0
        source_parent = relative.parent
        ranked_directories = sorted(
            (
                (path_score(source_parent, directory), directory)
                for directory in target_directories
            ),
            key=lambda item: (-item[0], str(item[1]).casefold()),
        )
        if ranked_directories:
            best_path_score, suggested_directory = ranked_directories[0]
        proposals.append(
            FileProposal(
                new_path=new_file,
                relative_path=relative,
                matches=matches,
                selected_match=matches[0].path if matches else None,
                suggested_directory=suggested_directory,
                path_score=best_path_score,
                action="replace" if matches else "copy",
            )
        )
    return proposals


def suggested_backup_directory(target_root: Path, requested_name: str | None = None) -> Path:
    name = requested_name.strip() if requested_name and requested_name.strip() else (
        f"Obsoletos_{datetime.now():%Y-%m-%d}"
    )
    return target_root / "Obsoletos" / name


def _available_backup_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}__{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _available_copy_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        suffix = "__novo" if counter == 1 else f"__novo_{counter}"
        candidate = path.with_name(f"{path.stem}{suffix}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def execute(
    proposals: Iterable[FileProposal],
    target_root: Path,
    backup_directory: Path,
) -> Path:
    target_root = target_root.resolve()
    backup_directory = backup_directory.resolve()
    manifest: list[dict[str, str]] = []
    for proposal in proposals:
        if not proposal.approved or proposal.destination is None:
            continue
        if not proposal.new_path.is_file():
            raise FileNotFoundError(f"Ficheiro novo não encontrado: {proposal.new_path}")
        destination = proposal.destination.resolve()
        if proposal.action == "replace" and proposal.selected_match:
            old_path = proposal.selected_match.resolve()
            if not old_path.is_file():
                raise FileNotFoundError(f"Match antigo não encontrado: {old_path}")
            relative_old = old_path.relative_to(target_root)
            backup_path = _available_backup_path(backup_directory / relative_old)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_path), str(backup_path))
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(proposal.new_path, destination)
            except OSError:
                shutil.move(str(backup_path), str(old_path))
                raise
            manifest.append(
                {
                    "action": "replaced",
                    "old": str(old_path),
                    "backup": str(backup_path),
                    "new": str(proposal.new_path),
                    "destination": str(destination),
                }
            )
            continue
        if proposal.action == "copy":
            destination = _available_copy_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        manifest.append(
            {
                "action": "added",
                "old": "",
                "backup": "",
                "new": str(proposal.new_path),
                "destination": str(destination),
            }
        )
        shutil.copy2(proposal.new_path, destination)

    backup_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = backup_directory / "relatorio.txt"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def rollback(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in reversed(manifest):
        if item["action"] == "replaced":
            old_path = Path(item["old"])
            destination = Path(item["destination"])
            if destination != old_path and destination.exists():
                destination.unlink()
            old_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(item["backup"], old_path)
        else:
            destination = Path(item["destination"])
            if destination.exists():
                destination.unlink()
