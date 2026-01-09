"""
This module handles the querying of LLMs through the OpenRouter API.
"""

import os
import sys
import json
import time
import requests
from dataclasses import dataclass
from lasv import prompts
from lasv import colors


@dataclass(frozen=True)
class LlmUsage:
    """LLM usage details for a single request."""
    spec_chars: int
    system_chars: int
    cost: float | None


def query_model(
    model: str, spec1_content: str, spec2_content: str
) -> tuple[str, LlmUsage]:
    """
    Query an LLM model through the OpenRouter API to compare two specs.
    Implements exponential backoff retry for 4xx and 5xx errors.
    Returns the response content and usage details.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")

    prompt = prompts.INSTRUCTIONS["detailed"]
    user_content = f"OLD:\n{spec1_content}\n\nNEW:\n{spec2_content}"
    sent_system_chars = len(prompt)
    sent_spec_chars = len(spec1_content) + len(spec2_content)

    # Retry configuration
    max_retries = 6  # Will give us: 1s, 2s, 4s, 8s, 16s, 32s, 60s (capped)
    retry_count = 0
    base_delay = 1  # Start with 1 second
    max_delay = 60  # Maximum 1 minute backoff

    while retry_count <= max_retries:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content}
                    ]
                }),
                timeout=30
            )

            # Check status code first, before parsing response
            if response.status_code != 200:
                # Trigger HTTPError to reuse backoff logic
                response.raise_for_status()

            result = response.json()
            if "choices" in result and result["choices"]:
                usage = result.get("usage", {}) if isinstance(result, dict) else {}
                total_cost = None
                if isinstance(usage, dict):
                    if "total_cost" in usage:
                        total_cost = usage.get("total_cost")
                    elif "cost" in usage:
                        total_cost = usage.get("cost")
                return (
                    result["choices"][0]["message"]["content"],
                    LlmUsage(
                        spec_chars=sent_spec_chars,
                        system_chars=sent_system_chars,
                        cost=total_cost,
                    ),
                )

            # Got a response but without expected structure - extract error code if available
            error_code = result.get("error", {}).get("code") if isinstance(result.get("error"), dict) else None

            print(colors.yellow(f"Error: Unexpected response from OpenRouter API: {result}"))

            # Raise RequestException to trigger backoff (caught by RequestException handler)
            # Include error code in message if available
            error_msg = f"Unexpected API response structure (error code: {error_code})" if error_code else "Unexpected API response structure"
            raise requests.exceptions.RequestException(error_msg)

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            # Treat HTTP errors as retryable, including when status is missing.
            if retry_count < max_retries and (status_code is None or 400 <= status_code < 600):
                delay = min(base_delay * (2 ** retry_count), max_delay)
                retry_count += 1
                if status_code is None:
                    status_text = "HTTP error"
                else:
                    status_text = f"HTTP {status_code} error"
                print(colors.red(f"{status_text} from OpenRouter API: {e}"))
                print(colors.yellow(f"{status_text} from OpenRouter API. "
                      f"Retrying in {delay} seconds... (attempt {retry_count}/{max_retries})"))
                time.sleep(delay)
                continue

            if status_code is None:
                print(colors.red(f"Error: Maximum retries reached after HTTP error: {e}"))
            else:
                print(colors.red(
                    f"Error: Maximum retries reached after HTTP {status_code} error: {e}"
                ))
            sys.exit(1)

        except requests.exceptions.RequestException as e:
            # Network errors, timeouts, etc. - also retry these
            if retry_count < max_retries:
                delay = min(base_delay * (2 ** retry_count), max_delay)
                retry_count += 1
                print(colors.yellow(f"Network error: {e}. "
                      f"Retrying in {delay} seconds... (attempt {retry_count}/{max_retries})"))
                time.sleep(delay)
                continue
            else:
                print(colors.red(f"Error: Maximum retries reached after network error: {e}"))
                sys.exit(1)

        except json.JSONDecodeError:
            print(colors.red(f"Error decoding JSON response from OpenRouter API: {response.text}"))
            sys.exit(1)

    # Should not reach here, but just in case
    print(colors.red("Error: Unexpected exit from retry loop"))
    sys.exit(1)
