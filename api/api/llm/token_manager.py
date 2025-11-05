import os
import logging
import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Manages the retrieval and caching of API tokens.

    This class is a singleton to ensure a single, shared cache.
    It supports two modes:
    1. Static API Key: Uses the 'GEMINI_API_KEY' environment variable directly.
    2. Dynamic JWT: Uses 'LLM_ID', 'LLM_SECRET', 'TOKEN_API_URL', and
       'TOKEN_API_SCOPE' to fetch a token from a service and cache it.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TokenManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        logger.info("Initializing TokenManager singleton...")

        # 8-minute TTL as requested (8 * 60 = 480 seconds)
        self.cache = TTLCache(maxsize=1, ttl=480)

        # Check for static key
        self.static_api_key = os.getenv("GEMINI_API_KEY")

        # Config for dynamic token service (from your images)
        self.client_id = os.getenv("LLM_ID")
        self.client_secret = os.getenv("LLM_SECRET")
        self.token_url = os.getenv("TOKEN_API_URL")
        self.token_scope = os.getenv("TOKEN_API_SCOPE")

        if self.static_api_key:
            logger.info("TokenManager: Using static GEMINI_API_KEY.")
        elif self.client_id and self.token_url:
            logger.info(
                "TokenManager: Configured for dynamic token generation.")
            if not self.client_secret:
                logger.warning(
                    "TokenManager: 'LLM_SECRET' is not set. Token request may fail.")
            if not self.token_scope:
                logger.warning(
                    "TokenManager: 'TOKEN_API_SCOPE' is not set. Token request may fail.")
        else:
            logger.error(
                "TokenManager: No API key configuration found. "
                "Set 'GEMINI_API_KEY' OR ('LLM_ID', 'LLM_SECRET', 'TOKEN_API_URL', 'TOKEN_API_SCOPE')."
            )

        self._initialized = True

    def get_token(self) -> str:
        """
        Retrieves the API token.

        Returns the static key if available. Otherwise, attempts to get
        a dynamic token, using the cache if possible.
        """
        if self.static_api_key:
            return self.static_api_key

        if not self.client_id or not self.token_url:
            logger.error(
                "Dynamic token config is incomplete. Missing 'LLM_ID' or 'TOKEN_API_URL'.")
            raise EnvironmentError(
                "Dynamic token config incomplete. Missing 'LLM_ID' or 'TOKEN_API_URL'.")

        return self._get_jwt_token()

    def _get_jwt_token(self) -> str:
        """
        Private method to fetch and cache the JWT.
        Logic is based on your provided images.
        """
        # 1. Try to get from cache
        try:
            token = self.cache.get("jwt_token")
            if token:
                logger.info("Token retrieved from cache.")
                return token
        except Exception as e:
            logger.warning(f"Cache lookup failed (this is unusual): {e}")

        # 2. If not in cache, request a new one
        logger.info(
            "No valid token in cache. Requesting new token from service...")

        payload = {"clientSecret": self.client_secret}
        headers = {"x-client-id": self.client_id}

        # Replicating the POST URL format from your image:
        # {COIN_URL}{CLIENT_ID}?scope={SCOPE}
        if not self.token_scope:
            self.token_scope = ""  # Handle if scope is optional

        url_with_params = f"{self.token_url}{self.client_id}?scope={self.token_scope}"

        try:
            response = requests.post(
                url_with_params,
                headers=headers,
                json=payload,
                timeout=10  # 10-second timeout
            )

            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            token = response.content.decode("utf-8").strip()
            if not token:
                logger.error("Token API returned an empty response.")
                raise ValueError("Token API returned an empty response.")

            # 3. Store in cache on success
            self.cache["jwt_token"] = token
            logger.info("Successfully retrieved and cached new token.")
            return token

        except requests.exceptions.RequestException as e:
            logger.error(f"Error retrieving token: {e}")
            raise  # Re-raise the exception after logging


# --- Singleton Instance ---
# Import this instance in other files
token_manager = TokenManager()
