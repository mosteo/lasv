#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This program without arguments list all alr crates and,
for each one, obtains its releases, if there are at least two of them.
Then, for each pair of consecutive releases, it queries a LLM to print
all interface changes, classifying them as minor- or major-number changes.

Intermediate (and final) results are cached in a "lasv.yaml" file.

Data is outputted to a YAML file for further processing.

Input arguments: optional crate name to process only that crate.
"""


import os
import sys
import yaml

from lasv import crates


class LasvContext:
    """Encapsulates lasv context data with load/save functionality."""

    def __init__(self, filename="lasv.yaml"):
        self.filename = filename
        self.data = {}

    def load(self):
        """Load context from YAML file."""
        if os.path.exists(self.filename):
            with open(self.filename, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                self.data = loaded if loaded else {}
        return self.data

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


def lasv_main():
    """
    Load context if it exists. Obtain from it the 'crates' list.
    If a crate name is given as argument, process only that crate.
    """
    context = LasvContext()
    data = context.load()

    target_crate = sys.argv[1] if len(sys.argv) > 1 else None

    if target_crate:
        print(f"Processing only crate: {target_crate}")
    else:
        print("Processing all crates.")

    crates.list(context)


# Program entry point
if __name__ == "__main__":
    lasv_main()