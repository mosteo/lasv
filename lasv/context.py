"""
Shared context and type definitions for LASV.
"""

import os
from dataclasses import dataclass
from enum import Enum

import semver
import yaml
from tqdm import tqdm


class ChangeType(Enum):
    """Enumeration for the type of change."""
    MAJOR = "MAJOR"
    MINOR = "minor"


class Compliance(Enum):
    """Enumeration for compliance status."""
    STRICT = "strict"
    LAX = "lax"
    NO = "no"
    ERROR = "error"  # Error during analysis


class BumpType(Enum):
    """Enumeration for version bump types."""
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    NONE = "none"


def normalize_model_name(model: str | None) -> str | None:
    """
    Normalize model name for storage so ':free' variants map to the same key.
    """
    if not model:
        return None
    if model.endswith(":free"):
        return model[:-5]
    return model


def fix_context_data(context: "LasvContext") -> int:
    """
    Normalize stored model keys by removing ':free' suffixes.
    Returns the number of keys updated.
    """
    from lasv import releases
    fixed_count = 0
    crates_data = context.data.get("crates", {})
    release_entries = []
    for crate_name, crate_data in crates_data.items():
        releases_dict = crate_data.get("releases", {})
        for release_version, release_data in releases_dict.items():
            release_entries.append((crate_name, release_version, release_data))
    for crate_name, release_version, release_data in tqdm(
        release_entries, desc="Normalizing model keys"
    ):
        diagnosis = release_data.get("diagnosis")
        if not isinstance(diagnosis, dict):
            continue
        prev_version = None
        for key in list(diagnosis.keys()):
            if key.endswith(":free"):
                new_key = normalize_model_name(key)
                if new_key and new_key != key:
                    diagnosis[new_key] = diagnosis.pop(key)
                    fixed_count += 1
        for analyzer_key, analyzer_data in list(diagnosis.items()):
            if analyzer_key == "from_version":
                continue
            if not isinstance(analyzer_data, dict):
                continue
            if "compliant" not in analyzer_data:
                del diagnosis[analyzer_key]
                fixed_count += 1
                continue
            if "from_version" in analyzer_data:
                del analyzer_data["from_version"]
                fixed_count += 1
        if "from_version" not in diagnosis:
            if prev_version is None:
                prev_version = releases.find_previous_version(
                    crate_name, release_version
                )
            if prev_version:
                diagnosis["from_version"] = prev_version
                fixed_count += 1
    return fixed_count


@dataclass
class ChangeInfo:
    """Information about a detected change."""
    severity: ChangeType
    line: int
    col: int
    description: str
    filename: str = ""  # Optional filename where the change occurred (new version)
    old_filename: str = ""  # Optional filename for the old version (for diffs)


