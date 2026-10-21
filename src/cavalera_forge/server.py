# -*- coding: utf-8 -*-
"""Cavalera Forge MCP server: Star Citizen crafting, mining and trading.

    cavalera-forge-mcp                     # stdio, local (downloads the data once a day)
    cavalera-forge-mcp --http --port 8793  # Streamable HTTP, behind a reverse proxy

Everything the Cavalera Forge Discord bot answers, for Claude and any MCP
client: recipes and quality effects, ingredients, missions, mining
locations, scan signatures, extraction profiles, refinery yields, terminal
prices, and the UEX player marketplace. Read only, public data.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Annotated, Literal

from pydantic import Field

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from uex_market import client as uex_client
from uex_market.market import Market

from . import __version__
from .data import DataError, Forge

log = logging.getLogger("cavalera_forge")

INSTRUCTIONS = """\
Cavalera Forge: Star Citizen crafting, mining and trading data (prices
and player listings from the UEX marketplace). Same answers as the
Cavalera Forge Discord bot.

- Crafting: product_recipe (ingredients, quantities, minimum quality and
  how ingredient quality changes the product stats), search_products,
  ingredient_uses (what uses an ingredient), craftable_from (what can be
  made from ingredients on hand), product_missions (missions rewarding it).
- Mining: mineral_info is the one-stop card (where, scan signatures,
  extraction profile, quality bands, refining, terminal prices).
  mining_locations for the full list, identify_signature for a value read
  on the scanner, refinery_yields per refinery.
- Trading: terminal_prices (best terminals buying a mineral) and
  marketplace_search (UEX player-to-player listings with combined filters:
  quality, age, price, system, seller...).
- Chain the tools for multi-step questions, e.g. recipe -> mineral_info for
  each ingredient -> marketplace_search for the missing one.
- All numbers come from the tools; never estimate one. Say which game
  version the data is for (data_status) when it matters.
- Marketplace: give listing URLs, quote price with its unit, flag qualities
  read from titles ('~886') or defaults ('500?'), and remind that trades
  happen between players at their own risk.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=True)


