FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files + minimal package stub for caching
COPY pyproject.toml uv.lock ./
COPY mcp_conductor/__init__.py mcp_conductor/__init__.py

# Install dependencies (cached unless pyproject.toml/uv.lock change)
RUN uv sync --frozen --no-dev

# Copy remaining source code
COPY . .

# Create tmp directories
RUN mkdir -p ./tmp/images
