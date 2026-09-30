from collections.abc import Callable
from typing import Annotated, Any

import globus_sdk
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from globus_mcp.core.audit import audited, log_tool_result
from globus_mcp.core.categories import ToolCategory
from globus_mcp.core.context import GlobusContext
from globus_mcp.services.search.client import get_search_client
from globus_mcp.services.search.projection import compile_field_patterns, select_fields
from globus_mcp.services.search.schemas.indices import SearchIndex, SearchIndexFieldMapping
from globus_mcp.services.search.schemas.query import Boost, Facet, Filter, Sort
from globus_mcp.services.search.schemas.results import (
    FacetBucket,
    FacetResult,
    SearchEntry,
    SearchQueryResult,
    SearchSubject,
)
from globus_mcp.services.search.whitelist import check_index_allowed, search_whitelist

_SERVICE = "search"


def _dump(items: list[BaseModel] | None) -> list[dict[str, Any]] | None:
    if items is None:
        return None
    return [i.model_dump(mode="json", by_alias=True, exclude_none=True) for i in items]


def _build_query_body(
    *,
    q: str | None,
    advanced: bool,
    filters: list[Any] | None,
    facets: list[Any] | None,
    post_facet_filters: list[Any] | None,
    boosts: list[Any] | None,
    sort: list[Any] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "advanced": advanced,
        "bypass_visible_to": False,  # hide admin only behaviors from query
        "fields": ["content"],
        "q": q,
        "filters": _dump(filters),
        "facets": _dump(facets),
        "post_facet_filters": _dump(post_facet_filters),
        "boosts": _dump(boosts),
        "sort": _dump(sort),
    }
    return {k: v for k, v in body.items() if v is not None}


def _format_query_response(
    data: dict[str, Any], only_fields: list[str] | None = None
) -> SearchQueryResult:
    patterns = compile_field_patterns(only_fields) if only_fields else None
    facet_results = None
    if "facet_results" in data:
        facet_results = [
            FacetResult(
                name=f["name"],
                value=f.get("value"),
                buckets=(
                    [FacetBucket(value=b["value"], count=b["count"]) for b in f["buckets"]]
                    if "buckets" in f
                    else None
                ),
            )
            for f in data["facet_results"]
        ]
    return SearchQueryResult(
        total=data["total"],
        count=data["count"],
        offset=data["offset"],
        has_next_page=data["has_next_page"],
        gmeta=[
            SearchSubject(
                subject=g["subject"],
                entries=[
                    SearchEntry(
                        entry_id=e.get("entry_id"),
                        content=(
                            e["content"]
                            if patterns is None
                            else select_fields(e["content"], patterns)
                        ),
                    )
                    for e in g["entries"]
                ],
            )
            for g in data["gmeta"]
        ],
        facet_results=facet_results,
    )


@audited(_SERVICE)
def globus_search_list_indices(*, ctx: Context[GlobusContext]) -> list[SearchIndex]:
    """
    List Globus Search indices visible to the current user.

    Not every index will be usable by this MCP server. Check `allowed` on each entry.
    """
    client = get_search_client(ctx)
    search_config = ctx.request_context.lifespan_context.config.search

    try:
        r = client.index_list()
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to list search indices: {e}") from e

    indices = []
    for idx in r.data.get("index_list", []):
        indices.append(
            SearchIndex(
                index_id=idx["id"],
                display_name=idx["display_name"],
                description=idx.get("description"),
                size=idx.get("size"),
                num_subjects=idx.get("num_subjects"),
                allowed=check_index_allowed(search_config, idx["id"], err=False),
            )
        )

    log_tool_result(
        ctx,
        tool_name=globus_search_list_indices.__name__,
        service=_SERVICE,
        result={"count": len(indices)},
    )
    return indices


