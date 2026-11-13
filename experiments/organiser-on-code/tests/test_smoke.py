# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for organiser-on-code. Hermetic: synthetic data in temporary
directories plus in-memory toys only; nothing reads the standard library,
the network, or the home tree. Under 10 s. Run from the package directory:

  python3 -W error::ResourceWarning -m unittest tests.test_smoke
"""
import io
import json
import math
import os
import random
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import baselines
import build_corpus
import organiser_v1
import run
import tfidf


def unit(vec):
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def write_module(path, prefix, count, extra=""):
    lines = []
    for i in range(count):
        lines.append("def %s_%d(arg):" % (prefix, i))
        lines.append("    value = %d" % i)
        lines.append("    return value + arg")
        lines.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n" + extra)


DUP_TEXT = "def shared_name(arg):\n    value = 7\n    return value + arg\n"


class TokeniserTest(unittest.TestCase):
    def test_camel_snake(self):
        self.assertEqual(tfidf.tokenise("getHTTPResponse_code"),
                         ["get", "http", "response", "code"])

    def test_empty(self):
        self.assertEqual(tfidf.tokenise(""), [])
        self.assertEqual(tfidf.tokenise("123 _"), [])
        self.assertEqual(tfidf.tokenise("v2 _ok"), ["v2", "ok"])


class TfidfTest(unittest.TestCase):
    def test_weights_and_norms(self):
        docs = [("b", "alpha beta"), ("a", "alpha alpha gamma"),
                ("c", "beta gamma delta")]
        model = tfidf.build(docs)
        self.assertEqual(model["vocab"], ["alpha", "beta", "delta", "gamma"])
        ubiqu = tfidf.build([("x", "zz top"), ("y", "zz bottom")])
        # 'zz' is in every doc: idf 0, contributes no weight.
        self.assertEqual(ubiqu["sparse"]["x"].get(ubiqu["vocab"].index("zz")),
                         0.0)
        for vec in model["sparse"].values():
            self.assertAlmostEqual(sum(w * w for w in vec.values()), 1.0)
        # Deterministic and order-free input.
        again = tfidf.build(list(reversed(docs)))
        self.assertEqual(model["sparse"], again["sparse"])
        dense = tfidf.densify(model["sparse"]["a"], len(model["vocab"]))
        self.assertEqual(len(dense), 4)
        self.assertAlmostEqual(sum(w * w for w in dense), 1.0)


class CorpusTest(unittest.TestCase):
    def test_synthetic_tree(self):
        with tempfile.TemporaryDirectory() as root:
            pkgs = ["pkga", "pkgb", "pkgc", "pkgd"]
            for pkg in pkgs:
                os.makedirs(os.path.join(root, pkg))
                open(os.path.join(root, pkg, "__init__.py"),
                     "w", encoding="utf-8").close()
                for m in range(3):
                    write_module(os.path.join(root, pkg, "mod%d.py" % m),
                                 "%s_f%d" % (pkg, m), 16)
            # Exact-duplicate pair across two files: both dropped.
            for pkg in pkgs[:2]:
                with open(os.path.join(root, pkg, "mod0.py"), "a",
                          encoding="utf-8") as handle:
                    handle.write("\n" + DUP_TEXT)
            corpus = build_corpus.build_corpus(root=root, packages=pkgs)
            atoms = corpus["atoms"]
            # 4 pkgs x 3 mods x 16 funcs = 192 raw + 2 planted dups,
            # and the duplicate pair is dropped.
            self.assertEqual(len(atoms), 192)
            self.assertNotIn("shared_name",
                             " ".join(a["text"] for a in atoms))
            self.assertEqual([a["id"] for a in atoms],
                             sorted(a["id"] for a in atoms))
            first = atoms[0]
            self.assertEqual(first["l1"], "pkga")
            self.assertEqual(first["l2"], "pkga.mod0")
            self.assertIsNone(first["l3"])
            self.assertTrue(first["id"].startswith("pkga||pkga.mod0||"))
            texts = [a["text"] for a in atoms]
            self.assertEqual(len(set(texts)), len(texts))
            elig = build_corpus.eligibility(atoms)
            self.assertEqual(elig["packages"], pkgs)
            self.assertEqual(elig["n_eligible_modules"], 12)
            for pkg in pkgs:
                self.assertEqual(len(elig["mods_by_pkg"][pkg]), 3)

    def test_methods_labelled_with_class(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "pkgq"))
            src = ("class Widget:\n"
                   "    def press(self, key):\n"
                   "        code = 1\n"
                   "        return code + key\n"
                   "\n"
                   "    def tap(self, key):\n"
                   "        code = 2\n"
                   "        return code\n")
            with open(os.path.join(root, "pkgq", "mod.py"), "w",
                      encoding="utf-8") as handle:
                handle.write(src)
            atoms = build_corpus.build_corpus(root=root,
                                              packages=["pkgq"])["atoms"]
            self.assertEqual(len(atoms), 2)
            self.assertEqual({a["l3"] for a in atoms}, {"Widget"})
            self.assertTrue(atoms[0]["id"].startswith(
                "pkgq||pkgq.mod||Widget.press||"))


class DrawTest(unittest.TestCase):
    def test_shape_and_determinism(self):
        mods_by_pkg = {p: ["%s.m%d" % (p, m) for m in range(3)]
                       for p in ["a", "b", "c", "d", "e", "f"]}
        atoms_by_mod = {(p, m): ["%s||%s||f%d||%d" % (p, m, i, i)
                                 for i in range(20)]
                        for p in mods_by_pkg for m in mods_by_pkg[p]}
        truth = {i: (i.split("||")[0], i.split("||")[1], None)
                 for ids in atoms_by_mod.values() for i in ids}
        first = run.draw_seed(61, sorted(mods_by_pkg), mods_by_pkg,
                              atoms_by_mod)
        again = run.draw_seed(61, sorted(mods_by_pkg), mods_by_pkg,
                              atoms_by_mod)
        self.assertEqual(first, again)
        self.assertEqual(len(first), 180)
        self.assertEqual(len(set(first)), 180)
        per_mod = {}
        for i in first:
            per_mod[truth[i][1]] = per_mod.get(truth[i][1], 0) + 1
        self.assertEqual(len(per_mod), 12)
        self.assertTrue(all(v == 15 for v in per_mod.values()))
        other = run.draw_seed(62, sorted(mods_by_pkg), mods_by_pkg,
                              atoms_by_mod)
        self.assertNotEqual(first, other)


class OrganiserTest(unittest.TestCase):
    def test_planted_pair_splits_clean(self):
        dim = 8
        u1 = unit([1.0] + [0.0] * (dim - 1))
        u2 = unit([0.0, 1.0] + [0.0] * (dim - 2))

        def once():
            org = organiser_v1.Organiser(dist=organiser_v1.Dist())
            truth = {}
            for k in range(30):
                org.insert("a%d" % k, list(u1))
                truth["a%d" % k] = 0
            for k in range(30):
                org.insert("b%d" % k, list(u2))
                truth["b%d" % k] = 1
            org.level_up()
            ids = sorted(truth)
            labels = [org.atom_o1[a][0] for a in ids]
            return labels, [truth[a] for a in ids], org.cluster_counts()

        labels, truth, counts = once()
        labels2, _, _ = once()
        self.assertEqual(labels, labels2)
        self.assertEqual(counts[1], 2)
        self.assertEqual(baselines.ari(truth, labels), 1.0)
        self.assertEqual(
            baselines.cluster_stats(labels, truth)["purity"], 1.0)

    def test_state_roundtrip(self):
        org = organiser_v1.Organiser(dist=organiser_v1.Dist())
        rng = random.Random("smoke-state")
        for k in range(60):
            org.insert("i%d" % k,
                       unit([rng.gauss(0.0, 1.0) for _ in range(4)]))
        org.level_up()
        clone = organiser_v1.Organiser(dist=organiser_v1.Dist())
        clone.from_state(org.to_state())
        ids = sorted(org.atom_o1)
        self.assertEqual([org.atom_o1[a][0] for a in ids],
                         [clone.atom_o1[a][0] for a in ids])
        self.assertEqual(org.cluster_counts(), clone.cluster_counts())


class BaselinesTest(unittest.TestCase):
    def test_ari_hand_cases(self):
        self.assertEqual(baselines.ari([0, 0, 1, 1], [0, 0, 1, 1]), 1.0)
        self.assertEqual(baselines.ari([0, 0, 0], [0, 0, 0]), 0.0)
        self.assertEqual(baselines.ari([0], [5]), 0.0)
        self.assertAlmostEqual(
            baselines.ari([0, 0, 1, 1], [0, 1, 0, 1]), -0.5)

    def test_purity_and_counts(self):
        stats = baselines.cluster_stats([0, 0, 0, 1, 1, 2],
                                        ["a", "a", "b", "b", "b", "a"])
        self.assertEqual(stats["K"], 3)
        self.assertEqual(stats["median"], 2.0)
        self.assertAlmostEqual(stats["purity"], 5.0 / 6.0)
        self.assertAlmostEqual(stats["share"], 0.5)

    def test_random_partition_shape(self):
        rng = random.Random("smoke-rand")
        labels = baselines.rand_partition(rng, 180, 12)
        self.assertEqual(len(labels), 180)
        self.assertEqual(sorted(set(labels)), list(range(12)))
        self.assertTrue(all(labels.count(c) == 15 for c in range(12)))

    def test_run_random_consumes_pair(self):
        # run_random draws the 4-split first, then the reported 12-split.
        rng = random.Random("b1code-rand-v1-7")
        baselines.rand_partition(rng, 180, 4)
        want = baselines.rand_partition(rng, 180, 12)
        self.assertEqual(run.run_random(7, 180), want)

    def test_kmeans_dense_deterministic(self):
        vecs = [unit([1.0, 0.1 * i, 0.0]) for i in range(6)] + \
               [unit([0.0, 0.1 * i, 1.0]) for i in range(6)]
        first = baselines.kmeans_dense(vecs, 2, "smoke-km")
        again = baselines.kmeans_dense(vecs, 2, "smoke-km")
        self.assertEqual(first, again)
        self.assertEqual(len(set(first)), 2)

    def test_kmeans_sparse_deterministic(self):
        vecs = [{0: 1.0, 1: 0.1 * i} for i in range(6)] + \
               [{2: 1.0, 3: 0.1 * i} for i in range(6)]
        first = baselines.kmeans_sparse(vecs, 2, "smoke-km")
        again = baselines.kmeans_sparse(vecs, 2, "smoke-km")
        self.assertEqual(first, again)
        self.assertEqual(len(set(first)), 2)

    def test_avg_link_tiny(self):
        sim = [[1.0, 0.9, 0.0, 0.0],
               [0.9, 1.0, 0.0, 0.0],
               [0.0, 0.0, 1.0, 0.9],
               [0.0, 0.0, 0.9, 1.0]]
        self.assertEqual(baselines.avg_link(sim, 2), [0, 0, 1, 1])


class VectorsFileTest(unittest.TestCase):
    def test_roundtrip_and_bad_magic(self):
        ids = ["p||p.m||f||1", "p||p.m||g||5", "q||q.n||h||2"]
        labels = {i: (i.split("||")[0], i.split("||")[1], None)
                  for i in ids}
        vecs = [[0.5, -0.5, 0.5, -0.5], [1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0]]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tiny.bin")
            directory = {"format": "orgcode-vec/1", "model": "tiny-test",
                         "revision": "0" * 40, "count": 3, "dim": 4,
                         "ids": ids,
                         "labels": {i: [l[0], l[1]]
                                    for i, l in labels.items()}}
            blob = json.dumps(directory, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            with open(path, "wb") as handle:
                handle.write(b"ORGCODE1")
                handle.write(struct.pack("<III", 3, 4, len(blob)))
                handle.write(blob)
                handle.write(struct.pack("<12f", *[x for v in vecs
                                                  for x in v]))
            data = run.load_vectors_file(path)
            self.assertEqual(data["ids"], ids)
            self.assertEqual(data["dim"], 4)
            for i, v in zip(ids, vecs):
                for got, want in zip(data["vecmap"][i], v):
                    self.assertAlmostEqual(got, want, places=6)
            self.assertEqual(data["truth"][ids[0]][:2], ("p", "p.m"))
            with open(path, "r+b") as handle:
                handle.write(b"BADMAGIC")
            with self.assertRaises(SystemExit):
                run.load_vectors_file(path)


class EndToEndTest(unittest.TestCase):
    def test_mode_b_on_planted_mini_corpus(self):
        rng = random.Random("smoke-mini")
        dim = 8
        pkgs = ["pa", "pb", "pc", "pd"]
        ids = []
        labels = {}
        vecs = {}
        for pkg in pkgs:
            for m in range(3):
                centre = unit([rng.gauss(0.0, 1.0) for _ in range(dim)])
                for a in range(15):
                    atom = "%s||%s.m%d||f%d||%d" % (pkg, pkg, m, a, a)
                    ids.append(atom)
                    labels[atom] = [pkg, "%s.m%d" % (pkg, m)]
                    vecs[atom] = unit([c + rng.gauss(0.0, 0.05)
                                       for c in centre])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mini.bin")
            directory = {"format": "orgcode-vec/1", "model": "tiny-test",
                         "revision": "0" * 40, "count": len(ids), "dim": dim,
                         "ids": sorted(ids), "labels": labels}
            blob = json.dumps(directory, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            order = sorted(ids)
            with open(path, "wb") as handle:
                handle.write(b"ORGCODE1")
                handle.write(struct.pack("<III", len(ids), dim, len(blob)))
                handle.write(blob)
                handle.write(struct.pack("<%df" % (len(ids) * dim),
                                         *[x for i in order
                                           for x in vecs[i]]))

            def capture():
                out, err = io.StringIO(), io.StringIO()
                old_out, old_err = sys.stdout, sys.stderr
                sys.stdout, sys.stderr = out, err
                try:
                    code = run.mode_b(path)
                finally:
                    sys.stdout, sys.stderr = old_out, old_err
                return code, out.getvalue()

            code, text = capture()
            self.assertEqual(code, 0)
            code2, text2 = capture()
            self.assertEqual(text, text2)
        self.assertIn("organiser-on-code", text)
        self.assertIn("mean module ARI over seeds 61,62,63,64,65:", text)
        rows = [ln for ln in text.splitlines()
                if ln.startswith("6")]
        self.assertEqual(len(rows), 5)

    def test_format_table_shape(self):
        rows = [(61, {"org": (0.5, 0.6, 7), "km": (0.4, 0.55),
                      "al": (0.3, 0.5), "rnd": (0.0, 0.2)})]
        text = run.format_table(rows)
        self.assertIn("0.5000", text)
        self.assertIn("organiser 0.500", text)
        self.assertTrue(text.endswith("\n"))
        for line in text.splitlines():
            self.assertEqual(line, line.rstrip())


if __name__ == "__main__":
    unittest.main()
