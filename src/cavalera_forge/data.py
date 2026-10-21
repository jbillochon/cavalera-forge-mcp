# -*- coding: utf-8 -*-
"""Read-only queries over the Cavalera Forge databases.

craft.db  crafting recipes, quality effects, missions, mining locations,
          mineable profiles, scan signatures, refinery yields
          (built by the Cavalera Forge pipeline)
market.db best terminal sell prices of minerals (UEX public API)

Same SQL and the same game rules as the Cavalera Forge Discord bot; results
come back as plain dicts with English keys. Every function opens its own
read-only connection, so a database swapped in by the build (os.replace)
is picked up on the next call.
"""
from __future__ import annotations

import contextlib
import difflib
import json
import os
import re
import sqlite3
import unicodedata

DATA_DIR = os.environ.get("FORGE_DATA_DIR", "")

# Scan signature rules, read in the source's SignatureChart code.
# Ship mining: each mineable has its own signature; the largest cluster
# depends on rarity (a legendary rock never comes in more than two).
CLUSTER_MAX = dict(common=6, uncommon=5, rare=4, epic=3, legendary=2)
CLUSTER_DEFAULT = 6
# Generic signatures: they tell what is detected, not which mineral.
GENERIC_SIGNATURES = (
    ("roc", 4000, "ROC / hand mineable deposit"),
    ("fps", 3000, "FPS mineable deposit"),
    ("salvage", 2000, "Salvage wreck panel"),
)
SIGNATURE_MAX = 30000

METHODS = {"Vaisseau": "Ship", "Vaisseau (rare)": "Ship (rare)",
           "ROC / vehicule": "ROC / vehicle", "ROC": "ROC", "FPS": "FPS"}
FORMS = {"raffine": "refined", "brut": "raw"}
QUALIFIERS = ("pure", "pur", "raw", "brut", "brute", "ore", "minerai",
              "mineral", "minerais", "minerals", "refined", "raffine")


_HINT = dict(
    ambiguous="Several products match: pick the one meant (often the base item, the others "
              "being skins) and call again with its product_id.",
    not_found="No product matches: try search_products with a shorter name.",
)


class DataError(RuntimeError):
    pass


# Helpers -------------------------------------------------------------------

