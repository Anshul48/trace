# Use a slim Python image
FROM python:3.12-slim

# Install uv by copying it from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (without installing the project itself)
RUN uv sync --frozen --no-install-project

# Copy the rest of the application code
COPY . .

# Sync the project
RUN uv sync --frozen

# API is the default container process.  The same image can run the durable
# worker or migration process with ``uv run python main.py worker`` and
# ``uv run python main.py migrate``; no specific orchestrator is required.
CMD ["uv", "run", "uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8000"]
