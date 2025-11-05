import asyncio
import jinja2
import os
import logging
from typing import AsyncGenerator, List, Dict, Any

from ..llm.llm import LLM
from .tools.sql_explorer_tool import sql_explorer_tool
from .tools.answer_sql_query_tool import answer_sql_query_tool
from .tools.url_fetch_tool import url_fetch_tool

logger = logging.getLogger(__name__)


class Agent:
    llm = LLM()

    def __init__(self):
        template_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(searchpath=template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        self.prompt_template = self.template_env.get_template(
            "./prompts/main.jinja2")

        self.data_sources_text = self._load_data_sources_as_text(template_dir)

    def _load_data_sources_as_text(self, base_path: str) -> str:
        """Loads the raw text content from data_sources.yaml."""
        data_sources_path = os.path.join(base_path, 'data_sources.yaml')
        try:
            with open(data_sources_path, 'r') as f:
                print("Successfully loaded data_sources.yaml as text.")
                return f.read()  # <-- Reads the entire file into a string
        except FileNotFoundError:
            print(f"Warning: 'data_sources.yaml' not found in {base_path}")
        except Exception as e:
            print(f"Error loading 'data_sources.yaml': {e}")
        return ""  # <-- Return an empty string on failure

    # Added 'global_context' parameter
    def _build_prompt_from_template(self, new_user_text: str, history: List[Dict[str, str]], global_context: str) -> str:
        return self.prompt_template.render(
            data_sources=self.data_sources_text,
            history=history,
            new_user_text=new_user_text,
            global_context=global_context  # <-- Pass it to the template
        )

    # Added 'global_context' parameter
    async def stream_response(
        self,
        user_text: str,
        thread_id: str,
        user_id: str,
        history: List[Dict[str, str]],
        global_context: str  # <-- Accept it here
    ) -> AsyncGenerator[Dict[str, Any], None]:
        print(
            f"Agent received request for thread '{thread_id}' from user '{user_id}'.")

        if "delete" in user_text.lower() and "thread" not in user_text.lower():
            yield {
                "role": "model",
                "type": "confirmation",
                "content": {
                    "title": "Confirm Action",
                    "message": "You mentioned deleting something. Are you sure you want to proceed?",
                    "confirmText": "Yes, I'm sure",
                    "cancelText": "No, cancel"
                }
            }
            return

        # Pass 'global_context' when building the prompt
        full_prompt = self._build_prompt_from_template(
            user_text, history, global_context)

        llm_response_stream = self.run(
            prompt=full_prompt, thread_id=thread_id, user_id=user_id)

        async for chunk in llm_response_stream:
            yield {
                "role": "model",
                "type": "text",
                "content": chunk
            }

    async def run(self, prompt: str, thread_id: str, user_id: str) -> AsyncGenerator[str, None]:
        """Wrapper for the LLM call that simulates streaming."""
        print(f"\n--- LLM Prompt ---\n{prompt}\n--------------------\n")

        print(prompt)
        # Unpack the response and metadata from the LLM run
        response_text, metadata = await self.llm.run(
            prompt=prompt,
            delay_ms=1000 * 10,
            thread_id=thread_id,
            user_id=user_id,
            tools=[
                sql_explorer_tool,
                answer_sql_query_tool,
                url_fetch_tool
            ]
        )

        # Optional: Log metadata
        logger.info(
            f"LLM run completed in {metadata.get('iterations', 'N/A')} iterations.")
        if metadata.get("final_response_object") and metadata["final_response_object"].usage_metadata:
            logger.info(
                f"Token usage: {metadata['final_response_object'].usage_metadata}")

        if not response_text:
            logger.warning(
                "LLM returned an empty final response. Checking for last tool output...")

            last_tool_output = None

            intermediate_steps_key = 'intermediate_steps'

            try:
                if (metadata and
                    isinstance(metadata, dict) and
                        intermediate_steps_key in metadata):

                    intermediate_steps = metadata.get(intermediate_steps_key)

                    if intermediate_steps and isinstance(intermediate_steps, list) and len(intermediate_steps) > 0:
                        # Get the last step
                        last_step = intermediate_steps[-1]

                        # We want the tool's output, which is the 2nd element
                        if isinstance(last_step, tuple) and len(last_step) > 1:
                            last_tool_output = last_step[1]
            except Exception as e:
                logger.error(
                    f"Error while trying to extract last tool output from metadata: {e}")
                # Don't fail, just proceed to the fallback

            # Now, check if we found a valid text output
            if last_tool_output and isinstance(last_tool_output, str):
                logger.info(
                    "Using last tool output as the final response.")
                yield last_tool_output
            else:
                # Fallback to the generic error if no valid tool output was found
                logger.warning(
                    "LLM returned empty, and no valid last tool output was found in metadata.")
                yield "I'm sorry, but an unexpected error occurred while processing your request. Please try again."

            return  # Stop execution here

        yield response_text
