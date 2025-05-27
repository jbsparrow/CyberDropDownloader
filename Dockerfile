# Use an official Python 3.11 image.
FROM python:3.11-slim

# Set environment variables
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VENV_CREATE=false \
    PATH="/opt/poetry/bin:$PATH"

# Install poetry
RUN apt-get update && \
    apt-get install -y curl && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    apt-get remove -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the project files for dependency installation
COPY pyproject.toml poetry.lock* /app/

# Install project dependencies
RUN poetry install --no-dev --no-root --no-interaction --no-ansi

# Copy the rest of the application code
COPY . /app/

# Set the entrypoint
ENTRYPOINT ["cyberdrop-dl"]
