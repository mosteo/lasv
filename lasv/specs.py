"""
This module is responsible for comparing the content of two Ada package specifications.
"""
from lasv_main import LasvContext


def compare_spec_content(context: LasvContext, path1: str, path2: str) -> None:
    """
    Compare the content of two existing specification files using an LLM.

    :param context: The application context for emitting changes.
    :param path1: Absolute path to the old specification file.
    :param path2: Absolute path to the new specification file.
    :return: None
    """
