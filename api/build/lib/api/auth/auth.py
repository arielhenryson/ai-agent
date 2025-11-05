import json
from urllib.request import urlopen
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
import os
import sys  # Import the sys module to exit the application
from dotenv import load_dotenv

load_dotenv()

# --- Auth0 Configuration ---
# This is the same as your Auth0 API "Identifier"
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE")
# This is your Auth0 domain
OIDC_DOMAIN = os.getenv("OIDC_DOMAIN")
# The algorithm used to sign the token
ALGORITHMS = ["RS256"]


# --- Environment Variable Validation ---
# We check for the presence of the required environment variables.
# If any are missing, we print an error to the console and exit.
if not all([OIDC_AUDIENCE, OIDC_DOMAIN]):
    missing_vars = []
    if not OIDC_AUDIENCE:
        missing_vars.append("OIDC_AUDIENCE")
    if not OIDC_DOMAIN:
        missing_vars.append("OIDC_DOMAIN")

    # Print a clear error message to standard error
    print(
        f"🔴 Error: Missing required environment variable(s): {', '.join(missing_vars)}",
        file=sys.stderr
    )
    # Exit the application with a non-zero status code to indicate an error
    sys.exit(1)


# --- Authentication Utility Class (previously in auth.py) ---

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# A dictionary to cache the JWKS to avoid repeated network requests
_jwks_cache = {}


class VerifyToken:
    """Does all the token verification using python-jose"""

    def __init__(self):
        self.jwks_url = f'https://{OIDC_DOMAIN}/.well-known/jwks.json'

    def _get_jwks(self):
        """
        Fetches the JSON Web Key Set (JWKS) from the Auth0 domain.
        Caches the result.
        """
        if "keys" in _jwks_cache:
            return _jwks_cache

        try:
            jsonurl = urlopen(self.jwks_url)
            jwks = json.loads(jsonurl.read())
            _jwks_cache.update(jwks)
            return jwks
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Could not fetch JWKS: {e}")

    def verify(self, token: str = Depends(oauth2_scheme)):
        """
        Decodes the token, verifies the signature, and validates the claims.
        """

        try:
            jwks = self._get_jwks()
            # Get the unverified header from the token
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}

            # Find the correct key in the JWKS based on the key ID ("kid")
            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }
                    break

            if not rsa_key:
                raise HTTPException(
                    status_code=401, detail="Unable to find appropriate key")

            # Decode and validate the token
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=ALGORITHMS,
                audience=OIDC_AUDIENCE,
                issuer=f'https://{OIDC_DOMAIN}/'
            )
            return payload

        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token is expired")
        except jwt.JWTClaimsError:
            raise HTTPException(
                status_code=401, detail="Incorrect claims, please check the audience and issuer")
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail=f"Unable to parse authentication token. Error: {e}"
            )
