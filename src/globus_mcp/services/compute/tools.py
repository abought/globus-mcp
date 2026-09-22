from collections.abc import Callable
from typing import Annotated, Any, Literal

import globus_sdk
from globus_compute_sdk.serialize import JSONData
from globus_compute_sdk.serialize.facade import validate_strategylike
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from globus_mcp.audit import log_tool_call, log_tool_error, log_tool_result
from globus_mcp.categories import ToolCategory
from globus_mcp.context import GlobusContext
from globus_mcp.services.compute.client import get_compute_client
from globus_mcp.services.compute.schemas import (
    ComputeEndpoint,
    ComputeFunctionRegisterResponse,
    ComputeSubmitResponse,
    ComputeTask,
)

_SERVICE = "compute"


def globus_compute_list_endpoints(
    role: Annotated[
        Literal["any", "owner"],
        Field(
            description=(
                "Filter returned list by the user's association to endpoints."
                " Specify 'any' (default) to return all endpoints that the user"
                " can submit tasks to. Specify 'owner' to only return endpoints"
                " that the user owns."
            ),
        ),
    ] = "owner",
    *,
    ctx: Context[GlobusContext],
) -> list[ComputeEndpoint]:
    """List Globus Compute endpoints that the user has access to."""
    log_tool_call(ctx, tool_name=globus_compute_list_endpoints.__name__, service=_SERVICE)
    client = get_compute_client(ctx)

    try:
        res = client.get_endpoints(role=role)
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_compute_list_endpoints.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to get endpoints: {e}") from e

    endpoints = []
    for ep in res:
        endpoint = ComputeEndpoint(
            endpoint_id=ep["uuid"],
            name=ep["name"],
            display_name=ep["display_name"],
            owner_id=ep["owner"],
        )
        endpoints.append(endpoint)

    return endpoints


def globus_compute_register_python_function(
    function_code: Annotated[str, Field(description="The text of the Python function source code")],
    function_name: Annotated[str, Field(description="The name of the Python function")],
    description: Annotated[
        str | None,
        Field(description="An optional description of the Python function"),
    ] = None,
    *,
    ctx: Context[GlobusContext],
) -> ComputeFunctionRegisterResponse:
    """
    Register a new Python function that can then be run on a Globus Compute endpoint via
        `globus_compute_submit_task`.

    This is an advanced feature that adds executable code to a remote environment. Consult
    the user about security implications before proceeding, and check that the python version
    and dependencies for this code match the environment available on the endpoint.
    """
    log_tool_call(ctx, tool_name=globus_compute_register_python_function.__name__, service=_SERVICE)
    client = get_compute_client(ctx)

    try:
        function_id = client.register_source_code(
            # NOTE: public flag is intentionally not exposed to LLMs
            source=function_code,
            function_name=function_name,
            description=description,
        )
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx,
            tool_name=globus_compute_register_python_function.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(f"Failed to register Python function: {e}") from e

    log_tool_result(
        ctx,
        tool_name=globus_compute_register_python_function.__name__,
        service=_SERVICE,
        result={"function_id": function_id},
    )
    return ComputeFunctionRegisterResponse(function_id=function_id)


_SHELL_FUNCTION_TEMPLATE = """
def {function_name}(*args, **kwargs):
    import subprocess
    try:
        completed = subprocess.run(
            '''{command}'''.format(*args, **kwargs),
            shell=True,
            capture_output=True,
            text=True,
            timeout={timeout},
        )
        return {{
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }}
    except subprocess.TimeoutExpired:
        return {{
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out after {timeout} seconds",
        }}
"""


