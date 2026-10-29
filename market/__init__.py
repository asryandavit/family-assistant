"""Market watch (docs/briefs/MARKET_WATCH.md): watch items on foreign and Armenian stores,
priced to Yerevan per forwarder x mode. Pure code; numbers are code (CLAUDE.md §2).

    shipping.py   chargeable weight + each forwarder's own price formula
    customs.py    customs estimate (default rule per forwarder, EAEU 2026 as a switch)
    workdays.py   working-day arithmetic and arrival dates (holidays.md)
    tariffs.py    parsers for the forwarders' published tariffs and the CBA rates
    stores.py     stores.md -> which origins/modes each store may use
    pricing.py    one offer -> one quote per forwarder x mode
"""
import os

DIR = os.path.dirname(os.path.abspath(__file__))
