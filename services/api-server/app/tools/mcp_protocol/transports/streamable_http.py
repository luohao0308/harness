from app.tools.mcp_protocol.transports.http_transport import MCPHTTPTransport


class MCPStreamableHTTPTransport(MCPHTTPTransport):
    """Minimal streamable-http transport facade.

    The current implementation uses one request/response cycle with SSE-aware
    parsing. It keeps the transport name explicit so runtime configuration can
    distinguish future bidirectional stream support without changing callers.
    """
