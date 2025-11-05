import logging
from ...llm.llm import LLM
from .sqlight_tool import sqlite_tool
from ...db.mongo import db_manager  # <-- IMPORTED

logger = logging.getLogger(__name__)

# Define cache duration in one place
CACHE_EXPIRATION_DAYS = 6


async def sql_explorer_tool(db_path: str) -> str:
    """Create a report about the stracture of of the db.

    Args:
      db_path: The path to the database file.
    """

    # --- 1. CHECK CACHE FIRST ---
    try:
        logger.info(f"Checking cache for SQL report: {db_path}")
        cached_report = await db_manager.get_cached_sql_report(
            db_path=db_path,
            max_age_days=CACHE_EXPIRATION_DAYS
        )

        if cached_report:
            logger.info(f"Returning cached SQL report for {db_path}.")
            print(f"Returning cached SQL report for {db_path}.")
            return cached_report

    except Exception as e:
        # Log the error but proceed to generate a new report
        logger.warning(
            f"Cache check failed for {db_path}: {e}. Will generate a new report.")

    # --- 2. IF NO CACHE, GENERATE NEW REPORT ---
    logger.info(f"No valid cache for {db_path}. Generating new report...")
    print(f"No valid cache for {db_path}. Generating new report...")
    print(db_path)  # Your original print statement

    llm = LLM()

    prompt = f"""
        Your sole responsibility is to explore the structure of the sqlite database at {db_path}.
        Use the `sqlite_tool` as many times as you need to perform exploratory queries that help you better 
        understand the data structure.

        Follow this workflow step-by-step before writing the final report:

        1. **Count Queries**: Count the total number of rows in various tables or views.
        2. **Distinct Value Queries**: Retrieve unique values from specific columns.
        3. **Group By Queries**: Aggregate data by grouping and counting rows.
        4. **Range Queries**: Retrieve minimum and maximum values for specific columns.
        5. **Conditional Queries**: Filter data based on specific conditions.

        After completing the above steps, write a detailed report about the database structure. This report will be used later to run queries against the DB, so it should include insights that would assist that.

        The report should be organized in the following sections:

        1. **Database Overview**
        - Name of the database (if provided).
        - Total number of tables.
        - General purpose or domain (based on names, column content, and context).

        2. **Table-by-Table Analysis**
        For each table:
        - Table name and description (inferred from name & content).
        - Number of rows (if available).
        - List of ALL columns with:
        - Column name
        - Data type
        - Nullability
        - Default values
        - Constraints (PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK, etc.)
        - Indexes
        - Auto-increment properties (if applicable)
        - DISTINCT values for categorical columns (and values meaning)
        - MIN/MAX for numerical columns
        - Description of the likely meaning of each column (inferred from its name and sample data).
        - Distribution statistics for each column:
        - Min, Max, Average (for numeric/date types)
        - Common values and frequency
        - Null percentage
        - Text length ranges for string columns
        - Example rows showing representative data.

        3. **Relationships & Keys**
        - Identify primary keys and foreign keys.
        - Describe relationships between tables (one-to-many, many-to-many).
        - Highlight any orphaned relationships or missing links.

        4. **Data Quality Observations**
        - Missing or inconsistent values.
        - Duplicates (if visible from samples).
        - Possible data anomalies.

        5. **Inferred Business Logic**
        - Guess the possible role of each table in the application/business context.
        - Identify columns that might be identifiers, timestamps, flags, or category labels.

        6. **Temporal Information**
        - Identify any date/time columns and what they likely represent (e.g., creation date, last update, expiration date).
        - Look for periodic patterns or ranges in the dates.

        7. **Security & Privacy Considerations**
        - Detect any columns likely containing PII (names, emails, phone numbers, addresses).
        - Identify any sensitive financial/health-related fields.

        8. **Summary & Recommendations**
        - Summarize the structure and purpose of the database.
        - Recommend further actions for documentation, cleaning, normalization, or optimization.

        Formatting:
        - Use clear headings and subheadings.
        - Use bullet points or tables for clarity.
        - Include both the factual schema details and your inferred interpretations.

        Important:
        - Do not fabricate details not supported by the schema or sample data.
        - Always clearly separate observed facts from inferred guesses.
        """

    print(prompt)

    # Unpack the result and metadata
    result_text, metadata = await llm.run(
        prompt=prompt,
        max_calls=100,
        delay_ms=1000 * 10,
        tools=[
            sqlite_tool
        ]
    )

    # --- 3. CACHE THE NEW RESULT ---
    if result_text:
        try:
            logger.info(f"Caching new report for {db_path}.")
            await db_manager.cache_sql_report(
                db_path=db_path,
                report_content=result_text
            )
        except Exception as e:
            logger.error(f"Failed to cache new report for {db_path}: {e}")
    # -----------------------------

    # Optional: Log metadata
    logger.info(
        f"SQL explorer run completed in {metadata.get('iterations', 'N/A')} iterations.")
    if metadata.get("final_response_object") and metadata["final_response_object"].usage_metadata:
        logger.info(
            f"Token usage: {metadata['final_response_object'].usage_metadata}")

    # Return just the text result
    return result_text
