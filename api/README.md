# Data Discovery API

## Setup Local Environment with Conda

Create and activate a Conda environment:
Open your terminal and run the following commands. This will create a new environment named ai-agent with Python 3.11 and activate it.

```bash
conda create --name ai-agent python=3.12 -y
conda activate ai-agent
```

Install dependencies:
With the environment activated, install the project dependencies. This command reads the pyproject.toml file and installs the required packages.

```bash
pip install .
```

How to run the server
Once your environment is set up and the dependencies are installed, use the following command to run the server:

```bash
uvicorn api.main:app --reload
```

Mock Data

To run the mock data server for credit score, use the following command:

```bash
cd api/api/mock_data/credit_score && uvicorn credit_score:app --reload --port 8001
```
