from dotenv import load_dotenv
from google import genai
from google.genai import types
import inspect
import os
import sys
import logging
import json
import asyncio
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

    async def run(self, prompt: str, max_calls: int = 20, tools: list = [], jsonResults=False, delay_ms: int = 0):
        """
        Runs the LLM agent loop.

        Args:
            prompt (str): The initial user prompt.
            max_calls (int): The maximum number of LLM calls in the loop.
            tools (list): A list of functions (tools) available to the LLM.
            jsonResults (bool): Whether to extract JSON from the final text response.
            delay_ms (int): The delay in milliseconds to wait *between* LLM calls (default: 0).

        Returns:
            tuple: A tuple containing (result, metadata).
                - result (str or dict): The final text or extracted JSON.
                - metadata (dict): A dictionary containing 'final_response_object',
                                    'message_history', 'iterations', and
                                    'intermediate_steps'.
        """
        messages = [
            {
                'role': 'user',
                'parts': [{
                    'text': prompt
                }]
            }
        ]

        intermediate_steps = []
        response = None
        final_result = None
        i = 0  # To track the loop index

        for i in range(max_calls):
            # Wait only if it's not the first iteration (i > 0) and a delay is set
            if i > 0 and delay_ms > 0:
                logger.info(
                    f"Waiting for {delay_ms}ms before next LLM call...")
                # Convert milliseconds to seconds for asyncio.sleep
                await asyncio.sleep(delay_ms / 1000.0)

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
                logger.warning(
                    f"Iteration {i + 1}: No candidates in response. Returning empty string."
                )
                final_result = ""
                break  # Exit the loop

            candidate = response.candidates[0]

            # --- MODIFICATION START: Support for Multi-Tool Calling ---

            # 1. Collect *all* function call parts, not just the first one.
            func_call_parts = []  # Changed from 'func_call_part = None'
            if candidate.content.parts:
                for part in candidate.content.parts:
                    if part.function_call:
                        func_call_parts.append(part)  # Append instead of break

            # 2. Check if the *list* of calls is not empty.
            if func_call_parts:
                logger.info(
                    f"LLM requested {len(func_call_parts)} tool(s) in this turn.")

                # 3. This list will hold the results to send back to the LLM.
                tool_result_parts_for_history = []

                # 4. Loop through each requested function call and execute it.
                #    This is your "running python code logic"
                for func_call_part in func_call_parts:
                    function_call = func_call_part.function_call
                    tool_name = function_call.name
                    tool_args = dict(function_call.args)

                    logger.info(
                        f"Executing tool: '{tool_name}' with arguments: {json.dumps(tool_args)}")

                    # Find the tool in our available list
                    func_to_run = next(
                        (f for f in tools if f.__name__ == tool_name), None)

                    func_results = None

                    if func_to_run:
                        # Tool *was* found, try to execute it
                        try:
                            if inspect.iscoroutinefunction(func_to_run):
                                # Note: This runs tools sequentially.
                                # For parallel execution, you'd use asyncio.gather here.
                                func_results = await func_to_run(**tool_args)
                            else:
                                func_results = func_to_run(**tool_args)

                            # Your original print statement
                            print(func_results)

                        except Exception as e:
                            # Handle errors *during* tool execution (e.g., bad args, network error)
                            logger.error(
                                f"Error executing tool '{tool_name}': {e}")
                            func_results = f"Error: Failed to execute tool '{tool_name}'. Reason: {e}"

                    else:
                        # Tool *was NOT* found
                        logger.warning(
                            f"Tool '{tool_name}' not found in the provided tools list.")
                        func_results = f"Error: Tool '{tool_name}' does not exist. Please choose from the available tools."

                    if func_results is None:
                        logger.warning(
                            f"Tool '{tool_name}' returned None. Coercing to empty string.")
                        func_results = ""

                    # Store the (action, observation) tuple for the agent's metadata
                    intermediate_steps.append((func_call_part, func_results))

                    # 5. Add the individual tool's result to our list for the history.
                    tool_result_parts_for_history.append({
                        'function_response': {
                            'name': tool_name,
                            'response': {
                                'content': func_results
                            },
                        }
                    })

                # 6. After executing *all* tools, append *one* 'tool' message
                #    to the history, containing the list of all results.
                messages.append(
                    {
                        'role': 'tool',
                        'parts': tool_result_parts_for_history  # Pass the list of results
                    }
                )

                continue  # Continue to the next loop iteration

            # --- MODIFICATION END ---

            # --- No tool call, this is the final answer ---
            final_text = response.text

            if final_text:
                if jsonResults:
                    final_result = extract_json(final_text)
                else:
                    final_result = final_text
            else:
                logger.warning(
                    f"Iteration {i + 1}: No function call and no text content. Returning empty string."
                )
                final_result = ""

            break  # Got a final answer, exit the loop

        # --- End of loop ---

        metadata = {
            "final_response_object": response,
            "message_history": messages,
            "iterations": i + 1 if response else i,
            "intermediate_steps": intermediate_steps
        }

        if final_result is None:
            logger.warning(
                "LLM.run loop finished without a final text result. Defaulting to empty string.")
            final_result = ""

        return final_result, metadata
