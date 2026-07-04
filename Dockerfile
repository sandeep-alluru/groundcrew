FROM python:3.12-slim

WORKDIR /app

# Install package with MCP extras from PyPI
RUN pip install --no-cache-dir 'groundcrew[mcp]'

# MCP stdio server — Glama sends JSON-RPC over stdin, reads responses from stdout
CMD ["groundcrew-mcp"]
