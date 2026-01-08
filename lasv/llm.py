"""
This module handles the querying of LLMs through the OpenRouter API.
"""

import os
import sys
import json
import time
import requests
from lasv import prompts
from lasv import colors


def query_model(model: str, spec1_content: str, spec2_content: str) -> str:
    """
    Query an LLM model through the OpenRouter API to compare two specs.
    Implements exponential backoff retry for 4xx and 5xx errors.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")

    prompt = prompts.INSTRUCTIONS["detailed"]
    user_content = f"OLD:\n{spec1_content}\n\nNEW:\n{spec2_content}"

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
                return result["choices"][0]["message"]["content"]

            # Got a response but without expected structure - extract error code if available
            error_code = result.get("error", {}).get("code") if isinstance(result.get("error"), dict) else None

            print(colors.yellow(f"Error: Unexpected response from OpenRouter API: {result}"))

            # Raise RequestException to trigger backoff (caught by RequestException handler)
            # Include error code in message if available
            error_msg = f"Unexpected API response structure (error code: {error_code})" if error_code else "Unexpected API response structure"
            raise requests.exceptions.RequestException(error_msg)

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            # Check if error is in 400 or 500 range
            if status_code and (400 <= status_code < 600):
                if retry_count < max_retries:
                    # Calculate exponential backoff delay
                    delay = min(base_delay * (2 ** retry_count), max_delay)
                    retry_count += 1
                    print(colors.yellow(f"HTTP {status_code} error from OpenRouter API. "
                          f"Retrying in {delay} seconds... (attempt {retry_count}/{max_retries})"))
                    time.sleep(delay)
                    continue
                else:
                    print(colors.red(f"Error: Maximum retries reached after HTTP {status_code} error: {e}"))
                    sys.exit(1)
            else:
                # Non-retryable error
                print(colors.red(f"Error connecting to OpenRouter API: {e}"))
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
