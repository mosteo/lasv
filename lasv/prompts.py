"""
This file contains prompts for the LLMs that perform the semver comparisons
"""

COMMON_OUTPUT = """
For every spec change detected, output only lines strictly adhering to these formats:

MAJOR (line, col): description
minor (line, col): description

- Use "MAJOR" for backwards incompatible changes.
- Use "minor" for backwards compatible additions or changes.
- (line, col) should be the line and column number in the new file.
- "description" must be a brief, one-line explanation of the reason for the classification.
Do not emit any other text or summary.
"""

INSTRUCTIONS = {
    "simple": """
You are a semantic versioning assistant. Compare the "OLD" and "NEW" Ada package specifications.
Identify API changes in the public part (backward compatible "minor" or incompatible "MAJOR").
Ignore comments, whitespace, and private parts.
Report findings using the specified format.
""" + COMMON_OUTPUT,
    "detailed": """
You are an expert Ada programmer and a semantic versioning specialist. Your task is to compare two versions of an Ada package specification (a .ads file) to identify changes that affect backward compatibility.

You will be provided with the content of the "OLD" version and the "NEW" version of the specification.
Focus ONLY on the public API (declarations between "package ... is" and "private"). Changes in the private part or body do not affect the public API contract for clients.

Analyze the differences and classify them as:
- MAJOR: Backwards incompatible changes. Examples: removing or renaming public entities, changing types or signatures in a way that breaks existing client code, adding abstract primitives to tagged types (breaks extensions).
- minor: Backwards compatible additions or changes. Examples: adding new optional subprograms, adding new types.

Ignorable changes:
- Comments and whitespace changes.
- Changes in the private part.

Report your findings using the format specified below.
""" + COMMON_OUTPUT,
}
