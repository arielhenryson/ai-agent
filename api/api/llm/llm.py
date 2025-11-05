from dotenv import load_dotenv
from google import genai
from google.genai import types
import inspect
import os
import sys
import logging
import json
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from .extract_json import extract_json
from ..db.mongo import db_manager
from .token_manager import token_manager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LLM:
    async def run(self, prompt: str, max_calls: int = 20, tools: list = [], jsonResults=False, delay_ms: int = 0, thread_id: str = None, user_id: str = None):
        """
        Runs the LLM agent loop.
        ... (args description) ...
        """

        logger.info("Attempting to retrieve API key via TokenManager...")
        try:
            # Get the token (from cache or new request)
            current_api_key = token_manager.get_token()
            logger.info("Successfully retrieved API key.")
        except Exception as e:
            logger.error(f"Failed to get API key: {e}. Aborting run.")
            # Return a user-facing error and empty metadata
            return "Error: Could not authenticate with LLM service.", {}

        # Initialize the client *inside* the run method with the retrieved key
        client = genai.Client(api_key=current_api_key)

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
        i = 0

        for i in range(max_calls):
            if i > 0 and delay_ms > 0:
                logger.info(
                    f"Waiting for {delay_ms}ms before next LLM call...")
                await asyncio.sleep(delay_ms / 1000.0)

            logger.info(f"--- Agent Loop Iteration: {i + 1} ---")

            agentConfig = types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            )

            if len(tools):
                agentConfig.tools = tools

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=messages,
                config=agentConfig
            )

            if not response.candidates:
                logger.warning(
                    f"Iteration {i + 1}: No candidates in response. Returning empty string."
                )
                final_result = ""
                break

            candidate = response.candidates[0]

            func_call_parts = []
            if candidate.content.parts:
                for part in candidate.content.parts:
                    if part.function_call:
                        func_call_parts.append(part)

            if func_call_parts:
                logger.info(
                    f"LLM requested {len(func_call_parts)} tool(s) in this turn.")

                tool_result_parts_for_history = []

                for func_call_part in func_call_parts:
                    function_call = func_call_part.function_call
                    tool_name = function_call.name
                    tool_args = dict(function_call.args)

                    logger.info(
                        f"Executing tool: '{tool_name}' with arguments: {json.dumps(tool_args)}")

                    # --- Log tool call to DB ---
                    if thread_id and user_id:
                        tool_call_message_id = ObjectId()
                        tool_call_message = {
                            "_id": tool_call_message_id,
                            "role": "tool",
                            "user_id": user_id,
                            "type": "tool_call",
                            "content": {
                                "name": tool_name,
                                "arguments": tool_args
                            },
                            "timestamp": datetime.now(timezone.utc)
                        }
                        try:
                            await db_manager.create_message(thread_id, tool_call_message)
                            logger.info(
                                f"Logged tool *call* to thread {thread_id}")
                        except Exception as e:
                            logger.error(
                                f"Failed to log tool call to thread {thread_id}: {e}")

                    # ... (Tool finding/execution logic) ...
                    func_to_run = next(
                        (f for f in tools if f.__name__ == tool_name), None)

                    func_results = None

                    if func_to_run:
                        try:
                            sig = inspect.signature(func_to_run)
                            if '__thread_id' in sig.parameters:
                                tool_args['__thread_id'] = thread_id
                                logger.info(
                                    f"Injecting __thread_id='{thread_id}' into '{tool_name}'")
                        except ValueError:
                            logger.debug(
                                f"Could not inspect signature for tool '{tool_name}'.")

                        try:
                            if inspect.iscoroutinefunction(func_to_run):
                                func_results = await func_to_run(**tool_args)
                            else:
                                func_results = func_to_run(**tool_args)
                            print(func_results)
                        except Exception as e:
                            logger.error(
                                f"Error executing tool '{tool_name}': {e}")
                            func_results = f"Error: Failed to execute tool '{tool_name}'. Reason: {e}"
                    else:
                        logger.warning(
                            f"Tool '{tool_name}' not found in the provided tools list.")
                        func_results = f"Error: Tool '{tool_name}' does not exist. Please choose from the available tools."

                    if func_results is None:
                        logger.warning(
                            f"Tool '{tool_name}' returned None. Coercing to empty string.")
                        func_results = ""

                    # --- Log tool response to DB ---
                    if thread_id and user_id:
                        tool_response_message_id = ObjectId()
                        tool_response_message = {
                            "_id": tool_response_message_id,
                            "role": "tool",
                            "user_id": user_id,
                            "type": "tool_response",
                            "content": {
                                "name": tool_name,
                                "response": func_results
                            },
                            "timestamp": datetime.now(timezone.utc)
                        }
                        try:
                            await db_manager.create_message(thread_id, tool_response_message)
                            logger.info(
                                f"Logged tool *response* to thread {thread_id}")
                        except Exception as e:
                            logger.error(
                                f"Failed to log tool response to thread {thread_id}: {e}")

                    intermediate_steps.append((func_call_part, func_results))

                    tool_result_parts_for_history.append({
                        'function_response': {
                            'name': tool_name,
                            'response': {
                                'content': func_results
                            },
                        }
                    })

                messages.append(
                    {
                        'role': 'tool',
                        'parts': tool_result_parts_for_history
                    }
                )
                continue

            # --- No tool call, this is the final answer ---
            final_text = response.text

            if final_text:
                if jsonResults:
                    final_result = extract_json(final_text)
                else:
                    final_result = final_text

                # Log the final model response to the database
                if thread_id:  # We have a thread to save to
                    model_message_id = ObjectId()
                    model_message = {
                        "_id": model_message_id,
                        "role": "model",
                        "user_id": "LLM_Assistant",  # Use a consistent ID for the bot
                        "type": "text",
                        "content": final_result,
                        "timestamp": datetime.now(timezone.utc)
                    }
                    try:
                        await db_manager.create_message(thread_id, model_message)
                        logger.info(
                            f"Logged final *model response* to thread {thread_id}")
                    except Exception as e:
                        logger.error(
                            f"Failed to log final model response to thread {thread_id}: {e}")

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
