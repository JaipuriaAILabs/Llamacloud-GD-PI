import click
import os

from mcp.server.fastmcp import Context, FastMCP
from llama_cloud_services import LlamaExtract
from llama_index.indices.managed.llama_cloud import LlamaCloudIndex
from typing import Awaitable, Callable, Optional

from .auth import EmailWhitelistAuth, get_auth_from_env


# MCP instance will be created in main() with proper port configuration
mcp = None
# Global auth instance
auth: Optional[EmailWhitelistAuth] = None


async def verify_request_auth(ctx: Context) -> Optional[str]:
    """
    Verify authentication for a request.

    Returns error message if auth fails, None if auth succeeds or is disabled.
    """
    global auth
    if auth is None:
        # Auth not configured, allow all requests
        return None

    # Try to get token from context metadata
    # The token should be passed via the Authorization header
    try:
        # Access request info from context if available
        request_context = getattr(ctx, 'request_context', None)
        if request_context:
            headers = getattr(request_context, 'headers', {})
            auth_header = headers.get('authorization', headers.get('Authorization', ''))
        else:
            # Fallback: check environment for token (useful for testing)
            auth_header = os.getenv('MCP_AUTH_TOKEN', '')

        if not auth_header:
            return "Authentication required. Please provide a valid Bearer token."

        # Extract token from "Bearer <token>" format
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        else:
            token = auth_header

        # Verify the token
        user = auth.verify_token(token)
        if user is None:
            return "Access denied. Your email is not authorized to use this service."

        await ctx.info(f"Authenticated user: {user.email}")
        return None

    except Exception as e:
        return f"Authentication error: {str(e)}"


def make_index_tool(
    index_name: str, project_name: Optional[str], org_id: Optional[str]
) -> Callable[[Context, str], Awaitable[str]]:
    async def tool(ctx: Context, query: str) -> str:
        # Verify authentication
        auth_error = await verify_request_auth(ctx)
        if auth_error:
            return auth_error

        try:
            await ctx.info(f"Querying index: {index_name} with query: {query}")
            index = LlamaCloudIndex(
                name=index_name,
                project_name=project_name,
                organization_id=org_id,
            )
            response = await index.as_retriever().aretrieve(query)
            return str(response)
        except Exception as e:
            await ctx.error(f"Error querying index: {str(e)}")
            return f"Error querying index: {str(e)}"

    return tool


def make_extract_tool(
    agent_name: str, project_name: Optional[str], org_id: Optional[str]
) -> Callable[[Context, str], Awaitable[str]]:
    async def tool(ctx: Context, file_path: str) -> str:
        """Extract data using a LlamaExtract Agent from the given file."""
        # Verify authentication
        auth_error = await verify_request_auth(ctx)
        if auth_error:
            return auth_error

        try:
            await ctx.info(
                f"Extracting data using agent: {agent_name} with file path: {file_path}"
            )
            llama_extract = LlamaExtract(
                organization_id=org_id,
                project_name=project_name,
            )
            extract_agent = llama_extract.get_agent(name=agent_name)
            result = await extract_agent.aextract(file_path)
            return str(result)
        except Exception as e:
            await ctx.error(f"Error extracting data: {str(e)}")
            return f"Error extracting data: {str(e)}"

    return tool


@click.command()
@click.option(
    "--index",
    "indexes",
    multiple=True,
    required=False,
    type=str,
    help="Index definition in the format name:description. Can be used multiple times.",
)
@click.option(
    "--extract-agent",
    "extract_agents",
    multiple=True,
    required=False,
    type=str,
    help="Extract agent definition in the format name:description. Can be used multiple times.",
)
@click.option(
    "--project-name", required=False, type=str, help="Project name for LlamaCloud"
)
@click.option(
    "--org-id", required=False, type=str, help="Organization ID for LlamaCloud"
)
@click.option(
    "--transport",
    default="stdio",
    type=click.Choice(["stdio", "sse", "streamable-http"]),
    help='Transport to run the MCP server on. One of "stdio", "sse", "streamable-http".',
)
@click.option("--api-key", required=False, type=str, help="API key for LlamaCloud")
@click.option("--port", required=False, type=int, help="Port to run the server on (for sse/streamable-http transports)")
def main(
    indexes: Optional[list[str]],
    extract_agents: Optional[list[str]],
    project_name: Optional[str],
    org_id: Optional[str],
    transport: str,
    api_key: Optional[str],
    port: Optional[int],
) -> None:
    global mcp, auth

    api_key = api_key or os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        raise click.BadParameter(
            "API key not found. Please provide an API key or set the LLAMA_CLOUD_API_KEY environment variable."
        )
    else:
        os.environ["LLAMA_CLOUD_API_KEY"] = api_key

    # Initialize authentication from environment variables
    auth = get_auth_from_env()
    if auth:
        print(f"Authentication enabled with email whitelist")
    else:
        print("Authentication disabled (no SUPABASE_URL or ALLOWED_EMAILS configured)")

    # Get port from parameter or environment variable
    if port is None and transport in ["sse", "streamable-http"]:
        port = int(os.getenv("PORT", "8000"))

    # Initialize FastMCP with port and host if needed
    # Render requires binding to 0.0.0.0 to be accessible
    if transport in ["sse", "streamable-http"] and port:
        mcp = FastMCP("llama-index-server", port=port, host="0.0.0.0")
    else:
        mcp = FastMCP("llama-index-server")

    # Parse indexes into (name, description) tuples
    index_info = []
    if indexes:
        for idx in indexes:
            if ":" not in idx:
                raise click.BadParameter(
                    f"Index '{idx}' must be in the format name:description"
                )
            name, description = idx.split(":", 1)
            index_info.append((name, description))

    # Parse extract agents into (name, description) tuples if provided
    extract_agent_info = []
    if extract_agents:
        for agent in extract_agents:
            if ":" not in agent:
                raise click.BadParameter(
                    f"Extract agent '{agent}' must be in the format name:description"
                )
            name, description = agent.split(":", 1)
            extract_agent_info.append((name, description))

    # Dynamically register a tool for each index
    for name, description in index_info:
        tool_func = make_index_tool(name, project_name, org_id)
        mcp.tool(name=f"query_{name}", description=description)(tool_func)

    # Dynamically register a tool for each extract agent, if any
    for name, description in extract_agent_info:
        tool_func = make_extract_tool(name, project_name, org_id)
        mcp.tool(name=f"extract_{name}", description=description)(tool_func)

    # Run the server (port is already configured in FastMCP constructor)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
