import random
from datetime import datetime
from fastapi import FastAPI, Path
from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# 1. Define the API Application and its Metadata
# This info will appear at the top of your Swagger/OpenAPI docs.
# -------------------------------------------------------------------
app = FastAPI(
    title="Mock Bank Credit Score API",
    description="A mock API service to retrieve customer credit scores. "
                "This service provides simulated, deterministic data for "
                "development and testing purposes.",
    version="1.0.0",
    contact={
        "name": "API Support",
        "email": "support@mockbank.com",
    },
)

# -------------------------------------------------------------------
# 2. Define the Data Models (Pydantic)
# This defines the *shape* of your response.
# FastAPI will use this to:
#   - Automatically validate your outgoing data.
#   - Generate the "Response Schema" in the OpenAPI docs.
# -------------------------------------------------------------------


class CreditScoreResponse(BaseModel):
    """
    The response model containing the customer's credit score details.
    """
    user_id: int = Field(
        ...,
        description="The unique identifier for the customer.",
        example=123
    )
    score: int = Field(
        ...,
        ge=300,
        le=850,
        description="The customer's calculated credit score.",
        example=742
    )
    risk_level: str = Field(
        ...,
        description="The calculated credit risk level (Low, Medium, High).",
        example="Low"
    )
    last_updated: datetime = Field(
        ...,
        description="The timestamp when the score was last calculated."
    )

    # This provides a full, concrete example for the /docs page
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": 123,
                    "score": 742,
                    "risk_level": "Low",
                    "last_updated": "2025-10-30T10:30:00Z"
                },
                {
                    "user_id": 456,
                    "score": 580,
                    "risk_level": "High",
                    "last_updated": "2025-10-29T11:00:00Z"
                }
            ]
        }
    }


# -------------------------------------------------------------------
# 3. Define the API Endpoint
# -------------------------------------------------------------------
@app.get(
    "/credit-score/{user_id}",
    response_model=CreditScoreResponse,
    tags=["Credit Score"],
    summary="Get Customer Credit Score",
    description="Retrieve the mock credit score and risk profile for a "
                "specific customer by their user ID.",
)
async def get_credit_score(
    user_id: int = Path(
        ...,
        description="The unique ID of the customer to query.",
        example=123,
        gt=0  # Adds validation: user_id must be greater than 0
    )
):
    """
    This endpoint generates a deterministic mock credit score based on the user_id.

    - **Deterministic:** The same `user_id` will always return the same score.
    - **Mock Data:** This data is randomly generated and not real.
    """

    # --- Mock Data Generation ---
    # We use the user_id as a seed for the random number generator.
    # This makes the mock data "deterministic" - the same user_id will
    # *always* return the same "random" score, which is great for testing.
    random.seed(user_id)

    mock_score = random.randint(300, 850)

    # Determine risk level based on score
    if mock_score > 750:
        mock_risk = "Low"
    elif mock_score > 650:
        mock_risk = "Medium"
    else:
        mock_risk = "High"

    # Return the data in the shape of our Pydantic model
    return CreditScoreResponse(
        user_id=user_id,
        score=mock_score,
        risk_level=mock_risk,
        last_updated=datetime.now()  # Use current time for "last_updated"
    )
