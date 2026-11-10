"""listener.py at startup heals the China queue (decision 104): jobs left waiting with no
worker get one, and a fault there never takes the listener down."""
import unittest
from unittest import mock

import listener
from china import watch

CFG = {"telegram": {"bot_token_env": "TG_TOKEN_T", "chat_id_env": "TG_OWNER_T"}}


class Startup(unittest.TestCase):
    def test_listener_start_heals(self):
        with mock.patch.object(watch, "ensure_worker", return_value=None) as ew:
            listener.china_startup(CFG)
        ew.assert_called_once_with(CFG, listener.ROOT)

    def test_fault_never_takes_the_listener_down(self):
        with mock.patch.object(watch, "ensure_worker", side_effect=RuntimeError("boom")):
            listener.china_startup(CFG)


if __name__ == "__main__":
    unittest.main()
