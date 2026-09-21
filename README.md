# Globus MCP Server

The Globus [MCP](https://modelcontextprotocol.io) Server enables LLM applications to interact
with [Globus](https://www.globus.org/) services.

## Supported Tools

### [Globus Transfer](https://docs.globus.org/api/transfer/)

- `globus_transfer_list_endpoints_and_collections` - List endpoints and collections the user has
access to
- `globus_transfer_search_endpoints_and_collections` - Use a filter string to search all endpoints
and collections that are visible to the user
- `globus_transfer_submit_task` - Submit a transfer task between two collections
- `globus_transfer_get_task_events` - Get a list of task events
- `globus_transfer_list_directory` - List contents of a directory on a collection

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
        "--transfer read operate",
        "--compute read"
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
