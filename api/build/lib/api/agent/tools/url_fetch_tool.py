import logging
import aiohttp
import json

logger = logging.getLogger(__name__)


async def url_fetch_tool(url: str) -> str:
    """
    Fetches the content from a given URL.

    It attempts to parse the content as JSON. If successful, it returns
    the pretty-printed JSON string. If not, it returns the raw text.

    Args:
        url: The URL to fetch.

    Returns:
        A string containing the fetched content (JSON or raw text), 
        or an error message.
    """
    logger.info(f"Fetching content from: {url}")
    try:
        # Use a timeout for safety
        timeout = aiohttp.ClientTimeout(total=10)  # 10 seconds total timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()  # Raise an exception for bad status codes (4xx, 5xx)

                # Try to parse as JSON first
                try:
                    # content_type=None tells it to try parsing even if header isn't application/json
                    data = await response.json(content_type=None)
                    logger.info(f"Successfully parsed JSON from {url}")
                    # Return as an indented string for easy reading
                    return json.dumps(data, indent=2)
                except (aiohttp.client_exceptions.ContentTypeError, json.JSONDecodeError, UnicodeDecodeError):
                    # If not JSON, fall back to raw text
                    logger.info(
                        f"Could not parse as JSON, returning raw text for {url}")
                    text_content = await response.text()
                    return text_content

    except aiohttp.ClientError as e:
        logger.error(f"HTTP error fetching {url}: {e}")
        return f"Error: Could not fetch URL. HTTP status: {getattr(e, 'status', 'N/A')}. Message: {e}"
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return f"Error: An unexpected error occurred: {e}"
