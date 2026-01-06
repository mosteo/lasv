"""
This module handles the querying of LLMs through the OpenRouter API.
"""

import os
import sys
import json
import requests
from lasv import prompts


def query_model(model: str, spec1_content: str, spec2_content: str) -> str:
    """
    Query an LLM model through the OpenRouter API to compare two specs.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")

    prompt = prompts.INSTRUCTIONS["detailed"]
    user_content = f"OLD:\n{spec1_content}\n\nNEW:\n{spec2_content}"

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

        response.raise_for_status()

        result = response.json()
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"]

        print(f"Error: Unexpected response from OpenRouter API: {result}")
        sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to OpenRouter API: {e}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from OpenRouter API: {response.text}")
        sys.exit(1)
