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
        content = f.read()
    private_match = re.search(r"\bprivate\b", content, re.IGNORECASE)
    if private_match:
        return content[:private_match.start()]
    return content


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
