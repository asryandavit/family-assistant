"""/amazon search (docs/briefs/AMAZON_SEARCH.md): Amazon UK, DE and IT searched in the bot's own
browser (scrapers/market.py Session, signed out, read-only), read by a Python parser - the model
never reads a page - and priced to Yerevan with the Market watch maths. The model plans (translates
the query) and phrases the pick's reason; every number is parsed and computed here (CLAUDE.md §2).

File names mirror china/ so the P1b "extract the engine" session can diff them; where code is
copied it says `# same as china/<file>`.

    parse.py     card parser + product-page parser, written against tests/fixtures/amazon/
    trust.py     seller class, rating, reviews, sponsored -> score and a human reason (config)
    pricing.py   offers -> AMD per forwarder x mode (market.pricing.quote), ranking, pick
    validate.py  the model's plan and reason -> clean values, or rejected whole
    runner.py    the two small `claude -p` calls (no browsing tools)
    search.py    one queued job: plan -> questions -> read stores -> price -> answer
    report.py    rich (sendRichMessage) and plain HTML answers, buttons
    queue.py     one browser job at a time, file queue
    bot.py       /amazon command, questions, buttons, /amazon last
"""
import os

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)


def data_dir(root=None):
    d = os.path.join(root or ROOT, ".browser", "amazon_data")
    os.makedirs(d, exist_ok=True)
    return d
