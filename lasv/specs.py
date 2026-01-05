"""
This module is responsible for comparing the content of two Ada package specifications.
"""
import re
from lasv_main import LasvContext, ChangeType
from lasv import llm


def _get_public_spec(path: str) -> str:
    """
    Return the public part of a spec file.
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    uncommented_lines = [re.sub(r"--.*", "", line) for line in lines]

    private_line_index = -1
    for i, line in enumerate(uncommented_lines):
        if re.search(r"\bprivate\b", line, re.IGNORECASE):
            private_line_index = i
            break

    if private_line_index != -1:
        # Find the column index of "private" in the uncommented line
        private_match_in_uncommented = re.search(r"\bprivate\b", uncommented_lines[private_line_index], re.IGNORECASE)
        col_index = private_match_in_uncommented.start()

        # Reconstruct the content up to the "private" keyword
        result = ""
        for i in range(private_line_index):
            result += lines[i]
        result += lines[private_line_index][:col_index]
        return result

    return "".join(lines)


def compare_spec_content(
    context: LasvContext, crate: str, version: str, path1: str, path2: str, model: str
) -> None:
    """
    Compare the content of two existing specification files using an LLM.

    :param context: The application context for emitting changes.
    :param path1: Absolute path to the old specification file.
    :param path2: Absolute path to the new specification file.
    :return: None
    """
    if not model:
        return

    spec1_public = _get_public_spec(path1)
    spec2_public = _get_public_spec(path2)

    if spec1_public == spec2_public:
        return

    response = llm.query_model(model, spec1_public, spec2_public)

    for line in response.splitlines():
        match = re.match(r"(MAJOR|minor) \((\d+), (\d+)\): (.*)", line)
        if match:
            severity_str, line_num, col_num, description = match.groups()
            severity = (
                ChangeType.MAJOR
                if severity_str == "MAJOR"
                else ChangeType.MINOR
            )
            context.emit_change(
                crate,
                version,
                model,
                severity,
                int(line_num),
                int(col_num),
                description,
            )
