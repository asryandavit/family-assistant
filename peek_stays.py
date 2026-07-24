"""Preview the data structures inside the discovery captures.

Usage:  python peek_stays.py

Reads .browser/stays_booking.json and stays_airbnb.json, finds the payload
that carries listing data, and prints the field names and a sample record
so we can build parsers without guessing.
"""
import json
import os
import re

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser")


def peek_dict(d, prefix="", depth=0, max_depth=3):
    """Print keys and types up to max_depth."""
    if depth > max_depth or not isinstance(d, dict):
        return
    for k, v in list(d.items())[:25]:
        t = type(v).__name__
        extra = ""
        if isinstance(v, list):
            t = "list[%d]" % len(v)
            if v and isinstance(v[0], dict):
                extra = " keys=" + ",".join(list(v[0].keys())[:8])
        elif isinstance(v, str) and len(v) > 80:
            t = "str[%d]" % len(v)
        elif isinstance(v, dict):
            t = "dict[%d]" % len(v)
        print("  " * depth + "%s%s: %s%s" % (prefix, k, t, extra))
        if isinstance(v, dict):
            peek_dict(v, "", depth + 1, max_depth)


def booking():
    path = os.path.join(OUT, "stays_booking.json")
    if not os.path.exists(path):
        print("no booking discovery file")
        return
    data = json.load(open(path, encoding="utf-8"))

    # Find the largest graphql response
    gql = [c for c in data["network"]
           if "dml/graphql" in c.get("url", "") and c["bytes"] > 50000]
    gql.sort(key=lambda x: -x["bytes"])

    if gql:
        print("=== BOOKING GraphQL (largest, %dB) ===" % gql[0]["bytes"])
        try:
            body = json.loads(gql[0]["preview"])
        except (json.JSONDecodeError, KeyError):
            # preview might be truncated; try to parse what we have
            print("  (preview truncated, showing raw preview)")
            print(gql[0]["preview"][:1500])
            return
        peek_dict(body, max_depth=4)

        # Try to find a property/search result
        for key_path in [
            ["data", "searchQueries", "search", "results"],
            ["data", "searchQueries", "search", "breadcrumbs"],
            ["data", "results"],
        ]:
            node = body
            for k in key_path:
                node = node.get(k) if isinstance(node, dict) else None
                if node is None:
                    break
            if isinstance(node, list) and node:
                print("\n--- First result at %s ---" % ".".join(key_path))
                print(json.dumps(node[0], indent=2, ensure_ascii=False)[:3000])
                break
    else:
        print("no large graphql response found")

    # Also peek at embedded blobs
    emb = [e for e in data.get("embedded", []) if e["bytes"] > 100000]
    if emb:
        print("\n=== BOOKING embedded blob (%dB, id=%s) ===" % (emb[0]["bytes"], emb[0]["id"]))
        try:
            body = json.loads(emb[0]["preview"])
            peek_dict(body, max_depth=3)
        except json.JSONDecodeError:
            print("  (not valid JSON in preview)")
            print(emb[0]["preview"][:500])


def airbnb():
    path = os.path.join(OUT, "stays_airbnb.json")
    if not os.path.exists(path):
        print("no airbnb discovery file")
        return
    data = json.load(open(path, encoding="utf-8"))

    # Airbnb data lives in embedded blobs, not network calls
    emb = [e for e in data.get("embedded", []) if e["bytes"] > 50000]
    emb.sort(key=lambda x: -x["bytes"])

    if emb:
        print("\n=== AIRBNB embedded blob (%dB, id=%s) ===" % (emb[0]["bytes"], emb[0]["id"]))
        try:
            body = json.loads(emb[0]["preview"])
            peek_dict(body, max_depth=4)
        except json.JSONDecodeError:
            print("  (not valid JSON in preview -- showing raw)")
            print(emb[0]["preview"][:2000])
    else:
        print("no large embedded blobs")

    # Also check network for any search API
    search = [c for c in data["network"]
              if "airbnb.com/api" in c.get("url", "") and c["bytes"] > 5000
              and "Consent" not in c["url"] and "client_configs" not in c["url"]]
    if search:
        print("\n=== AIRBNB API responses ===")
        for s in search[:3]:
            print("  %dB  %s" % (s["bytes"], s["url"][:120]))
            try:
                body = json.loads(s["preview"])
                peek_dict(body, max_depth=3)
            except json.JSONDecodeError:
                print("  (preview not parseable)")


if __name__ == "__main__":
    booking()
    airbnb()
