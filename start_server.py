#!/usr/bin/env python3
"""
Startup script for deploying LlamaCloud MCP server on Render.
This script reads configuration from environment variables and starts the MCP server.
"""
import os
import sys
from llamacloud_mcp.main import main

def start():
    """Start the MCP server with configuration from environment variables."""

    # Get configuration from environment variables
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    index_name = os.getenv("INDEX_NAME", "")
    index_description = os.getenv("INDEX_DESCRIPTION", "Search index")
    project_name = os.getenv("PROJECT_NAME")
    org_id = os.getenv("ORG_ID")
    transport = os.getenv("TRANSPORT", "streamable-http")
    port = os.getenv("PORT", "8000")  # Render provides PORT env var

    # Validate required variables
    if not api_key:
        print("ERROR: LLAMA_CLOUD_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    if not org_id:
        print("ERROR: ORG_ID environment variable is required", file=sys.stderr)
        sys.exit(1)

    # Set the API key in environment for the MCP server
    os.environ["LLAMA_CLOUD_API_KEY"] = api_key

    # Build the command line arguments
    args = []

    # Add index if configured
    if index_name:
        index_arg = f"{index_name}:{index_description}"
        args.extend(["--index", index_arg])

    # Add project name if configured
    if project_name:
        args.extend(["--project-id", project_name])

    # Add org ID
    args.extend(["--org-id", org_id])

    # Add transport
    args.extend(["--transport", transport])

    # Add API key
    args.extend(["--api-key", api_key])

    print(f"Starting LlamaCloud MCP Server on port {port}...")
    print(f"Transport: {transport}")
    print(f"Index: {index_name}")
    print(f"Organization ID: {org_id}")
    print(f"Project: {project_name}")

    # Set sys.argv to simulate command line arguments
    sys.argv = ["llamacloud-mcp"] + args

    # Run the main function
    try:
        main()
    except Exception as e:
        print(f"ERROR: Failed to start server: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    start()
