---
name: cavalera-forge
description: Star Citizen crafting, mining and trading assistant using the Cavalera Forge connector - recipes and quality effects, ingredients, missions, mining locations, scan signatures, refineries, terminal prices and UEX player listings. Use for any Star Citizen craft, mining, refining or marketplace question.
---

# Cavalera Forge

This skill drives the `cavalera-forge` MCP connector. Its tools hold the
game data and the market data (UEX). If they are not available, tell
the user to add the connector (see "Setup") instead of answering from
memory: recipes, locations and prices change with every game patch.

## Rules

- Every number comes from a tool. Never estimate a quantity, a quality, a
  location share, a signature or a price.
- Item names stay in English as in game; answer in the user's language.
- When an answer depends on the patch, give the game version from
  `data_status` (once per conversation is enough).
- `status: "ambiguous"` returns candidates: pick the obvious one, otherwise
  ask, then call again with the exact id. `not_found` often lists valid
  names: use them rather than guessing.

## Which tool

| Question | Tool |
|---|---|
| How do I craft X / what does X need | `product_recipe` (then `mineral_info` per ingredient if they ask where to get them) |
| Which products exist for... | `search_products` (`list_types=true` for the types) |
| What can I make with A and B | `craftable_from` |
| What uses ingredient X | `ingredient_uses` |
| Which missions give X | `product_missions` |
| Everything about a mineral | `mineral_info` |
| Where to mine X in a system | `mining_locations` with `system` |
| My scanner shows N | `identify_signature` |
| Where to refine X | `refinery_yields` |
| Where to sell X at a terminal | `terminal_prices` |
| Who sells / buys X between players | `marketplace_search` (`marketplace_find_items` for non-crafting items) |

Chain tools for planning questions. Example, "I want to craft the
Arrowhead, what do I need and where do I get it": `product_recipe` ->
`mineral_info` for each mineral ingredient -> `marketplace_search` with
`quality_min` set to the recipe's minimum quality for what the user lacks.

## Reading the results

- Recipes: `min_quality` is the minimum ingredient quality accepted.
  `quality_effects` give the stat change in percent at the lowest and the
  highest ingredient quality; `higher_quality_is_better` already accounts
  for stats where lower is better (recoil, spread). Several recipes means
  alternative recipes.
- Mining: `share_of_deposits_pct` is how often the mineral appears among
  that place's deposits, `concentration_pct` its share inside a rock.
  Extraction readings (easy/hard, risk, window width) are an
  interpretation of raw numbers: present them as such.
- Signatures: a value is a unit signature times a count; several families
  can share a value (12000 = 3 ROC deposits = 4 FPS deposits = 6 salvage
  panels). Give all matches, most likely first, with the counts.
- Refineries: `yield_bonus_pct` per refinery; unlisted refineries apply no
  modifier.
- Terminal prices: aUEC per SCU, with the update time; refined and raw
  forms differ a lot.
- Marketplace: always give the listing URL. Quality labels: `974` declared,
  `~886` read from the title, `517-747` several qualities in one listing,
  `500?` unconfirmed default, `?` unknown. Quote price with its unit, never
  convert. End with a reminder that trades are between players, at their
  own risk.

## Setup

- Claude (web, desktop, mobile): Settings > Connectors > Add custom
  connector, URL `https://forge.cavalera.news/mcp`, then Connect.
- Claude Code: `claude mcp add --transport http cavalera-forge https://forge.cavalera.news/mcp`
- Local: `uvx --from git+https://github.com/jbillochon/cavalera-forge-mcp cavalera-forge-mcp`
  (downloads the published data once a day).
