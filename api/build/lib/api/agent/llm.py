from dotenv import load_dotenv
from google import genai
from google.genai import types
import inspect
import os
import sys
import logging
import json
from .extract_json import extract_json

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print(
        f"🔴 Error: GEMINI_API_KEY is not set in the environment variables",
        file=sys.stderr
    )
    # Exit the application with a non-zero status code to indicate an error
    sys.exit(1)


class LLM:
    def __init__(self):
        self.client = genai.Client(
            api_key=GEMINI_API_KEY
        )

    async def run(self, prompt: str, max_calls: int = 2, tools: list = [], jsonResults=False):
        messages = [
            {
                'role': 'user',
                'parts': [{
                    'text': prompt
                }]
            }
        ]

        for i in range(max_calls):
            logger.info(f"--- Agent Loop Iteration: {i + 1} ---")

            agentConfig = types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            )

            if len(tools):
                agentConfig.tools = tools

            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=messages,
                config=agentConfig
            )

            if not response.candidates:
                raise Exception("No response from LLM")

            candidate = response.candidates[0]

            if candidate.content.parts and candidate.content.parts[0].function_call:
                function_call = candidate.content.parts[0].function_call
                tool_name = function_call.name
                tool_args = dict(function_call.args)

                logger.info(
                    f"Executing tool: '{tool_name}' with arguments: {json.dumps(tool_args)}")

                func_to_run = next(
                    (f for f in tools if f.__name__ == tool_name), None)

                func_results = None

                if inspect.iscoroutinefunction(func_to_run):
                    func_results = await func_to_run(*tool_args)
                else:
                    func_results = func_to_run(*tool_args)

                print(func_results)

                messages.append(
                    {
                        'role': 'tool',
                        'parts': [{
                            'function_response': {
                                'name': tool_name,
                                'response': {
                                    'content': func_results
                                },
                            }
                        }]
                    }
                )

                continue

            if candidate.content.parts and candidate.content.parts[0].text:
                if jsonResults:
                    return extract_json(candidate.content.parts[0].text)

                return candidate.content.parts[0].text

        return response.text
