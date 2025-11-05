import os
import requests
from functools import lru_cache
from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt, jwk
from jose.exceptions import JOSEError

# Load environment variables from a .env file at the start
load_dotenv()

# --- Configuration ---
# Load these from environment variables for security.
# They will be read from your .env file.
OIDC_PROVIDER_URL = os.getenv(
    "OIDC_PROVIDER_URL", "https://your-oidc-provider.com/auth/realms/your-realm")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "your-api-audience")

# This will expect a header like: `Authorization: Bearer <token>`
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

# --- CORS Middleware ---
# This is crucial for allowing your Angular frontend to communicate with the backend.
# Adjust origins as needed for your production environment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],  # Your Angular app's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- OIDC Token Validation Logic ---


@lru_cache()
def get_jwks():
    """
    Fetches the JSON Web Key Set (JWKS) from the OIDC provider.
    The result is cached to avoid fetching it on every request.
    """
    try:
        oidc_config_url = f"{OIDC_PROVIDER_URL}/.well-known/openid-configuration"
        oidc_config = requests.get(oidc_config_url, timeout=5).json()
        jwks_uri = oidc_config.get("jwks_uri")
        if not jwks_uri:
            raise HTTPException(
                status_code=500, detail="jwks_uri not found in OIDC config")

        return requests.get(jwks_uri, timeout=5).json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=503, detail=f"Could not fetch OIDC configuration or JWKS: {e}")


async def get_current_user_claims(token: str = Depends(oauth2_scheme)):
    """
    Dependency to validate the OIDC token and extract its claims.
    This function will be called for every request to a protected endpoint.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1. Get the unverified header from the token to find the correct key
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}

        # 2. Fetch the JWKS from the provider
        jwks = get_jwks()

        # 3. Find the key in JWKS that matches the key ID ('kid') from the token header
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break

        if not rsa_key:
            raise credentials_exception

        # 4. Decode and validate the token
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=OIDC_AUDIENCE,
            issuer=OIDC_PROVIDER_URL
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (JOSEError, KeyError):
        # Catches errors from finding the key or decoding
        raise credentials_exception


# --- API Endpoints ---

@app.get("/")
def read_root():
    """A public endpoint that anyone can access."""
    return {"Hello": "World", "authenticated": False}


@app.get("/test")
def read_protected_test_endpoint(claims: dict = Depends(get_current_user_claims)):
    """
    A protected endpoint.
    The `Depends(get_current_user_claims)` ensures that only requests with a valid
    JWT from your OIDC provider can access it. The validated claims are
    injected into the `claims` variable.
    """
    # You can now trust the claims and use them in your logic.
    # For example, 'sub' is a standard claim for the user's unique ID.
    user_id = claims.get("sub")

    return {
        "message": f"Hello, you are an authenticated user with ID: {user_id}!",
        "authenticated": True,
        "all_claims": claims
    }

# To run this app:
# 1. Create a .env file in this directory (see the provided .env file).
# 2. Install dependencies from requirements.txt:
#    pip install -r requirements.txt
# 3. Run with uvicorn:
#    uvicorn main:app --reload
