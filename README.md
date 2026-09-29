# Globus MCP Server

The Globus [MCP](https://modelcontextprotocol.io) Server enables LLM applications to interact
with [Globus](https://www.globus.org/) services.

## Supported Tools

### [Globus Transfer](https://docs.globus.org/api/transfer/)

- `globus_transfer_list_collections` - List endpoints and collections the user has
access to
- `globus_transfer_search_collections` - Use a filter string to search all endpoints
and collections that are visible to the user
- `globus_transfer_submit_file_transfer_task` - Submit a transfer task between two collections
- `globus_transfer_get_task_status` - Get the status and progress of a transfer task
- `globus_transfer_get_task_events` - Get a list of task events
- `globus_transfer_list_directory_contents` - List contents of a directory on a collection
- `globus_transfer_stat_path` - Get metadata for a file or directory on a collection
- `globus_transfer_direct_read_content` - Read a small file directly from a collection via HTTPS
- `globus_transfer_direct_upload_content_via_https` - Upload small content directly to a
  collection via HTTPS
- `globus_transfer_upload_file_via_https` - Write a local file to a collection via HTTPS
  (requires `FILESYSTEM_ROOT`)
- `globus_transfer_download_file_via_https` - Download a file from a collection via HTTPS
  (requires `FILESYSTEM_ROOT`)

### [Globus Compute](https://docs.globus.org/compute/)

- `globus_compute_list_endpoints` - List endpoints that the user has access to
- `globus_compute_register_python_function` - Register a Python function
- `globus_compute_register_shell_command` - Register a shell command
- `globus_compute_submit_task` - Submit a task to an endpoint
- `globus_compute_get_task_status` - Retrieve the status and result of a task

## Configuration

The following configuration is compatible with most LLM applications that support MCP such as
[Claude Desktop](https://modelcontextprotocol.io/docs/develop/connect-local-servers):

The Globus MCP server is designed to limit the tools it exposes. Each service exposes a command line flag (`--transfer`, `--compute`, etc), and tools are grouped by their level of impact:

* `read`: Perform read-ony operations such as list that do not change state
* `operate`: initiate operations that may change state, such as transferring a file or running a function
* `admin`: Highly sensitive operations that may alter the behavior of the system, such as changing configuration, registering new runnable compute functions, or creating/deleting resources.

If the service flag is specified without a level, only `read` tools will be activated. See usage example below:

```json
{
  "mcpServers": {
    "globus-mcp": {
      "command": "uvx",
      "args": [
        "globus-mcp",
        "--transfer", "read", "operate",
        "--compute", "read"
      ]
    }
  }
}
```

### Specifying Client Credentials

If you've [registered a client application](https://docs.globus.org/api/auth/developer-guide/#register-app) in the [Globus web UI](https://app.globus.org/settings/developers/), you can specify the client credentials via the `GLOBUS_CLIENT_ID` and `GLOBUS_CLIENT_SECRET` environment variables:

```json
{
  "mcpServers": {
    "globus-mcp": {
      "command": "uvx",
      "args": ["globus-mcp"],
      "env": {
        "GLOBUS_CLIENT_ID": "...",
        "GLOBUS_CLIENT_SECRET": "..."
      }
    }
  }
}
```

Service account / client credentials are recommended for many local single-user scenarios, because it ensures that the LLM operates under tighter access limitations than your user account. For example, if you (a human) split your time among three projects, then there is no guarantee that an LLM would restrict itself to the data you tell it to read. A service account can be used to establish a hard permissions boundary that can only see resources for one specific project. 

The disadvantage of service accounts is that they are entirely separate identities: you will need to re-grant access to every affected resource, and not every service supports guest / service account identities.

### Shared Filesystem

Some tools can read and write files that are too large to fit in the LLM context window — for
example, you may want the MCP server to read or write a file on one end, and have it processed by the coding agent via a one-off script on the other end.  Example use cases include data download for analysis, or building a search index too large to fit into memory.

To enable these tools, set `FILESYSTEM_ROOT` to a directory that both the MCP server process and your agent environment can access at the same path:

```json
{
  "mcpServers": {
    "globus-mcp": {
      "command": "uvx",
      "args": ["globus-mcp", "--transfer", "read", "operate"],
      "env": {
        "FILESYSTEM_ROOT": "/path/to/shared/folder"
      }
    }
  }
}
```

When `FILESYSTEM_ROOT` is set the server registers `mcp_get_shared_mount_location`, which the  agent can call to discover the path. The directory must already exist, and the server will refuse to start if it overlaps with system directories, the Python environment, or known credential stores (`.ssh`, `.aws`, etc.). This is a best-effort safeguard, and if you use these advanced filesystem tools, **it is up to you to ensure that no sensitive data is compromised**.

> **Note:** If your agent runs in a sandbox or container, ensure the shared directory is mounted
> at the same absolute path inside the sandbox. The MCP server cannot verify agent-side
> accessibility — use `mcp_get_shared_mount_location` and confirm the path is reachable before
> relying on file-based workflows.

### Resource restriction whitelists
In many cases, the Globus permissions model means that a service token is allowed to use all resources available to the user: eg all transfer collections. 

For compliance or data usage agreement reasons, it is sometimes useful to draw narrower boundaries around what a specific LLM can access. 

Operations in this MCP server may be configured to only work with a whitelist of allowed resources (for transfer, the source and destination whitelists are controlled separately). This is helpful for meeting compliance and security control requirements. This is orthogonal to permissions controls; it simply prevents the LLM from attempting an operation at all.

This feature is active when `GLOBUS_TRANSFER_ALLOWED_SOURCE_COLLECTIONS` and/or
`GLOBUS_TRANSFER_ALLOWED_DESTINATION_COLLECTIONS` are set to a comma-separated list of collection IDs:

```json
{
  "mcpServers": {
    "globus-mcp": {
      "command": "uvx",
      "args": ["globus-mcp", "--transfer", "read", "operate"],
      "env": {
        "GLOBUS_TRANSFER_ALLOWED_SOURCE_COLLECTIONS": "aaaaaaaa-...",
        "GLOBUS_TRANSFER_ALLOWED_DESTINATION_COLLECTIONS": "bbbbbbbb-...,cccccccc-..."
      }
    }
  }
}
```

## Development
See the included `Makefile` for development commands.