class LasvContext:
    """Encapsulates lasv context data with load/save functionality."""

    def __init__(self, filename="lasv.yaml"):
        self.filename = filename
        self.data = {}
        self.model = None
        self.model_key = None
        self.full = False
        self.blacklist = set()

    def load(self):
        """Load context from YAML file."""
        if os.path.exists(self.filename):
            print(f"Loading context from {self.filename}...")
            with open(self.filename, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                self.data = loaded if loaded else {}

        if 'crates' not in self.data:
            self.data['crates'] = {}

        return self.data

    def load_config(self, filename: str = "config.yaml") -> None:
        """
        Load optional configuration data.
        Currently supports: blacklist -> list of crate names.
        """
        if not os.path.exists(filename):
            return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as e:
            print(f"Warning: could not load {filename}: {e}")
            return

        blacklist = config.get("blacklist", [])
        if isinstance(blacklist, list):
            self.blacklist = {str(name) for name in blacklist}
        else:
            print(f"Warning: {filename} blacklist must be a list.")

    def clear_diagnosis(self, crate: str) -> None:
        """Remove all diagnosis data for a given crate."""
        if 'crates' in self.data and crate in self.data['crates']:
            crate_data = self.data['crates'][crate]
            if 'releases' in crate_data:
                for release in crate_data['releases'].values():
                    if 'diagnosis' in release:
                        del release['diagnosis']
                self.save()

    def start_diagnosis(
        self, crate: str, version: str, analyzer: str, from_version: str | None = None
    ) -> None:
        """Initialize diagnosis structure for a specific analyzer."""
        if 'crates' not in self.data:
            self.data['crates'] = {}
        if crate not in self.data['crates']:
            self.data['crates'][crate] = {}
        if 'releases' not in self.data['crates'][crate]:
            self.data['crates'][crate]['releases'] = {}
        if version not in self.data['crates'][crate]['releases']:
            self.data['crates'][crate]['releases'][version] = {}

        rel_data = self.data['crates'][crate]['releases'][version]
        if 'diagnosis' not in rel_data:
            rel_data['diagnosis'] = {}

        diag_data = {'changes': []}
        if from_version:
            rel_data['diagnosis'].setdefault('from_version', from_version)
        rel_data['diagnosis'][analyzer] = diag_data
        self.save()

    def add_llm_usage(
        self,
        crate: str,
        version: str,
        analyzer: str,
        spec_chars: int,
        system_chars: int,
        cost: float | None,
    ) -> tuple[int, int, float | None]:
        """
        Accumulate LLM usage statistics for a diagnosis.
        """
        diag = (
            self.data.get('crates', {})
            .get(crate, {})
            .get('releases', {})
            .get(version, {})
            .get('diagnosis', {})
            .get(analyzer)
        )
        if not diag:
            return 0, 0, None

        diag['llm_spec_chars'] = diag.get('llm_spec_chars', 0) + spec_chars
        diag['llm_system_chars'] = diag.get('llm_system_chars', 0) + system_chars
        diag['llm_chars'] = (
            diag.get('llm_spec_chars', 0) + diag.get('llm_system_chars', 0)
        )
        if cost is not None:
            diag['llm_cost'] = diag.get('llm_cost', 0.0) + cost
        self.save()
        return (
            diag.get('llm_spec_chars', 0),
            diag.get('llm_system_chars', 0),
            diag.get('llm_cost'),
        )

    def emit_change(self, crate: str, version: str, analyzer: str, change: ChangeInfo):
        """
        Record a detected change.
        """
        print(f"            {change.severity.value} ({change.line}, {change.col}): {change.description}")

        # Ensure all required parent keys exist before storing anything new.
        # Up to release must already exist as it was created during fetching.
        release_data = self.data['crates'][crate]['releases'][version]
        diagnosis = release_data.setdefault('diagnosis', {})
        analyzer_data = diagnosis.setdefault(analyzer, {'changes': []})
        changes = analyzer_data['changes']
        change_dict = {
            'severity': change.severity.value,
            'line': change.line,
            'col': change.col,
            'description': change.description
        }
        if change.filename:
            change_dict['filename'] = change.filename
        if change.old_filename:
            change_dict['old_filename'] = change.old_filename
        changes.append(change_dict)

    def finish_diagnosis(
        self, crate: str, prev_version: str, curr_version: str, analyzer: str
    ) -> None:
        """
        Computes compliance based on stored changes and version bump.
        """
        try:
            v1 = semver.Version.parse(prev_version)
            v2 = semver.Version.parse(curr_version)
        except ValueError:
            print(f"Non-semver version found: {prev_version} -> {curr_version}")
            raise

        diag = self.data['crates'][crate]['releases'][curr_version]['diagnosis'][analyzer]
        major_changes = [c for c in diag['changes'] if c['severity'] == "MAJOR"]
        minor_changes = [c for c in diag['changes'] if c['severity'] == "minor"]

        bump_type = _detect_version_bump(v1, v2)
        compliance, reason = _calculate_compliance(
            bump_type, major_changes, minor_changes, analyzer
        )

        diag['compliant'] = compliance.value
        if compliance == Compliance.NO:
            diag['noncompliance'] = reason
            print(f"      [{analyzer}: NON-COMPLIANT] {reason}")
        elif compliance == Compliance.LAX:
            diag['noncompliance'] = reason
            print(f"      [{analyzer}: COMPLIANT (lax)] {reason}")
        else:  # strict
            if 'noncompliance' in diag:
                del diag['noncompliance']
            print(f"      [{analyzer}: COMPLIANT (strict)]")

        self.save()

    def finish_diagnosis_with_error(
        self, crate: str, curr_version: str, analyzer: str, error_message: str
    ) -> None:
        """
        Keep error status but remove any partial changes.
        """
        diag = self.data['crates'][crate]['releases'][curr_version] \
                        ['diagnosis'][analyzer]
        if 'changes' in diag:
            del diag['changes']
        diag['compliant'] = Compliance.ERROR.value
        diag['error_message'] = error_message
        print(f"      [{analyzer}: ERROR] {error_message}")
        self.save()

    def save(self):
        """Save context to YAML file, with backup on failure."""
        old_filename = self.filename + ".old"
        if os.path.exists(self.filename):
            os.rename(self.filename, old_filename)

        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.data, f)
        except Exception as e:
            if os.path.exists(old_filename):
                os.rename(old_filename, self.filename)  # Restore the old file
            raise e


def _detect_version_bump(v1: semver.Version, v2: semver.Version) -> BumpType:
    """
    Detect the type of version bump between two versions.
    Returns a BumpType enum value.
    """
    is_major_bump = v2.major > v1.major
    is_minor_bump = v2.minor > v1.minor and v2.major == v1.major
    is_patch_bump = v2.patch > v1.patch and v2.major == v1.major and v2.minor == v1.minor

    result = BumpType.NONE

    if v1.major == 0:
        # 0.x.y semantic versioning:
        # - minor bump acts as MAJOR bump (breaking changes)
        # - patch bump acts as minor bump (backwards compatible additions)
        if is_minor_bump or is_major_bump:
            result = BumpType.MAJOR
        elif is_patch_bump:
            result = BumpType.MINOR
    else:
        if is_major_bump:
            result = BumpType.MAJOR
        elif is_minor_bump:
            result = BumpType.MINOR
        elif is_patch_bump:
            result = BumpType.PATCH

    return result


def _calculate_compliance(
    bump_type: BumpType,
    major_changes: list,
    minor_changes: list,
    analyzer: str
) -> tuple[Compliance, str]:
    """
    Calculate compliance status based on version bump type and detected changes.
    Returns (compliance, reason).
    """
    compliance = Compliance.STRICT
    reason = ""

    if bump_type == BumpType.MAJOR:
        if not major_changes and analyzer != 'files':
            compliance = Compliance.LAX
            reason = "Major version bump but no MAJOR changes found."
    elif bump_type == BumpType.MINOR:
        if major_changes:
            compliance = Compliance.NO
            reason = "Minor version bump but MAJOR changes found."
        elif not minor_changes and analyzer != 'files':
            compliance = Compliance.LAX
            reason = "Minor version bump but no minor changes found."
    elif bump_type == BumpType.PATCH:
        if major_changes or minor_changes:
            compliance = Compliance.NO
            reason = "Patch version bump but API changes found."

    return compliance, reason