def build_server(forge=None, market=None, data_dir=None, cache_dir=None):
    forge = forge or Forge(data_dir)
    market = market or Market(cache_dir=cache_dir)
    mcp = MCPServer(name="cavalera-forge", title="Cavalera Forge (Star Citizen)",
                    version=__version__, instructions=INSTRUCTIONS,
                    website_url="https://github.com/jbillochon/cavalera-forge-mcp")

    def guarded(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DataError as exc:
            raise ToolError("Game data unavailable: %s" % exc)
        except uex_client.UexError as exc:
            raise ToolError("UEX API unavailable right now (%s). Retry in a minute." % exc)

    # Status -----------------------------------------------------------------

    @mcp.tool(title="Data status", annotations=READ_ONLY)
    def data_status() -> dict:
        """Game version the data is built for, data freshness, counts."""
        out = guarded(forge.status)
        out["marketplace"] = market.status()
        out["server"] = dict(name="cavalera-forge-mcp", version=__version__)
        return out

    # Crafting ---------------------------------------------------------------

    @mcp.tool(title="Search craftable products", annotations=READ_ONLY)
    def search_products(
        query: Annotated[str, Field(min_length=2, description="Part of a product name, e.g. 'Pembroke', 'Arrowhead'.")],
        product_type: Annotated[str | None, Field(description=(
            "Optional type filter: armour, weapons, ammo, cooler, powerplant, quantumdrive, "
            "shield, radar, mininglaser, miningmodule, tractorbeam, salvage, refuelling, orepod. "
            "Call with list_types=true to see all."))] = None,
        list_types: Annotated[bool, Field(description="Return the product types and subtypes instead.")] = False,
        limit: Annotated[int, Field(ge=1, le=50)] = 15,
    ) -> dict:
        """Find craftable products by name (typo tolerant)."""
        if list_types:
            return dict(types=guarded(forge.product_types))
        return guarded(forge.search_products, query, product_type, limit)

    @mcp.tool(title="Product recipe", annotations=READ_ONLY)
    def product_recipe(
        product: Annotated[str | None, Field(description="Product name.")] = None,
        product_id: Annotated[int | None, Field(description="Exact id from search_products or a candidates list.")] = None,
    ) -> dict:
        """Crafting recipe(s) of a product: per slot the ingredient, quantity,
        minimum quality, and how the ingredient quality moves each stat of
        the product (percent at lowest and highest quality). Also the craft
        time and how many missions reward the product."""
        if not product and not product_id:
            raise ToolError("Give product or product_id.")
        return guarded(forge.product_recipe, product, product_id)

    @mcp.tool(title="Missions rewarding a product", annotations=READ_ONLY)
    def product_missions(
        product: Annotated[str | None, Field(description="Product name.")] = None,
        product_id: Annotated[int | None, Field(description="Exact product id.")] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 15,
    ) -> dict:
        """Missions that can reward this product (blueprint or item), best
        paid first: type, faction, systems, reward, required standing."""
        if not product and not product_id:
            raise ToolError("Give product or product_id.")
        return guarded(forge.product_missions, product, product_id, limit)

    @mcp.tool(title="What uses an ingredient", annotations=READ_ONLY)
    def ingredient_uses(
        ingredient: Annotated[str, Field(min_length=2, description="Ingredient name, e.g. 'Stileron', 'Taranite'.")],
        product_type: Annotated[str | None, Field(description="Optional product type filter.")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 40,
    ) -> dict:
        """Products that use an ingredient, with quantities and a breakdown
        by product type."""
        return guarded(forge.ingredient_uses, ingredient, product_type, limit)

    @mcp.tool(title="Craftable from ingredients", annotations=READ_ONLY)
    def craftable_from(
        ingredients: Annotated[list[str], Field(min_length=1, max_length=12, description="Ingredients on hand.")],
        product_type: Annotated[str | None, Field(description="Optional product type filter.")] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 25,
    ) -> dict:
        """Products craftable from the given ingredients: complete recipes
        first, then the ones closest to complete (slots covered / total)."""
        return guarded(forge.craftable_from, ingredients, product_type, limit)

    # Mining -----------------------------------------------------------------

    @mcp.tool(title="Mineral card", annotations=READ_ONLY)
    def mineral_info(
        mineral: Annotated[str, Field(min_length=2, description="Mineral or ore, e.g. 'Quantainium', 'Stileron (Raw)', 'Ice'.")],
        locations: Annotated[int, Field(ge=1, le=30)] = 8,
    ) -> dict:
        """Everything about a mineral: best mining locations, scan signature
        per rock and method, extraction profile (resistance, instability,
        optimal window, explosion), quality bands, best and worst refineries,
        best terminal sell prices."""
        return guarded(forge.mineral_info, mineral, locations)

    @mcp.tool(title="Mining locations", annotations=READ_ONLY)
    def mining_locations(
        mineral: Annotated[str, Field(min_length=2)],
        system: Annotated[str | None, Field(description="Optional: Stanton, Pyro, Nyx.")] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 15,
    ) -> dict:
        """Where a mineral is found, most frequent first: place, system,
        place type, method (ship, ROC, FPS), share of deposits and
        concentration range. Without a name match, lists the minerals."""
        return guarded(forge.mining_locations, mineral, system, limit)

    @mcp.tool(title="List minerals", annotations=READ_ONLY)
    def list_minerals() -> dict:
        """All minerals with their number of locations, systems, and whether
        they are crafting ingredients."""
        return guarded(forge.list_minerals)

    @mcp.tool(title="Identify a scan signature", annotations=READ_ONLY)
    def identify_signature(
        value: Annotated[int, Field(ge=1, le=30000, description="Signature value read on the scanner.")],
    ) -> dict:
        """What a scanner signature can be: exact multiples of a mineral's
        ship signature (within its cluster size), ROC/FPS deposits or salvage
        panels, with the number of rocks or items."""
        return guarded(forge.identify_signature, value)

    @mcp.tool(title="Refinery yields", annotations=READ_ONLY)
    def refinery_yields(
        material: Annotated[str, Field(min_length=2, description="Refined material, e.g. 'Quantainium'.")],
    ) -> dict:
        """Yield bonus or malus of every refinery for a material, best first."""
        return guarded(forge.refinery_yields, material)

    # Trading ----------------------------------------------------------------

    @mcp.tool(title="Terminal sell prices", annotations=READ_ONLY)
    def terminal_prices(
        mineral: Annotated[str, Field(min_length=2)],
        limit: Annotated[int, Field(ge=1, le=20)] = 5,
    ) -> dict:
        """Best trade terminals buying a mineral (refined and raw forms),
        price per SCU, from UEX, with the update time."""
        return guarded(forge.terminal_prices, mineral, limit)

    @mcp.tool(title="Search marketplace listings", annotations=READ_ONLY)
    def marketplace_search(
        item: Annotated[str | None, Field(description=(
            "Item name, e.g. 'Stileron', 'Quantainium', 'Pembroke helmet'. Leave empty to "
            "search recent listings by text/category."))] = None,
        id_items: Annotated[list[int] | None, Field(description=(
            "Exact UEX item ids (from marketplace_find_items or an 'ambiguous' answer). Up to 6."))] = None,
        operation: Annotated[Literal["sell", "buy"], Field(description=(
            "'sell': players selling (you want to buy). 'buy': players looking to buy."))] = "sell",
        quality_min: Annotated[int | None, Field(ge=0, le=1000, description=(
            "Minimum quality 0-1000; listings of unknown quality are excluded when set."))] = None,
        quality_max: Annotated[int | None, Field(ge=0, le=1000)] = None,
        max_age_days: Annotated[int | None, Field(ge=0, le=365, description=(
            "Posted within this many days; 0 or empty: any age. 'Recent' usually means 7 to 14."))] = 30,
        price_max: Annotated[float | None, Field(ge=0, description="Maximum price in the listing's own unit.")] = None,
        system: Annotated[str | None, Field(description="Star system, e.g. 'Stanton', 'Pyro', 'Nyx'.")] = None,
        location: Annotated[str | None, Field(description="Substring of the location.")] = None,
        seller: Annotated[str | None, Field(description="Substring of the seller's username.")] = None,
        text: Annotated[str | None, Field(description="Words that must all appear in the title.")] = None,
        category: Annotated[str | None, Field(description="UEX category or section, e.g. 'Helmets'.")] = None,
        sort: Annotated[Literal["quality", "recent", "price"], Field(description=(
            "quality: best first; recent: newest first; price: cheapest first."))] = "quality",
        one_per_seller: bool = True,
        include_unknown_quality: bool = True,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict:
        """UEX player marketplace listings with combined filters, ranked by
        quality, recency or price, one per seller, each with a direct link.
        Qualities read from titles are marked '~', defaults '500?'."""
        return guarded(market.search, item=item, id_items=id_items, text=text,
                       category=category, operation=operation, quality_min=quality_min,
                       quality_max=quality_max, max_age_days=max_age_days,
                       price_max=price_max, system=system, location=location, seller=seller,
                       sort=sort, one_per_seller=one_per_seller,
                       include_unknown_quality=include_unknown_quality, limit=limit)

    @mcp.tool(title="Find marketplace items", annotations=READ_ONLY)
    def marketplace_find_items(
        query: Annotated[str, Field(min_length=2, description="Part of an item name.")],
        category: Annotated[str | None, Field(description="Optional UEX category or section.")] = None,
        limit: Annotated[int, Field(ge=1, le=30)] = 10,
    ) -> dict:
        """Look up items in the UEX catalog (all items, not only crafting) to
        get exact names and ids for marketplace_search."""
        return guarded(market.find_items, query, category=category, limit=limit)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request):  # noqa: ARG001
        from starlette.responses import JSONResponse
        try:
            st = forge.status()
            return JSONResponse(dict(status="ok", version=__version__,
                                     game_version=st.get("game_version"),
                                     products=st["counts"]["products"]))
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(dict(status="error", detail=str(exc)[:200]), status_code=503)

    return mcp, forge, market


def default_cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "cavalera-forge")


def main(argv=None):
    p = argparse.ArgumentParser(prog="cavalera-forge-mcp", description=__doc__.split("\n")[0])
    p.add_argument("--http", action="store_true", help="serve Streamable HTTP instead of stdio")
    p.add_argument("--host", default=os.environ.get("FORGE_MCP_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("FORGE_MCP_PORT", "8793")))
    p.add_argument("--path", default=os.environ.get("FORGE_MCP_PATH", "/mcp"))
    p.add_argument("--data-dir", default=os.environ.get("FORGE_DATA_DIR"),
                   help="folder holding craft.db and market.db; if unset, they are "
                        "downloaded from the published copy into the cache folder")
    p.add_argument("--cache-dir", default=os.environ.get("FORGE_CACHE_DIR") or default_cache_dir())
    p.add_argument("--allowed-host", action="append", default=None,
                   help="public Host header accepted behind a proxy (repeatable); "
                        "env FORGE_MCP_ALLOWED_HOSTS, comma separated")
    p.add_argument("--oauth-shim", action="store_true",
                   default=os.environ.get("FORGE_MCP_OAUTH_SHIM", "") in ("1", "true", "yes"),
                   help="auto-approving OAuth facade for claude.ai custom connectors")
    p.add_argument("--public-url", default=os.environ.get("FORGE_MCP_PUBLIC_URL"))
    p.add_argument("--version", action="version", version=__version__)
    args = p.parse_args(argv)
    if args.oauth_shim and not args.public_url:
        p.error("--oauth-shim needs --public-url (or FORGE_MCP_PUBLIC_URL)")

    logging.basicConfig(stream=sys.stderr, level=os.environ.get("FORGE_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    data_dir = args.data_dir
    if not data_dir:
        from . import fetch
        data_dir = fetch.ensure(os.path.join(args.cache_dir, "data"))
    mcp, _, market = build_server(data_dir=data_dir, cache_dir=os.path.join(args.cache_dir, "uex"))
    market.catalog.refresh_in_background()

    if not args.http:
        mcp.run("stdio")
        return
    if args.oauth_shim:
        from uex_market import oauth_shim
        redirect_hosts = [h for h in os.environ.get("FORGE_MCP_OAUTH_REDIRECT_HOSTS", "").split(",")
                          if h.strip()] or oauth_shim.DEFAULT_REDIRECT_HOSTS
        oauth_shim.install(mcp, args.public_url, args.path, redirect_hosts)
        log.info("OAuth shim enabled for %s", args.public_url)
    hosts = args.allowed_host or [h.strip() for h in
                                  os.environ.get("FORGE_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts + ["127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=["https://%s" % h for h in hosts] + ["https://claude.ai"],
    )
    mcp.run("streamable-http", host=args.host, port=args.port,
            streamable_http_path=args.path, json_response=True,
            stateless_http=True, transport_security=security)


if __name__ == "__main__":
    main()