def globus_compute_register_shell_command(
    command: Annotated[
        str,
        Field(
            description=(
                "The shell command string, which may contain variables to be replaced with"
                " args and kwargs provided in each submit call (e.g.`echo {} --foo {foo}`)."
            )
        ),
    ],
    timeout: Annotated[
        float | None,
        Field(description="Maximum execution time in seconds."),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="An optional description of the shell command"),
    ] = None,
    *,
    ctx: Context[GlobusContext],
) -> ComputeFunctionRegisterResponse:
    """
    Register a new shell command function that can then be run on a Globus Compute endpoint via
        `globus_compute_submit_task`.

    The tool it calls must be accessible on the specified compute endpoint host.

    This is an advanced feature that adds executable code to a remote environment. Consult
    the user about security implications before proceeding, and check that the python version
    and dependencies for this code match the environment available on the endpoint.
    """
    log_tool_call(ctx, tool_name=globus_compute_register_shell_command.__name__, service=_SERVICE)
    client = get_compute_client(ctx)

    function_name = "run_shell_command"
    source = _SHELL_FUNCTION_TEMPLATE.format(
        function_name=function_name, command=command, timeout=timeout
    )

    try:
        function_id = client.register_source_code(
            # NOTE: public flag is intentionally not exposed to LLMs
            source=source,
            function_name=function_name,
            description=description,
        )
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx,
            tool_name=globus_compute_register_shell_command.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(f"Failed to register shell command: {e}") from e

    log_tool_result(
        ctx,
        tool_name=globus_compute_register_shell_command.__name__,
        service=_SERVICE,
        result={"function_id": function_id},
    )
    return ComputeFunctionRegisterResponse(function_id=function_id)


def globus_compute_submit_task(
    endpoint_id: Annotated[
        str, Field(description="ID of the endpoint that will execute the function")
    ],
    function_id: Annotated[str, Field(description="ID of the function")],
    function_args: Annotated[
        tuple[Any, ...] | None,
        Field(description="Positional arguments for the function"),
    ],
    function_kwargs: Annotated[
        dict[str, Any] | None, Field(description="Keyword arguments for the function")
    ],
    ctx: Context[GlobusContext],
) -> ComputeSubmitResponse:
    """Run a specified function on a specified Globus Compute endpoint.

    Use `globus_compute_get_task_status` to monitor progress and retrieve results.

    NOTE: In practice, functions are not entirely portable: they depend heavily on the specific
     endpoint chosen. If a tool fails to run, prompt the user to verify the chosen endpoint.
    """
    log_tool_call(ctx, tool_name=globus_compute_submit_task.__name__, service=_SERVICE)
    client = get_compute_client(ctx)

    batch = client.create_batch(result_serializers=[validate_strategylike(JSONData).import_path])
    batch.add(function_id, function_args, function_kwargs)

    try:
        res = client.batch_run(endpoint_id, batch)
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_compute_submit_task.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to submit task: {e}") from e

    task_id = res["tasks"][function_id][0]
    log_tool_result(
        ctx,
        tool_name=globus_compute_submit_task.__name__,
        service=_SERVICE,
        result={"task_id": task_id},
    )
    return ComputeSubmitResponse(task_id=task_id)


def globus_compute_get_task_status(
    task_id: Annotated[str, Field(description="The ID of the task")],
    ctx: Context[GlobusContext],
) -> ComputeTask:
    """Retrieve the status and result of a Globus Compute task."""
    log_tool_call(ctx, tool_name=globus_compute_get_task_status.__name__, service=_SERVICE)
    client = get_compute_client(ctx)

    try:
        res = client._compute_web_client.v2.get_task(task_id)
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_compute_get_task_status.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to get task status: {e}") from e

    result = res.get("result")
    if result:
        try:
            result = client.fx_serializer.deserialize(result)
        except Exception as e:
            log_tool_error(
                ctx, tool_name=globus_compute_get_task_status.__name__, service=_SERVICE, error=e
            )
            raise ToolError("Unable to deserialize result") from e

    return ComputeTask(
        task_id=res["task_id"],
        status=res.get("status"),
        result=result,
        exception=res.get("exception"),
    )


COMPUTE_TOOLS_BY_CATEGORY: dict[ToolCategory, list[Callable[..., Any]]] = {
    ToolCategory.READ: [
        globus_compute_list_endpoints,
        globus_compute_get_task_status,
    ],
    ToolCategory.OPERATE: [
        globus_compute_submit_task,
    ],
    ToolCategory.ADMIN: [
        # Allowing new code to be run on the server is ADMIN level due to the security implications
        globus_compute_register_python_function,
        globus_compute_register_shell_command,
    ],
}