def fold(value):
    txt = unicodedata.normalize("NFKD", str(value or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return " ".join(txt.lower().split())


def squash(value):
    return "".join(c for c in fold(value) if c.isalnum())


def clean(text):
    """Drop variant qualifiers: the base knows Carinite, not Carinite (Pure)."""
    words = [w for w in fold(text).replace("(", " ").replace(")", " ").split()
             if w not in QUALIFIERS]
    return " ".join(words) or fold(text)


def closest(text, names, threshold=0.78):
    """Spelling fallback, word by word, mean score (same as the bot)."""
    words = [squash(w) for w in fold(text).split()]
    words = [w for w in words if len(w) >= 3]
    if not words:
        return None
    best, best_score = None, 0.0
    for name in names:
        forms = [squash(name)] + [squash(w) for w in fold(name).split()]
        forms = [f for f in forms if len(f) >= 3]
        if not forms:
            continue
        scores = []
        for w in words:
            s = 0.0
            for f in forms:
                if w in f or f in w:
                    s = max(s, 0.95)
                    continue
                s = max(s, difflib.SequenceMatcher(None, w, f).ratio())
            scores.append(s)
        mean = sum(scores) / len(scores)
        if mean >= threshold and mean > best_score:
            best, best_score = name, mean
    return best


def _path(name, data_dir=None):
    d = data_dir or DATA_DIR
    if not d:
        raise DataError("FORGE_DATA_DIR is not set")
    p = os.path.join(d, name)
    if not os.path.exists(p):
        raise DataError("%s not found in %s" % (name, d))
    return p


def _connect(name, data_dir=None):
    cx = sqlite3.connect("file:%s?mode=ro" % _path(name, data_dir), uri=True, timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


class Forge:
    """All queries, bound to one data directory."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or DATA_DIR

    @contextlib.contextmanager
    def craft(self):
        cx = _connect("craft.db", self.data_dir)
        try:
            yield cx
        finally:
            cx.close()

    @contextlib.contextmanager
    def market(self):
        cx = _connect("market.db", self.data_dir)
        try:
            yield cx
        finally:
            cx.close()

    # Status ----------------------------------------------------------------

    def status(self):
        out = dict()
        with self.craft() as cx:
            meta = dict((r["key"], r["value"]) for r in cx.execute("SELECT key, value FROM meta"))
            out["game_version"] = meta.get("display_version")
            out["game_build"] = meta.get("raw_version")
            out["channel"] = meta.get("channel")
            out["craft_data_built"] = meta.get("built_at")
            out["counts"] = dict(
                products=cx.execute("SELECT COUNT(*) FROM products WHERE name<>'-'").fetchone()[0],
                ingredients=cx.execute("SELECT COUNT(DISTINCT ingredient) FROM slot_options").fetchone()[0],
                minerals=cx.execute("SELECT COUNT(*) FROM minerals").fetchone()[0],
                mining_locations=cx.execute("SELECT COUNT(*) FROM mineral_locations").fetchone()[0],
                missions=cx.execute("SELECT COUNT(*) FROM missions").fetchone()[0],
                refineries=cx.execute("SELECT COUNT(*) FROM refineries").fetchone()[0],
            )
        try:
            with self.market() as cx:
                m = dict((r["key"], r["value"]) for r in cx.execute("SELECT key, value FROM meta"))
            out["terminal_prices_updated"] = m.get("updated_at")
        except (DataError, sqlite3.Error):
            out["terminal_prices_updated"] = None
        return out

    # Products --------------------------------------------------------------

    def search_products(self, query, product_type=None, limit=15):
        key = fold(query)
        sql = ("SELECT id, name, type, subtype, manufacturer FROM products "
               "WHERE name<>'-' AND name_folded LIKE ?")
        args = ["%" + key + "%"]
        if product_type:
            sql += " AND type=?"
            args.append(product_type)
        with self.craft() as cx:
            total = cx.execute(sql.replace("id, name, type, subtype, manufacturer", "COUNT(*)"),
                               args).fetchone()[0]
            rows = cx.execute(sql + " ORDER BY CASE WHEN name_folded LIKE ? THEN 0 ELSE 1 END, "
                              "LENGTH(name), name LIMIT ?", args + [key + "%", limit]).fetchall()
            if not rows:
                names = [r[0] for r in cx.execute("SELECT name FROM products WHERE name<>'-'")]
                near = closest(query, names)
                if near:
                    rows = cx.execute("SELECT id, name, type, subtype, manufacturer FROM products "
                                      "WHERE name=? LIMIT ?", (near, limit)).fetchall()
                    total = len(rows)
        return dict(total=total, products=[self._head(r) for r in rows])

    def product_types(self):
        with self.craft() as cx:
            return [dict(type=r[0], subtypes=r[1].split(","), products=r[2]) for r in cx.execute(
                "SELECT type, GROUP_CONCAT(DISTINCT subtype), COUNT(*) FROM products "
                "WHERE name<>'-' GROUP BY type ORDER BY type")]

    def _resolve_product(self, cx, product=None, product_id=None):
        if product_id:
            row = cx.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
            return ("ok", [row]) if row else ("not_found", [])
        key = fold(product)
        rows = cx.execute("SELECT * FROM products WHERE name<>'-' AND name_folded=?", (key,)).fetchall()
        if rows:
            return "ok", rows[:1]
        rows = cx.execute("SELECT * FROM products WHERE name<>'-' AND name_folded LIKE ? "
                          "ORDER BY LENGTH(name), name LIMIT 11", ("%" + key + "%",)).fetchall()
        if len(rows) == 1:
            return "ok", rows
        if rows:
            # Several products contain the query: often a base item and its
            # skins ("Arrowhead Sniper Rifle", "Arrowhead "Warhawk" ...).
            return "ambiguous", rows[:10]
        names = [r[0] for r in cx.execute("SELECT name FROM products WHERE name<>'-'")]
        near = closest(product, names)
        if near:
            return "ok", cx.execute("SELECT * FROM products WHERE name=? LIMIT 1", (near,)).fetchall()
        return "not_found", []

    @staticmethod
    def _head(row):
        return dict(product_id=row["id"], name=row["name"], type=row["type"],
                    subtype=row["subtype"], manufacturer=row["manufacturer"])

    def _quality_effects(self, cx, slot_id):
        """One entry per property: effect of the ingredient quality on the
        product, summarized by its extreme bounds. Properties where lower
        is better (recoil...) are flipped so a gain never reads as a loss."""
        rows = cx.execute(
            "SELECT m.property_key, m.property_name, m.start_quality, m.end_quality, "
            "m.factor_start, m.factor_end, COALESCE(p.lower_is_better,0) inv, p.category "
            "FROM slot_modifiers m LEFT JOIN properties p ON p.key=m.property_key "
            "WHERE m.slot_id=? ORDER BY m.property_key, m.start_quality", (slot_id,)).fetchall()
        by_prop, order = dict(), []
        for r in rows:
            if r["property_key"] not in by_prop:
                by_prop[r["property_key"]] = []
                order.append(r["property_key"])
            by_prop[r["property_key"]].append(r)
        out = []
        for key in order:
            ranges = by_prop[key]
            low = min(min(r["factor_start"], r["factor_end"]) for r in ranges)
            high = max(max(r["factor_start"], r["factor_end"]) for r in ranges)
            stepped = all(abs(r["factor_start"] - r["factor_end"]) < 0.0001 for r in ranges) \
                and len(ranges) > 1
            item = dict(property=ranges[0]["property_name"], lower_is_better=bool(ranges[0]["inv"]),
                        quality_range=[min(r["start_quality"] for r in ranges),
                                       max(r["end_quality"] for r in ranges)])
            if stepped:
                item["kind"] = "absolute steps"
                item["from"], item["to"] = round(low, 4), round(high, 4)
            else:
                # Read the actual ends instead of assuming a direction: the
                # factor at the lowest quality of the first range, and at the
                # highest quality of the last one.
                first = min(ranges, key=lambda r: r["start_quality"])
                last = max(ranges, key=lambda r: r["end_quality"])
                start = round((first["factor_start"] - 1) * 100, 1)
                end = round((last["factor_end"] - 1) * 100, 1)
                item["kind"] = "percent change of the stat"
                item["at_lowest_quality_pct"], item["at_highest_quality_pct"] = start, end
                better = end < start if ranges[0]["inv"] else end > start
                item["higher_quality_is_better"] = better if start != end else None
            out.append(item)
        return out

    def product_recipe(self, product=None, product_id=None):
        with self.craft() as cx:
            status, rows = self._resolve_product(cx, product, product_id)
            if status != "ok":
                return dict(status=status, query=product or product_id,
                            candidates=[self._head(r) for r in rows],
                            hint=_HINT.get(status))
            head = rows[0]
            recipes = []
            for tier in cx.execute("SELECT * FROM tiers WHERE product_id=? ORDER BY tier_index",
                                   (head["id"],)):
                slots = []
                for s in cx.execute(
                        "SELECT s.id sid, s.name slot, o.ingredient, o.quantity, o.min_quality "
                        "FROM slots s JOIN slot_options o ON o.slot_id=s.id "
                        "WHERE s.tier_id=? ORDER BY s.position", (tier["id"],)):
                    slots.append(dict(slot=s["slot"], ingredient=s["ingredient"],
                                      quantity=s["quantity"], min_quality=s["min_quality"],
                                      quality_effects=self._quality_effects(cx, s["sid"])))
                recipes.append(dict(recipe=tier["tier_index"] + 1,
                                    craft_seconds=tier["craft_seconds"], slots=slots))
            missions = cx.execute("SELECT COUNT(DISTINCT mission_id) FROM mission_rewards "
                                  "WHERE product_id=?", (head["id"],)).fetchone()[0]
        out = dict(status="ok", product=self._head(head), recipes=recipes,
                   rewarded_by_missions=missions)
        if not recipes:
            out["note"] = "No crafting recipe for this product in the game data."
        return out

    def product_missions(self, product=None, product_id=None, limit=15):
        with self.craft() as cx:
            status, rows = self._resolve_product(cx, product, product_id)
            if status != "ok":
                return dict(status=status, query=product or product_id,
                            candidates=[self._head(r) for r in rows],
                            hint=_HINT.get(status))
            head = rows[0]
            total = cx.execute("SELECT COUNT(DISTINCT mission_id) FROM mission_rewards "
                               "WHERE product_id=?", (head["id"],)).fetchone()[0]
            missions = []
            for r in cx.execute(
                    "SELECT m.title, m.mission_type, m.faction, m.reward_uec, m.min_standing, "
                    "m.systems, m.once_only, MAX(r.chance) chance FROM mission_rewards r "
                    "JOIN missions m ON m.id=r.mission_id WHERE r.product_id=? "
                    "GROUP BY m.id ORDER BY m.reward_uec DESC LIMIT ?", (head["id"], limit)):
                missions.append(dict(title=r["title"], type=r["mission_type"], faction=r["faction"],
                                     reward_auec=r["reward_uec"], min_standing=r["min_standing"],
                                     systems=json.loads(r["systems"] or "[]"),
                                     once_only=bool(r["once_only"]),
                                     drop_chance=r["chance"]))
        return dict(status="ok", product=self._head(head), total_missions=total, missions=missions)

    # Ingredients -----------------------------------------------------------

    def _resolve_ingredient(self, cx, ingredient):
        names = [r[0] for r in cx.execute("SELECT DISTINCT ingredient FROM slot_options")]
        key = fold(clean(ingredient))
        exact = [n for n in names if fold(n) == key]
        if exact:
            return exact[0]
        part = [n for n in names if key and key in fold(n)]
        if len(part) == 1:
            return part[0]
        return closest(ingredient, names)

    def ingredient_uses(self, ingredient, product_type=None, limit=40):
        with self.craft() as cx:
            name = self._resolve_ingredient(cx, ingredient)
            if not name:
                return dict(status="not_found", query=ingredient,
                            ingredients=self.list_ingredients()["ingredients"])
            by_type = [dict(type=r[0], products=r[1]) for r in cx.execute(
                "SELECT p.type, COUNT(DISTINCT p.id) FROM slot_options o "
                "JOIN slots s ON s.id=o.slot_id JOIN tiers t ON t.id=s.tier_id "
                "JOIN products p ON p.id=t.product_id WHERE o.ingredient=? AND p.name<>'-' "
                "GROUP BY p.type ORDER BY 2 DESC", (name,))]
            sql = ("SELECT p.id, p.name, p.type, p.subtype, MIN(x.q) mn, MAX(x.q) mx FROM ("
                   "SELECT t.product_id pid, SUM(o.quantity) q FROM slot_options o "
                   "JOIN slots s ON s.id=o.slot_id JOIN tiers t ON t.id=s.tier_id "
                   "WHERE o.ingredient=? GROUP BY t.id) x "
                   "JOIN products p ON p.id=x.pid WHERE p.name<>'-'")
            args = [name]
            if product_type:
                sql += " AND p.type=?"
                args.append(product_type)
            rows = cx.execute(sql + " GROUP BY p.id ORDER BY p.type, p.subtype, p.name",
                              args).fetchall()
        products = [dict(product_id=r["id"], name=r["name"], type=r["type"], subtype=r["subtype"],
                         quantity=r["mn"] if r["mn"] == r["mx"] else [r["mn"], r["mx"]])
                    for r in rows]
        out = dict(status="ok", ingredient=name, total_products=sum(t["products"] for t in by_type),
                   by_type=by_type, products=products[:limit])
        if len(products) > limit:
            out["truncated"] = "%d more products; filter with product_type" % (len(products) - limit)
        return out

    def list_ingredients(self):
        with self.craft() as cx:
            rows = cx.execute(
                "SELECT o.ingredient, COUNT(DISTINCT t.product_id) n FROM slot_options o "
                "JOIN slots s ON s.id=o.slot_id JOIN tiers t ON t.id=s.tier_id "
                "GROUP BY o.ingredient ORDER BY n DESC").fetchall()
        return dict(ingredients=[dict(name=r[0], products=r[1]) for r in rows])

    def craftable_from(self, ingredients, product_type=None, limit=25):
        with self.craft() as cx:
            names = [self._resolve_ingredient(cx, i) for i in ingredients or []]
            names = sorted(set(n for n in names if n))
            if not names:
                return dict(status="not_found", query=ingredients)
            holes = ",".join("?" * len(names))
            sql = ("SELECT p.id, p.name, p.type, p.subtype, t.id tid, "
                   "COUNT(DISTINCT s.id) slots_total, "
                   "COUNT(DISTINCT CASE WHEN o.ingredient IN (%s) THEN s.id END) slots_covered "
                   "FROM tiers t JOIN products p ON p.id=t.product_id "
                   "JOIN slots s ON s.tier_id=t.id JOIN slot_options o ON o.slot_id=s.id "
                   "WHERE p.name<>'-'" % holes)
            args = list(names)
            if product_type:
                sql += " AND p.type=?"
                args.append(product_type)
            sql += " GROUP BY t.id HAVING slots_covered>0"
            rows = cx.execute(sql, args).fetchall()
        best = dict()
        for r in rows:
            k = r["id"]
            if k not in best or r["slots_covered"] * best[k]["slots_total"] > \
                    best[k]["slots_covered"] * r["slots_total"]:
                best[k] = dict(r)
        ranked = sorted(best.values(), key=lambda r: (r["slots_covered"] < r["slots_total"],
                                                      -r["slots_covered"] / r["slots_total"],
                                                      r["slots_total"] - r["slots_covered"], r["name"]))
        full = sum(1 for r in ranked if r["slots_covered"] == r["slots_total"])
        return dict(status="ok", ingredients=names, fully_craftable=full,
                    products=[dict(product_id=r["id"], name=r["name"], type=r["type"],
                                   subtype=r["subtype"],
                                   complete=r["slots_covered"] == r["slots_total"],
                                   slots_covered=r["slots_covered"],
                                   slots_total=r["slots_total"]) for r in ranked[:limit]])

    # Minerals --------------------------------------------------------------

    def list_minerals(self):
        with self.craft() as cx:
            rows = cx.execute(
                "SELECT m.name, m.is_ingredient, COUNT(l.id) n, "
                "GROUP_CONCAT(DISTINCT l.system) systems FROM minerals m "
                "LEFT JOIN mineral_locations l ON l.mineral=m.name GROUP BY m.name ORDER BY m.name")
            return dict(minerals=[dict(name=r["name"], crafting_ingredient=bool(r["is_ingredient"]),
                                       locations=r["n"],
                                       systems=sorted((r["systems"] or "").split(",")) if r["systems"] else [])
                                  for r in rows])

    def _resolve_mineral(self, cx, mineral):
        """Name under which mining LOCATIONS are stored. The material bridge
        works both ways: 'Ice (Raw)' yields 'Pressurized Ice'."""
        names = [r[0] for r in cx.execute("SELECT name FROM minerals")]
        key = fold(clean(mineral))
        exact = [n for n in names if fold(n) == key]
        name = exact[0] if exact else None
        if not name:
            row = cx.execute("SELECT name FROM mineables WHERE name_folded=? OR LOWER(material)=? "
                             "LIMIT 1", (fold(mineral), key)).fetchone()
            if row:
                base = re.sub(r"\s*\((?:Ore|Raw|Pure)\)\s*$", "", row[0])
                if base in names:
                    name = base
        if not name:
            name = closest(mineral, names + [r[0] for r in cx.execute(
                "SELECT material FROM mineables WHERE material IS NOT NULL")])
            if name and name not in names:
                row = cx.execute("SELECT name FROM mineables WHERE material=? LIMIT 1",
                                 (name,)).fetchone()
                base = re.sub(r"\s*\((?:Ore|Raw|Pure)\)\s*$", "", row[0]) if row else name
                name = base if base in names else name
        return name

    def _mineable(self, cx, mineral):
        row = cx.execute("SELECT * FROM mineables WHERE material=? LIMIT 1", (mineral,)).fetchone()
        if row is None:
            row = cx.execute("SELECT * FROM mineables WHERE name_folded=? LIMIT 1",
                             (fold(mineral),)).fetchone()
        if row is None:
            row = cx.execute("SELECT * FROM mineables WHERE name_folded LIKE ? LIMIT 1",
                             (fold(mineral) + " (%",)).fetchone()
        return row

    @staticmethod
    def _profile(row):
        def read(value, steps):
            for bound, word in steps:
                if value is not None and value <= bound:
                    return word
            return steps[-1][1]
        return dict(
            resistance=row["resistance"],
            resistance_reading=read(row["resistance"], [(0.0, "easy"), (0.5, "medium"),
                                                        (0.8, "hard"), (99, "very hard")]),
            instability=row["instability"],
            instability_reading=read(row["instability"], [(1, "no risk"), (400, "low"),
                                                          (800, "high"),
                                                          (9999, "explodes at the slightest excess")]),
            optimal_window_mid=row["window_mid"],
            optimal_window_thinness=row["window_thin"],
            optimal_window_reading=read(row["window_thin"], [(0.8, "wide"), (1.6, "medium"),
                                                             (99, "narrow")]),
            optimal_window_random=row["window_random"],
            explosion_multiplier=row["explosion"],
            density=row["density"],
            cluster_factor=row["cluster"],
            note="Readings are an interpretation of the raw numbers, calibrated across all mineables.",
        )

    def mining_locations(self, mineral, system=None, limit=15):
        with self.craft() as cx:
            name = self._resolve_mineral(cx, mineral)
            if not name:
                return dict(status="not_found", query=mineral,
                            minerals=[m["name"] for m in self.list_minerals()["minerals"]])
            sql = ("SELECT place, system, place_type, method, pct_deposits, conc_min, conc_max "
                   "FROM mineral_locations WHERE mineral=?")
            args = [name]
            if system:
                sql += " AND LOWER(system)=?"
                args.append(system.lower())
            rows = cx.execute(sql + " ORDER BY pct_deposits DESC", args).fetchall()
        return dict(status="ok", mineral=name, total_locations=len(rows),
                    locations=[dict(place=r["place"], system=r["system"], place_type=r["place_type"],
                                    method=METHODS.get(r["method"], r["method"]),
                                    share_of_deposits_pct=r["pct_deposits"],
                                    concentration_pct=[r["conc_min"], r["conc_max"]])
                               for r in rows[:limit]],
                    note="share_of_deposits_pct: how often this mineral appears in the deposits of "
                         "that place; concentration_pct: its share inside a rock.")

    def refinery_yields(self, material):
        with self.craft() as cx:
            mats = [r[0] for r in cx.execute("SELECT DISTINCT material FROM refinery_yields")]
            key = fold(clean(material))
            name = next((m for m in mats if fold(m) == key), None) or closest(material, mats)
            if not name:
                alt = self._resolve_mineral(cx, material)
                name = alt if alt in mats else None
            if not name:
                return dict(status="not_found", query=material, materials=sorted(mats))
            rows = cx.execute("SELECT r.name, r.system, y.value FROM refineries r "
                              "JOIN refinery_yields y ON y.profile_id=r.profile_id "
                              "WHERE y.material=? ORDER BY y.value DESC, r.name", (name,)).fetchall()
            total = cx.execute("SELECT COUNT(*) FROM refineries").fetchone()[0]
        out = dict(status="ok", material=name, refineries_with_modifier=len(rows),
                   refineries_total=total,
                   yields=[dict(refinery=r["name"], system=r["system"], yield_bonus_pct=r["value"])
                           for r in rows],
                   note="Yield bonus or malus applied by each refinery to this material; "
                        "refineries not listed apply none.")
        if rows:
            out["spread_pct"] = round(rows[0]["value"] - rows[-1]["value"], 1)
        return out

    def terminal_prices(self, mineral, limit=5):
        try:
            ctx = self.market()
            cx = ctx.__enter__()
        except DataError as exc:
            return dict(status="unavailable", detail=str(exc))
        try:
            bases = [r[0] for r in cx.execute("SELECT DISTINCT base FROM commodities")]
            key = fold(clean(mineral))
            base = next((b for b in bases if fold(b) == key), None) or closest(mineral, bases)
            if not base:
                return dict(status="not_found", query=mineral, commodities=sorted(bases))
            forms = []
            for f in cx.execute("SELECT * FROM commodities WHERE base=? ORDER BY form DESC", (base,)):
                buyers = cx.execute("SELECT terminal, system, price_sell FROM prices "
                                    "WHERE id_commodity=? ORDER BY price_sell DESC LIMIT ?",
                                    (f["id"], limit)).fetchall()
                forms.append(dict(commodity=f["name"], form=FORMS.get(f["form"], f["form"]),
                                  average_price=f["price_avg"],
                                  best_buyers=[dict(terminal=b["terminal"], system=b["system"],
                                                    price_per_scu=b["price_sell"]) for b in buyers]))
            meta = dict((r["key"], r["value"]) for r in cx.execute("SELECT key, value FROM meta"))
        finally:
            ctx.__exit__(None, None, None)
        return dict(status="ok", mineral=base, forms=forms, unit="aUEC per SCU",
                    updated=meta.get("updated_at"), source="UEX Corp (uexcorp.space), terminal sell prices")

    def mineral_info(self, mineral, locations=8):
        """Everything about one mineral: where, how, signatures, profile,
        quality bands, refining, terminal prices."""
        with self.craft() as cx:
            name = self._resolve_mineral(cx, mineral)
            row = self._mineable(cx, mineral) or (self._mineable(cx, name) if name else None)
            if not name and row is None:
                return dict(status="not_found", query=mineral,
                            minerals=[m["name"] for m in self.list_minerals()["minerals"]])
            sigs = []
            if row is not None:
                sigs = [dict(method=METHODS.get(s["method"], s["method"]), signature_per_rock=s["value"])
                        for s in cx.execute("SELECT method, value FROM signatures WHERE mineable=? "
                                            "ORDER BY method", (row["name"],))]
            is_ingredient = cx.execute("SELECT 1 FROM slot_options WHERE ingredient=? LIMIT 1",
                                       (name or (row["material"] if row else ""),)).fetchone()
        out = dict(status="ok", mineral=name or row["material"])
        if name:
            loc = self.mining_locations(name, limit=locations)
            out["total_locations"] = loc["total_locations"]
            out["top_locations"] = loc["locations"]
        if row is not None:
            out["mineable"] = dict(name=row["name"], material=row["material"], rarity=row["rarity"],
                                   max_rocks_per_ship_cluster=CLUSTER_MAX.get(row["rarity"] or "",
                                                                              CLUSTER_DEFAULT))
            out["scan_signatures"] = sigs
            out["extraction_profile"] = self._profile(row)
            bands = json.loads(row["quality_bands"] or "[]")
            if bands:
                out["quality_bands"] = bands
                out["quality_bands_note"] = "Quality thresholds observed for this mineable."
        out["crafting_ingredient"] = bool(is_ingredient)
        ref = self.refinery_yields(out["mineral"])
        if ref.get("status") == "ok":
            out["refining"] = dict(best=ref["yields"][:3], worst=ref["yields"][-3:] if len(ref["yields"]) > 3 else [],
                                   refineries_with_modifier=ref["refineries_with_modifier"])
        prices = self.terminal_prices(out["mineral"], limit=3)
        if prices.get("status") == "ok":
            out["terminal_prices"] = dict(forms=prices["forms"], unit=prices["unit"],
                                          updated=prices["updated"])
        return out

    def identify_signature(self, value):
        """Exact matches for a scan signature read in game. The displayed
        value is the unit signature times the number of detected items, so
        only exact multiples count. Several families can share a value:
        12000 is three ROC deposits, four FPS deposits or six wreck panels."""
        try:
            value = int(value)
        except (TypeError, ValueError):
            return dict(status="invalid", detail="value must be an integer")
        if value <= 0 or value > SIGNATURE_MAX:
            return dict(status="invalid", detail="signatures range from 1 to %d" % SIGNATURE_MAX)
        matches = []
        with self.craft() as cx:
            for r in cx.execute(
                    "SELECT s.value, m.name, m.material, m.rarity FROM signatures s "
                    "JOIN mineables m ON m.name=s.mineable "
                    "WHERE s.method='Vaisseau' AND ? % s.value = 0", (value,)):
                count = value // r["value"]
                cap = CLUSTER_MAX.get(r["rarity"] or "", CLUSTER_DEFAULT)
                if 1 <= count <= cap:
                    matches.append(dict(family="ship mining", mineral=r["material"] or r["name"],
                                        mineable=r["name"], rarity=r["rarity"],
                                        unit_signature=r["value"], count=count))
        for family, sig, label in GENERIC_SIGNATURES:
            if value % sig == 0:
                matches.append(dict(family=label, unit_signature=sig, count=value // sig))
        matches.sort(key=lambda m: (m["family"] != "ship mining", m["count"]))
        out = dict(status="ok" if matches else "no_match", value=value, matches=matches)
        if not matches:
            out["hint"] = ("No exact multiple. Check the value read in game; partially "
                           "mined rocks and overlapping clusters do not add up exactly.")
        return out