@audited(_SERVICE)
@search_whitelist("index_id")
def globus_search_query(
    index_id: Annotated[str, Field(description="ID of the search index to query")],
    q: Annotated[
        str | None,
        Field(
            description=(
                "Query string. Required unless `filters` is given. By default it is parsed"
                " leniently; with `advanced` it supports field:value terms, AND/OR/NOT and"
                " parentheses, and a malformed query is an error."
            )
        ),
    ] = None,
    advanced: Annotated[
        bool, Field(description="Enable elasticsearch-style advanced query string syntax for `q`.")
    ] = False,
    filters: Annotated[
        list[Filter] | None,
        Field(description="Filters restricting the results. Applied before facets are counted."),
    ] = None,
    facets: Annotated[
        list[Facet] | None, Field(description="Aggregations (counts, histograms, sums) to compute.")
    ] = None,
    post_facet_filters: Annotated[
        list[Filter] | None,
        Field(description="Filters applied to results only, after facet counts are computed."),
    ] = None,
    boosts: Annotated[
        list[Boost] | None,
        Field(description="Relevance weights per field. Ignored by the service if `sort` is set."),
    ] = None,
    sort: Annotated[
        list[Sort] | None, Field(description="Explicit result ordering, instead of relevance.")
    ] = None,
    only_fields: Annotated[
        list[str] | None,
        Field(
            min_length=1,
            description=(
                "Limit each entry's `content` to these fields, to keep responses small."
                " Dotted paths into nested objects, eg `dc.titles.title`; `*` is a wildcard,"
                " eg `dc.*`. Selecting an object returns everything under it. Paths that match"
                " nothing are ignored, so an entry whose content has none of these fields comes"
                " back with empty `content`: re-request with different or more fields."
                " Omit to return full content. See `globus_search_get_index_field_mapping`."
            ),
        ),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum results to return.")] = 25,
    offset: Annotated[int, Field(ge=0, description="Zero based offset into the result set.")] = 0,
    *,
    ctx: Context[GlobusContext],
) -> SearchQueryResult:
    """
    Query a Globus Search index.

    For advanced queries: nested fields are separated with `.`, eg `dc.title`.

    Result fields are index-specific. See `globus_search_get_index_field_mapping` for index-specific
    field mappings.
    """
    if q is None and not filters:
        raise ToolError("At least one of `q` or `filters` is required.")

    client = get_search_client(ctx)
    body = _build_query_body(
        q=q,
        advanced=advanced,
        filters=filters,
        facets=facets,
        post_facet_filters=post_facet_filters,
        boosts=boosts,
        sort=sort,
    )
    try:
        r = client.post_search(index_id, body, limit=limit, offset=offset)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Search query failed: {e}") from e

    result = _format_query_response(r.data, only_fields)
    log_tool_result(
        ctx,
        tool_name=globus_search_query.__name__,
        service=_SERVICE,
        result={"count": result.count, "total": result.total},
    )
    return result


@audited(_SERVICE)
@search_whitelist("index_id")
def globus_search_get_index_field_mapping(
    index_id: Annotated[str, Field(description="ID of the search index")],
    *,
    ctx: Context[GlobusContext],
) -> SearchIndexFieldMapping:
    """
    Get the field mappings (field name -> type) for a Globus Search index.

    Use this to discover which fields can be used in queries, filters, facets and sorts
    for a given index. Nested fields are separated with `.`, eg `dc.titles.title`.
    """
    client = get_search_client(ctx)

    # Undocumented beta API: not wrapped by the SDK, so use the authenticated generic request.
    try:
        r = client.get(f"/beta/index/{index_id}/mapping")
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Field mapping unavailable for index {index_id!r}: {e}") from e

    mappings = r.get("mappings")
    if not isinstance(mappings, dict):
        raise ToolError(f"Field mapping unavailable for index {index_id!r}: unexpected response")

    return SearchIndexFieldMapping(index_id=index_id, mappings=mappings)


SEARCH_TOOLS_BY_CATEGORY: dict[ToolCategory, list[Callable[..., Any]]] = {
    ToolCategory.READ: [
        globus_search_list_indices,
        globus_search_get_index_field_mapping,
        globus_search_query,
    ],
    ToolCategory.OPERATE: [],
    ToolCategory.ADMIN: [],
}
