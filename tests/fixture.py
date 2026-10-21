# -*- coding: utf-8 -*-
"""Tiny craft.db and market.db with the real schema and a few real-shaped rows."""
import json
import os
import sqlite3
import tempfile

CRAFT = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE products (id INTEGER PRIMARY KEY, source_uuid TEXT, name TEXT NOT NULL,
  name_folded TEXT NOT NULL, gear TEXT NOT NULL, type TEXT NOT NULL, subtype TEXT NOT NULL,
  manufacturer TEXT NOT NULL);
CREATE TABLE tiers (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, tier_index INTEGER NOT NULL,
  craft_seconds INTEGER NOT NULL);
CREATE TABLE slots (id INTEGER PRIMARY KEY, tier_id INTEGER NOT NULL, position INTEGER NOT NULL,
  name TEXT NOT NULL);
CREATE TABLE slot_options (id INTEGER PRIMARY KEY, slot_id INTEGER NOT NULL, ingredient TEXT NOT NULL,
  quantity REAL NOT NULL, min_quality INTEGER NOT NULL);
CREATE TABLE minerals (name TEXT PRIMARY KEY, name_folded TEXT NOT NULL,
  is_ingredient INTEGER NOT NULL DEFAULT 0);
CREATE TABLE mineral_locations (id INTEGER PRIMARY KEY, mineral TEXT NOT NULL, place TEXT NOT NULL,
  system TEXT NOT NULL, place_type TEXT, method TEXT, pct_deposits REAL, conc_min REAL, conc_max REAL);
CREATE TABLE missions (id INTEGER PRIMARY KEY, source_uuid TEXT NOT NULL, debug_name TEXT, title TEXT,
  description TEXT, mission_type TEXT, faction TEXT, systems TEXT, locations TEXT, reward_uec INTEGER,
  min_standing TEXT, once_only INTEGER NOT NULL DEFAULT 0);
CREATE TABLE mission_rewards (id INTEGER PRIMARY KEY, mission_id INTEGER NOT NULL, product_id INTEGER,
  product_name TEXT NOT NULL, pool_name TEXT, chance REAL, trigger TEXT);
CREATE TABLE properties (key TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, unit TEXT,
  lower_is_better INTEGER NOT NULL DEFAULT 0);
CREATE TABLE slot_modifiers (id INTEGER PRIMARY KEY, slot_id INTEGER NOT NULL, property_key TEXT NOT NULL,
  property_name TEXT NOT NULL, start_quality INTEGER NOT NULL, end_quality INTEGER NOT NULL,
  factor_start REAL NOT NULL, factor_end REAL NOT NULL);
CREATE TABLE mineables (name TEXT PRIMARY KEY, name_folded TEXT NOT NULL, material TEXT, rarity TEXT,
  density REAL, instability REAL, resistance REAL, explosion REAL, window_mid REAL, window_random REAL,
  window_thin REAL, cluster REAL, quality_bands TEXT);
CREATE TABLE signatures (id INTEGER PRIMARY KEY, mineable TEXT NOT NULL, method TEXT NOT NULL,
  value INTEGER NOT NULL);
CREATE TABLE refineries (name TEXT PRIMARY KEY, system TEXT, profile_id TEXT NOT NULL);
CREATE TABLE refinery_yields (profile_id TEXT NOT NULL, material TEXT NOT NULL, value REAL NOT NULL,
  PRIMARY KEY (profile_id, material));
"""

MARKET = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE commodities (id INTEGER PRIMARY KEY, name TEXT NOT NULL, base TEXT NOT NULL,
  form TEXT NOT NULL, price_avg REAL, weight_scu REAL, wiki TEXT, slug TEXT);
CREATE TABLE prices (id_commodity INTEGER NOT NULL, terminal TEXT NOT NULL, system TEXT,
  price_sell REAL NOT NULL);
"""


