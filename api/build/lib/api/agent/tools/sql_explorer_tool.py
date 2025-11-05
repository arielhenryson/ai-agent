import logging
import json
from datetime import datetime, timezone  # --- VVV NEW IMPORTS VVV ---
from bson import ObjectId
from ...llm.llm import LLM
from .execute_sql_tool import execute_sql_tool
from ...db.mongo import db_manager

logger = logging.getLogger(__name__)

# Define cache duration in one place
CACHE_EXPIRATION_DAYS = 6


def _get_cache_key_from_config(config: dict) -> str:
    # ... (this function is unchanged) ...
    db_type = config.get('db_type')

    if db_type == 'sqlite':
        return config.get('db_path', 'sqlite_unknown')

    elif db_type in ('postgresql', 'oracle'):
        host = config.get('host', config.get('dsn', 'unknown_host'))
        port = config.get('port', 'default_port')
        user = config.get('user', 'unknown_user')
        db = config.get('dbname', 'unknown_db')

        return f"{db_type}|{user}@{host}:{port}/{db}"

    else:
        return json.dumps(config, sort_keys=True)


async def sql_explorer_tool(connection_config: dict, __thread_id: str, __user_id: str) -> str:
    """
    ... (docstring is unchanged) ...
    """

    # --- 1. CHECK CACHE FIRST ---
    cache_key = _get_cache_key_from_config(connection_config)
    db_type = connection_config.get('db_type', 'unknown')

    try:
        logger.info(f"Checking cache for SQL report: {cache_key}")
        cached_report = await db_manager.get_cached_sql_report(
            db_path=cache_key,
            max_age_days=CACHE_EXPIRATION_DAYS
        )

        if cached_report:
            logger.info(f"Returning cached SQL report for {cache_key}.")
            print(f"Returning cached SQL report for {cache_key}.")

            # --- VVV NEW LOGGING BLOCK VVV ---
            # Create a system message to inform the user about the cache hit
            try:
                cache_message_doc = {
                    "_id": ObjectId(),
                    "role": "system",  # Use a new 'system' role
                    "user_id": __user_id,
                    "type": "cache_hit",
                    "content": f"Using cached database report (valid for {CACHE_EXPIRATION_DAYS} days). No new exploration performed.",
                    "timestamp": datetime.now(timezone.utc)
                }
                await db_manager.create_message(__thread_id, cache_message_doc)
                logger.info(
                    f"Logged cache hit message to thread {__thread_id}")
            except Exception as e:
                # Don't fail the whole tool if just the logging fails
                logger.error(
                    f"Failed to log cache hit message to thread {__thread_id}: {e}")
            # --- ^^^ END OF NEW BLOCK ^^^ ---

            return cached_report

    except Exception as e:
        logger.warning(
            f"Cache check failed for {cache_key}: {e}. Will generate a new report.")

    # --- 2. IF NO CACHE, GENERATE NEW REPORT ---
    # ... (the rest of the file is unchanged) ...
    logger.info(f"No valid cache for {cache_key}. Generating new report...")
    print(
        f"No valid cache for {cache_key}. Generating new report for {db_type}...")

    llm = LLM()
    config_string = json.dumps(connection_config)

    prompt = f"""
        Your sole responsibility is to explore the structure of the {db_type.upper()} database.
        You MUST write all queries in the **{db_type.upper()}** SQL dialect.

        Use the `execute_sql_tool` as many times as you need to perform exploratory queries
        that help you better understand the data structure.

        You MUST pass this *exact* dictionary as the `connection_config` argument to the tool:
        {config_string}

        Follow this workflow step-by-step before writing the final report:

        1. **List Tables/Views**: Find all tables, views, and their types.
        2. **Inspect Schema**: For each table, get column names, data types, nullability, keys, and indexes.
        3. **Count Queries**: Count rows in important tables.
        4. **Distinct/Range Queries**: Get sample distinct values for categorical columns and MIN/MAX for numerical/date columns.
        5. **Analyze Relationships**: Use schema info (foreign keys) to map relationships.

        After completing the above steps, write a detailed report about the database structure. This report will be used later to run queries against the DB, so it should include insights that would assist that.

        The report should be organized in the following sections:

        1. **Database Overview**
        - Total number of tables and views.
        - General purpose or domain (inferred).

        2. **Table-by-Table Analysis**
        For each table:
        - Table name and description (inferred).
        - Number of rows.
        - List of ALL columns with:
            - Column name
            - Data type ({db_type.upper()} specific)
            - Nullability
            - Constraints (PRIMARY KEY, UNIQUE, FOREIGN KEY, etc.)
            - Indexes
        - DISTINCT values for categorical columns (and values meaning)
        - MIN/MAX for numerical columns
        - Description of the likely meaning of each column.
        - Example rows (if helpful).

        3. **Relationships & Keys**
        - Identify primary keys and foreign keys.
        - Describe relationships between tables.

        4. **Data Quality Observations** (Brief, if obvious)
        - Missing or inconsistent values.

        5. **Inferred Business Logic**
        - Guess the possible role of each table in the application/business context.

        Formatting:
        - Use clear headings and subheadings.
        - Use bullet points or tables for clarity.
        - Include both the factual schema details and your inferred interpretations.

        Important:
        - Do not fabricate details.
        - Always clearly separate observed facts from inferred guesses.
        - Provide ONLY the final report as your response.
        """

    print(f"Running LLM to explore {db_type} database...")

    result_text, metadata = await llm.run(
        prompt=prompt,
        thread_id=__thread_id,
        user_id=__user_id,
        max_calls=100,
        delay_ms=1000 * 10,
        tools=[
            execute_sql_tool
        ]
    )

    # --- 3. CACHE THE NEW RESULT ---
    if result_text:
        try:
            logger.info(f"Caching new report for {cache_key}.")
            await db_manager.cache_sql_report(
                db_path=cache_key,
                report_content=result_text
            )
        except Exception as e:
            logger.error(f"Failed to cache new report for {cache_key}: {e}")
    # -----------------------------

    logger.info(
        f"SQL explorer run completed in {metadata.get('iterations', 'N/A')} iterations.")
    if metadata.get("final_response_object") and metadata["final_response_object"].usage_metadata:
        logger.info(
            f"Token usage: {metadata['final_response_object'].usage_metadata}")

    return result_text
