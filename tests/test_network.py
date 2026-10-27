"""The network, without relays: ids, activity, your profile extras, how a post is read.
Run:  .venv/bin/python -m unittest tests/test_network.py"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["ROOT_HARNESS_HOME"] = tempfile.mkdtemp(prefix="rh-test-")
HOME = Path(os.environ["ROOT_HARNESS_HOME"])

from rootharness import network, conversations   # noqa: E402  (after the home is set)


def _index(days_ago: list[int], titles=None):
    now = int(time.time() * 1000)
    convs = {}
    for i, d in enumerate(days_ago):
        convs[f"c{i}"] = {"id": f"c{i}", "brain": "claude", "title": (titles or [f"Conversation {i}"] * len(days_ago))[i],
                          "created": now - d * 86400000, "updated": now - d * 86400000, "folder": None}
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "index.json").write_text(json.dumps({"folders": [], "conversations": convs}))


class Ids(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(network.slug("Security & CTF"), "security-ctf")
        self.assertEqual(network.slug("  42 Paris!! "), "42-paris")
        self.assertEqual(network.slug(""), "")
        self.assertEqual(len(network.slug("x" * 100)), 40)


class At(unittest.TestCase):
    def test_names(self):
        self.assertEqual(network.at_norm("@Root"), "root")
        self.assertEqual(network.at_norm("root_42"), "root_42")
        for bad in ("ro", "a" * 21, "ro ot", "r!oot", "", "@"):
            self.assertEqual(network.at_norm(bad), "")


class Work(unittest.TestCase):
    def test_images_are_web_links_only(self):
        w = network._work_item({"title": "Root", "image": "https://raw.githubusercontent.com/x/x/main/demos/root.gif", "url": "javascript:alert(1)"})
        self.assertTrue(w["image"].startswith("https://"))
        self.assertEqual(w["url"], "")
        self.assertEqual(network._work_item({"title": "x", "image": "http://insecure/x.gif"})["image"], "")
        p = network.profile_set({"work": [{"title": "Root", "image": "data:image/gif;base64,AAAA"}]})
        self.assertEqual(p["work"][0]["image"], "")


class Activity(unittest.TestCase):
    def test_levels(self):
        _index([])
        self.assertEqual(network.activity()["level"], 0)
        _index([0, 1, 2])
        self.assertEqual(network.activity(), {"days": 3, "level": 1, "label": "active"})
        _index(list(range(0, 9)))
        self.assertEqual(network.activity()["level"], 2)
        _index(list(range(0, 21)))
        self.assertEqual(network.activity()["label"], "actively active")
        _index([40, 50])                      # too old to count
        self.assertEqual(network.activity()["days"], 0)

    def test_same_day_counts_once(self):
        _index([0, 0, 0, 1])
        self.assertEqual(network.activity()["days"], 2)


class Profile(unittest.TestCase):
    def test_bounds_and_choices(self):
        p = network.profile_set({"name": "Vincent", "show": "both", "state": "cherche", "school": "42 Paris", "role": "x" * 200,
                                 "work": [{"kind": "hackathon", "title": "Test", "text": "t", "when": "Oct 2026"}, {"kind": "weird", "title": "p"}, {"title": ""}],
                                 "pinned": ["30009:abc:first-post", "nope"], "communities": ["Security & CTF", "agents", "agents"]})
        self.assertEqual(p["show"], "both")
        self.assertEqual(p["state"], "cherche")
        self.assertEqual(len(p["role"]), 160)
        self.assertEqual([w["kind"] for w in p["work"]], ["hackathon", "project"])     # unknown kind -> project, empty title dropped
        self.assertEqual(p["pinned"], ["30009:abc:first-post"])
        self.assertEqual(p["communities"], ["agents", "security-ctf"])
        p = network.profile_set({"show": "nope", "state": "nope"})
        self.assertEqual((p["show"], p["state"]), ("both", "cherche"))               # bad values change nothing

    def test_work_suggest_from_conversations(self):
        _index([0, 1, 2], ["Notifications on the phone", "salut", "Notifications on the phone"])
        titles = [w["title"] for w in network.work_suggest() if w["kind"] == "progress"]
        self.assertEqual(titles, ["Notifications on the phone"])                      # greetings skipped, duplicates merged


class Posts(unittest.TestCase):
    def test_post_is_read_back(self):
        import nostr_sdk as n
        k = n.Keys.generate()
        ev = n.EventBuilder(n.Kind(1), "Built a thing.\nhttps://media.example/a.jpg").tags([n.Tag.parse(t) for t in [
            ["t", "root-harness"], ["t", "agents"], ["rh-agent", "Claude Agent"], ["imeta", "url https://media.example/a.jpg", "m image/jpeg", "dim 800x600"],
            ["e", "ab" * 32, "wss://relay.damus.io", "root"], ["p", "cd" * 32], ["client", "root-harness"]]]).finalize(k)
        p = network.Network._post_of(None, ev)
        self.assertEqual(p["text"], "Built a thing.")                                  # the link is not shown twice
        self.assertEqual(p["media"], [{"url": "https://media.example/a.jpg", "mime": "image/jpeg", "dim": "800x600"}])
        self.assertEqual((p["community"], p["agent"], p["reply_to"]), ("agents", "Claude Agent", "ab" * 32))
        self.assertTrue(p["from_root_harness"])
        self.assertEqual(p["author"]["hex"], k.public_key().to_hex())

    def test_repost_carries_the_original(self):
        import nostr_sdk as n
        a, b = n.Keys.generate(), n.Keys.generate()
        inner = n.EventBuilder(n.Kind(1), "hello").tags([n.Tag.parse(["t", "root-harness"])]).finalize(a)
        rp = n.EventBuilder(n.Kind(6), inner.as_json()).tags([n.Tag.parse(["e", inner.id().to_hex()]), n.Tag.parse(["p", a.public_key().to_hex()])]).finalize(b)
        p = network.Network._post_of(None, rp)
        self.assertEqual(p["id"], inner.id().to_hex())
        self.assertEqual(p["reposted_by"]["hex"], b.public_key().to_hex())
        bad = n.EventBuilder(n.Kind(6), "{not json").finalize(b)
        self.assertIsNone(network.Network._post_of(None, bad))

    def test_other_kinds_are_ignored(self):
        import nostr_sdk as n
        ev = n.EventBuilder(n.Kind(7), "+").finalize(n.Keys.generate())
        self.assertIsNone(network.Network._post_of(None, ev))


if __name__ == "__main__":
    unittest.main()