def build():
    d = tempfile.mkdtemp()
    cx = sqlite3.connect(os.path.join(d, "craft.db"))
    cx.executescript(CRAFT)
    cx.executemany("INSERT INTO meta VALUES (?,?)", [
        ("display_version", "4.10"), ("raw_version", "4.10.2-live.1"),
        ("channel", "live"), ("built_at", "2026-10-13T20:13:44+00:00")])
    cx.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?)", [
        (1, "u1", "Pembroke Helmet Arctic", "pembroke helmet arctic", "g", "armour", "helmet", "RSI"),
        (2, "u2", "Pembroke Helmet RSI Edition", "pembroke helmet rsi edition", "g", "armour", "helmet", "RSI"),
        (3, "u3", "Arrowhead Sniper Rifle", "arrowhead sniper rifle", "g", "weapons", "sniper", "Klaus"),
        (4, "u4", "-", "-", "g", "armour", "x", "x"),
    ])
    cx.executemany("INSERT INTO tiers VALUES (?,?,?,?)", [(10, 1, 0, 120), (11, 2, 0, 90), (12, 3, 0, 300)])
    cx.executemany("INSERT INTO slots VALUES (?,?,?,?)", [
        (100, 10, 1, "Shell"), (101, 10, 2, "Visor"), (102, 11, 1, "Shell"),
        (103, 12, 1, "Barrel"), (104, 12, 2, "Stock")])
    cx.executemany("INSERT INTO slot_options VALUES (?,?,?,?,?)", [
        (1, 100, "Stileron", 2, 500), (2, 101, "Taranite", 1, 300),
        (3, 102, "Stileron", 3, 600), (4, 103, "Stileron", 4, 700), (5, 104, "Iron", 2, 0)])
    cx.executemany("INSERT INTO properties VALUES (?,?,?,?,?)", [
        ("armor_dmg", "Damage Reduction", "armor", "%", 0),
        ("weapon_recoil", "Recoil", "weapon", "%", 1)])
    cx.executemany("INSERT INTO slot_modifiers VALUES (?,?,?,?,?,?,?,?)", [
        (1, 100, "armor_dmg", "Damage Reduction", 0, 1000, 0.9, 1.15),
        (2, 103, "weapon_recoil", "Recoil", 0, 1000, 1.2, 0.8)])
    cx.executemany("INSERT INTO minerals VALUES (?,?,?)", [
        ("Stileron", "stileron", 1), ("Taranite", "taranite", 1), ("Ice", "ice", 0)])
    cx.executemany("INSERT INTO mineral_locations VALUES (?,?,?,?,?,?,?,?,?)", [
        (1, "Stileron", "Pyro I", "Pyro", "planet", "Vaisseau", 12.5, 10, 30),
        (2, "Stileron", "Aaron Halo", "Stanton", "belt", "Vaisseau", 4.0, 5, 15),
        (3, "Taranite", "Daymar", "Stanton", "moon", "ROC / vehicule", 8.0, 20, 40),
        (4, "Ice", "Yela", "Stanton", "moon", "Vaisseau", 30.0, 10, 50)])
    cx.executemany("INSERT INTO mineables VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("Stileron (Raw)", "stileron (raw)", "Stileron", "legendary", 2.1, 850, 0.9, 200, 0.5, 0.1,
         1.8, 0.4, json.dumps([300, 550, 800, 950, 1000])),
        ("Ice (Raw)", "ice (raw)", "Pressurized Ice", "common", 1.0, 0, -0.5, 10, 0.5, 0.1,
         0.5, 1.0, "[]"),
    ])
    cx.executemany("INSERT INTO signatures VALUES (?,?,?,?)", [
        (1, "Stileron (Raw)", "Vaisseau", 4100), (2, "Ice (Raw)", "Vaisseau", 3000)])
    cx.executemany("INSERT INTO refineries VALUES (?,?,?)", [
        ("ARC-L1", "Stanton", "p1"), ("Ruin Station", "Pyro", "p2"), ("HUR-L2", "Stanton", "p3")])
    cx.executemany("INSERT INTO refinery_yields VALUES (?,?,?)", [
        ("p1", "Stileron", 5), ("p2", "Stileron", -3), ("p3", "Ice", 2)])
    cx.executemany("INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        (1, "m1", "d", "Bounty A", "", "Mercenary", "Headhunters", '["Pyro"]', "", 70750, "Jr", 0),
        (2, "m2", "d", "Bounty B", "", "Mercenary", "CFP", '["Pyro","Stanton"]', "", 82750, "Jr", 1)])
    cx.executemany("INSERT INTO mission_rewards VALUES (?,?,?,?,?,?,?)", [
        (1, 1, 1, "Pembroke Helmet Arctic", "p", 0.25, "t"),
        (2, 2, 1, "Pembroke Helmet Arctic", "p", 0.1, "t")])
    cx.commit()
    cx.close()
    cx = sqlite3.connect(os.path.join(d, "market.db"))
    cx.executescript(MARKET)
    cx.executemany("INSERT INTO meta VALUES (?,?)", [("updated_at", "2026-10-21T15:27:46+00:00")])
    cx.executemany("INSERT INTO commodities VALUES (?,?,?,?,?,?,?,?)", [
        (1, "Stileron", "Stileron", "raffine", 9000, 1, "", ""),
        (2, "Stileron (Ore)", "Stileron", "brut", 0, 1, "", "")])
    cx.executemany("INSERT INTO prices VALUES (?,?,?,?)", [
        (1, "TDD - Area 18", "Stanton", 10000), (1, "TDD - Orison", "Stanton", 9500)])
    cx.commit()
    cx.close()
    return d
