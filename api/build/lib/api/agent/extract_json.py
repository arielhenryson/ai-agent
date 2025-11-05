
def extract_json(text: str):
    """
    Extracts a JSON object from a string, typically formatted in a markdown code block.

    Args:
        text: The string containing the JSON object.

    Returns:
        The parsed JSON object (dict or list).

    Raises:
        ValueError: If no valid JSON object is found in the text.
    """
    # Use a regular expression to find content inside a JSON markdown block
    # This pattern looks for ```json ... ``` and captures the content in between.
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)

    json_str_to_parse = ""
    if match:
        json_str_to_parse = match.group(1)
    else:
        # As a fallback, try to use the whole string if no markdown block is found
        json_str_to_parse = text

    try:
        return json.loads(json_str_to_parse)
    except json.JSONDecodeError as e:
        # Raise an exception if parsing fails, providing context.
        raise ValueError(
            f"Failed to decode JSON. Content: '{json_str_to_parse}'") from e
