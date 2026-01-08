"""
This module provides color formatting functions for console output.
"""
from colorama import Fore, Style


def red(text: str) -> str:
    """
    Format text in red (for fatal errors that abort execution).

    Args:
        text: The text to colorize

    Returns:
        The text wrapped in red color codes
    """
    return f"{Fore.RED}{text}{Style.RESET_ALL}"


def yellow(text: str) -> str:
    """
    Format text in yellow (for warnings and retryable errors).

    Args:
        text: The text to colorize

    Returns:
        The text wrapped in yellow color codes
    """
    return f"{Fore.YELLOW}{text}{Style.RESET_ALL}"


def crate(text: str) -> str:
    """
    Format text as a crate name (bold light cyan/blue).

    Args:
        text: The crate name to colorize

    Returns:
        The text wrapped in bold light cyan color codes
    """
    return f"{Style.BRIGHT}{Fore.LIGHTCYAN_EX}{text}{Style.RESET_ALL}"


def version(text: str) -> str:
    """
    Format text as a version number (green).

    Args:
        text: The version to colorize

    Returns:
        The text wrapped in green color codes
    """
    return f"{Fore.GREEN}{text}{Style.RESET_ALL}"
