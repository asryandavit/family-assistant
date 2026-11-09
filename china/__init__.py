"""/china search (docs/briefs/CHINA_SEARCH.md): Pinduoduo, Taobao/Tmall and 1688 searched in a
real browser, results priced to Yerevan with the Market watch maths. The model reads and
classifies; every number is parsed and computed here (CLAUDE.md §2).

    parse.py     page strings -> numbers, seller class, restriction flags, links
    validate.py  the model's JSON per site -> clean result rows (or rejected whole)
    pricing.py   result rows -> ¥ / AMD / USD, shipping per forwarder x mode, customs, ranking
    report.py    rich (sendRichMessage) and plain HTML answers, buttons
    runner.py    one `claude -p --chrome` call per site (Pinduoduo, 1688)
    taobao.py    Taobao read in the bot's own browser profile (.browser/taobao)
    queue.py     one Chrome job at a time, file queue shared by both chats
    bot.py       /china command, questions, buttons, /china last
"""
import os

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)


def data_dir(root=None):
    d = os.path.join(root or ROOT, ".browser", "china_data")
    os.makedirs(d, exist_ok=True)
    return d
