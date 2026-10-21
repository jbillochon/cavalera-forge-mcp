# cavalera-forge-mcp

Star Citizen crafting, mining and trading for Claude and any MCP client.
Everything the [Cavalera Forge](https://cavalera.news/discord) Discord bot
answers, as MCP tools:

> *I want to craft the Arrowhead: what does it need, where do I mine it,
> and who sells the missing ingredient above quality 800?*

| Area | Tools |
|---|---|
| Crafting | `product_recipe` (ingredients, quantities, minimum quality, effect of ingredient quality on each stat), `search_products`, `ingredient_uses`, `craftable_from`, `product_missions` |
| Mining | `mineral_info` (one-stop card), `mining_locations`, `list_minerals`, `identify_signature`, `refinery_yields` |
| Trading | `terminal_prices` (best terminals), `marketplace_search` and `marketplace_find_items` (UEX player listings, combined filters) |
| Status | `data_status` (game version, data freshness) |

Read-only, public data, no account needed. Prices and player listings
come from the [UEX marketplace](https://uexcorp.space/marketplace).
The marketplace part is
[uex-market-mcp](https://github.com/jbillochon/uex-market-mcp).

## Use it

**Hosted instance** (free, public, rate limited): `https://forge.cavalera.news/mcp`

- Claude web / desktop / mobile: *Settings > Connectors > Add custom connector*, paste the URL, then *Connect*.
- Claude Code: `claude mcp add --transport http cavalera-forge https://forge.cavalera.news/mcp`

**Local** (needs [uv](https://docs.astral.sh/uv/)):

```json
{
  "mcpServers": {
    "cavalera-forge": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/jbillochon/cavalera-forge-mcp", "cavalera-forge-mcp"]
    }
  }
}
```

The local server downloads the published databases
(`https://forge.cavalera.news/data/craft.db` and `market.db`) once a day,
and calls UEX directly for the marketplace.

**Skill**: `skill/cavalera-forge/SKILL.md` tells Claude which tool answers
which question and how to read the results. Zip the folder and add it in
Claude (*Settings > Capabilities > Skills*), or copy it to
`~/.claude/skills/` for Claude Code.

## Data

- `craft.db` is built by the Cavalera Forge pipeline from Star Citizen
  game data: 1 600+ products, recipes and quality modifiers, 670 missions,
  mining locations, mineable profiles, scan signatures, refinery yields.
  `data_status` gives the game version it matches.
- `market.db` holds terminal sell prices from UEX, refreshed hourly.

## Self-hosting over HTTP

```bash
pip install git+https://github.com/jbillochon/cavalera-forge-mcp
FORGE_DATA_DIR=/path/to/data FORGE_MCP_ALLOWED_HOSTS=forge.example.org \
  cavalera-forge-mcp --http --port 8793
```

| Variable | Default | |
|---|---|---|
| `FORGE_DATA_DIR` | | folder with craft.db and market.db; unset: download the published copy |
| `FORGE_DATA_URL` | `https://forge.cavalera.news/data` | where to download from |
| `FORGE_CACHE_DIR` | `~/.cache/cavalera-forge` | downloads and UEX catalog cache |
| `FORGE_MCP_ALLOWED_HOSTS` | | public host names accepted (DNS rebinding protection) |
| `FORGE_MCP_OAUTH_SHIM` / `FORGE_MCP_PUBLIC_URL` | off | auto-approving OAuth facade for claude.ai custom connectors (see uex-market-mcp) |
| `UEX_MAX_CALLS_PER_MIN` | `40` | outgoing UEX budget |

`deploy/` has the systemd unit and the nginx configuration of the hosted
instance.

```bash
python -m unittest discover -s tests
```

Not affiliated with Cloud Imperium Games or UEX Corp. Trades
between players happen at their own risk.

MIT License.
