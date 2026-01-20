"""
This module is responsible for comparing the content of two Ada package specifications.
"""
import os
import re
from dataclasses import dataclass
from lasv.context import LasvContext, ChangeType, ChangeInfo
from lasv import llm
from lasv import colors

MAX_SPEC_BYTES = 64 * 1024


@dataclass
class SpecComparisonResult:
    """Result of comparing two spec files."""
    has_major: bool
    has_minor: bool
    sent_to_llm: bool


def _get_public_spec(path: str) -> str:
    """
    Return the public part of a spec file.
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    return '\n'.join(lines)

    uncommented_lines = [re.sub(r"--.*", "", line) for line in lines]

    private_line_index = -1
    for i, line in enumerate(uncommented_lines):
        if re.search(r"\bprivate\b", line, re.IGNORECASE):
            private_line_index = i
            break

    if private_line_index != -1:
        # Find the column index of "private" in the uncommented line
        private_match_in_uncommented = re.search(
            r"\bprivate\b", uncommented_lines[private_line_index], re.IGNORECASE
        )
        col_index = private_match_in_uncommented.start()

        # Reconstruct the content up to the "private" keyword
        result = ""
        for i in range(private_line_index):
            result += lines[i]
        result += lines[private_line_index][:col_index]
        return result

    return "".join(lines)


def compare_spec_content(
    context: LasvContext,
    crate: str,
    version: str,
    path1: str,
    path2: str,
    prompt_name: str = "detailed",
) -> SpecComparisonResult:
    """
    Compare the content of two existing specification files using an LLM.

    :param context: The application context for emitting changes.
    :param path1: Absolute path to the old specification file.
    :param path2: Absolute path to the new specification file.
    :param prompt_name: Name of the prompt to use for LLM comparison.
    :return: SpecComparisonResult with has_major, has_minor, sent_to_llm
    """
    if not context.model:
        return SpecComparisonResult(False, False, False)

    try:
        if os.path.getsize(path1) > MAX_SPEC_BYTES:
            print(colors.yellow(
                f"         Skipping large spec (>64k): {os.path.basename(path1)}"
            ))
            return SpecComparisonResult(False, False, False)
        if os.path.getsize(path2) > MAX_SPEC_BYTES:
            print(colors.yellow(
                f"         Skipping large spec (>64k): {os.path.basename(path2)}"
            ))
            return SpecComparisonResult(False, False, False)
    except OSError as e:
        print(colors.yellow(
            f"         Skipping spec due to size check error: {e}"
        ))
        return SpecComparisonResult(False, False, False)

    spec1_public = _get_public_spec(path1)
    spec2_public = _get_public_spec(path2)

    if spec1_public == spec2_public:
        # Include parent folder in the output
        parent_folder = os.path.basename(os.path.dirname(path2))
        filename = os.path.basename(path2)
        print(f"         Identical spec in {parent_folder}/{filename}")
        return SpecComparisonResult(False, False, False)

    response, usage = llm.query_model(
        context.model, spec1_public, spec2_public, prompt_name
    )
    base_model_name = context.model_key or context.model
    analyzer_name = f"{base_model_name}({prompt_name})"
    _total_spec_chars, _total_system_chars, total_cost = context.add_llm_usage(
        crate,
        version,
        analyzer_name,
        usage.spec_chars,
        usage.system_chars,
        usage.cost,
    )
    if usage.cost is None:
        cost_text = "instant cost: N/A"
    else:
        cost_text = f"instant cost: ${usage.cost:.5f}"
    if total_cost is None:
        total_cost_text = "accumulated cost: N/A"
    else:
        total_cost_text = f"accumulated cost: ${total_cost:.5f}"
    print(colors.lilac(f"         {cost_text}, {total_cost_text}"))

    first_change = True
    has_major = False
    has_minor = False
    for line in response.splitlines():
        match = re.match(r"(MAJOR|minor) \((\d+), (\d+)\): (.*)", line)
        if match:
            # Print filename before the first change
            if first_change:
                parent_folder = os.path.basename(os.path.dirname(path2))
                filename = os.path.basename(path2)
                print(f"         {parent_folder}/{filename}:")
                first_change = False

            severity_str, line_num, col_num, description = match.groups()
            severity = (
                ChangeType.MAJOR
                if severity_str == "MAJOR"
                else ChangeType.MINOR
            )
            if severity == ChangeType.MAJOR:
                has_major = True
            else:
                has_minor = True

            # Store the full path for the change info (both old and new)
            context.emit_change(
                crate,
                version,
                analyzer_name,
                ChangeInfo(
                    severity,
                    int(line_num),
                    int(col_num),
                    description,
                    path2,
                    path1,
                ),
            )

    if first_change:
        # Include parent folder in the output
        parent_folder = os.path.basename(os.path.dirname(path2))
        filename = os.path.basename(path2)
        print(f"         No semantic changes in {parent_folder}/{filename}")
        parent_folder = os.path.basename(os.path.dirname(path2))

    return SpecComparisonResult(has_major, has_minor, True)
