# -*- coding: utf-8 -*-
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fixture import build  # noqa: E402
from cavalera_forge.data import Forge  # noqa: E402

D = build()


class DataTest(unittest.TestCase):
    def setUp(self):
        self.f = Forge(D)

    def test_status(self):
        s = self.f.status()
        self.assertEqual(s["game_version"], "4.10")
        self.assertEqual(s["counts"]["products"], 3)
        self.assertTrue(s["terminal_prices_updated"])

    def test_search_and_typo(self):
        r = self.f.search_products("pembroke")
        self.assertEqual(r["total"], 2)
        r = self.f.search_products("arowhead snipr")
        self.assertEqual(r["products"][0]["name"], "Arrowhead Sniper Rifle")

    def test_recipe_quality_effects(self):
        r = self.f.product_recipe("Arrowhead Sniper Rifle")
        self.assertEqual(r["status"], "ok")
        slot = r["recipes"][0]["slots"][0]
        self.assertEqual((slot["ingredient"], slot["quantity"], slot["min_quality"]), ("Stileron", 4, 700))
        eff = slot["quality_effects"][0]
        # Recoil: +20% at the lowest quality, -20% at the highest; lower is
        # better for recoil, so higher quality is better.
        self.assertEqual(eff["at_lowest_quality_pct"], 20.0)
        self.assertEqual(eff["at_highest_quality_pct"], -20.0)
        self.assertTrue(eff["higher_quality_is_better"])
        r = self.f.product_recipe("Pembroke Helmet Arctic")
        self.assertEqual(r["rewarded_by_missions"], 2)

    def test_recipe_ambiguous(self):
        r = self.f.product_recipe("pembroke")
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(len(r["candidates"]), 2)
        r = self.f.product_recipe(product_id=2)
        self.assertEqual(r["product"]["name"], "Pembroke Helmet RSI Edition")

    def test_missions(self):
        r = self.f.product_missions("Pembroke Helmet Arctic")
        self.assertEqual([m["title"] for m in r["missions"]], ["Bounty B", "Bounty A"])
        self.assertEqual(r["missions"][0]["systems"], ["Pyro", "Stanton"])

    def test_ingredient_uses(self):
        r = self.f.ingredient_uses("stileron (raw)")
        self.assertEqual(r["ingredient"], "Stileron")
        self.assertEqual(r["total_products"], 3)
        self.assertEqual(self.f.ingredient_uses("Stileron", "weapons")["products"][0]["quantity"], 4)

    def test_craftable_from(self):
        r = self.f.craftable_from(["Stileron"])
        names = [(p["name"], p["complete"]) for p in r["products"]]
        self.assertEqual(names[0], ("Pembroke Helmet RSI Edition", True))
        self.assertIn(("Arrowhead Sniper Rifle", False), names)
        r = self.f.craftable_from(["Stileron", "Iron"])
        self.assertIn(("Arrowhead Sniper Rifle", True),
                      [(p["name"], p["complete"]) for p in r["products"]])

    def test_mineral_info(self):
        r = self.f.mineral_info("Stileron")
        self.assertEqual(r["mineral"], "Stileron")
        self.assertEqual(r["top_locations"][0]["place"], "Pyro I")
        self.assertEqual(r["top_locations"][0]["method"], "Ship")
        self.assertEqual(r["scan_signatures"][0]["signature_per_rock"], 4100)
        self.assertEqual(r["mineable"]["max_rocks_per_ship_cluster"], 2)
        self.assertEqual(r["extraction_profile"]["resistance_reading"], "very hard")
        self.assertEqual(r["refining"]["best"][0]["refinery"], "ARC-L1")
        self.assertEqual(r["terminal_prices"]["forms"][0]["best_buyers"][0]["price_per_scu"], 10000)
        self.assertTrue(r["crafting_ingredient"])

    def test_ice_bridge(self):
        r = self.f.mineral_info("Pressurized Ice")
        self.assertEqual(r["mineral"], "Ice")
        self.assertEqual(r["top_locations"][0]["place"], "Yela")

    def test_signature(self):
        r = self.f.identify_signature(8200)
        self.assertEqual(r["matches"][0]["mineral"], "Stileron")
        self.assertEqual(r["matches"][0]["count"], 2)
        r = self.f.identify_signature(12300)  # 3 x Stileron exceeds legendary cap of 2
        self.assertFalse([m for m in r["matches"] if m.get("mineral") == "Stileron"])
        r = self.f.identify_signature(12000)
        fams = sorted(m["family"] for m in r["matches"])
        self.assertIn("ROC / hand mineable deposit", fams)
        self.assertIn("ship mining", fams)  # 4 x Ice 3000
        self.assertEqual(self.f.identify_signature(50000)["status"], "invalid")

    def test_refinery_and_prices(self):
        r = self.f.refinery_yields("stileron")
        self.assertEqual(r["spread_pct"], 8)
        r = self.f.terminal_prices("Stileron (Ore)")
        self.assertEqual([f["form"] for f in r["forms"]], ["refined", "raw"])

    def test_locations_filter(self):
        r = self.f.mining_locations("Stileron", system="stanton")
        self.assertEqual([l["place"] for l in r["locations"]], ["Aaron Halo"])
        self.assertEqual(self.f.mining_locations("zzzz")["status"], "not_found")


class ServerTest(unittest.TestCase):
    def test_tools(self):
        from mcp import Client
        from cavalera_forge.server import build_server
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "uexmcp", "tests"))
        srv, _, _ = build_server(data_dir=D, cache_dir=None)

        async def go():
            async with Client(srv) as c:
                tools = (await c.list_tools()).tools
                r = await c.call_tool("mineral_info", dict(mineral="stileron"))
                return tools, r
        tools, r = asyncio.run(go())
        names = sorted(t.name for t in tools)
        self.assertEqual(names, sorted([
            "data_status", "search_products", "product_recipe", "product_missions",
            "ingredient_uses", "craftable_from", "mineral_info", "mining_locations",
            "list_minerals", "identify_signature", "refinery_yields", "terminal_prices",
            "marketplace_search", "marketplace_find_items"]))
        for t in tools:
            self.assertTrue(t.annotations.read_only_hint)
        self.assertFalse(r.is_error)
        d = r.structured_content or json.loads(r.content[0].text)
        d = d.get("result", d)
        self.assertEqual(d["mineral"], "Stileron")


if __name__ == "__main__":
    unittest.main()
