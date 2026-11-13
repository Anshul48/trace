# SPDX-License-Identifier: Apache-2.0
"""One command, two modes. Default (no arguments) builds identifier-token
TF-IDF vectors from the running interpreter's standard library and scores
the organiser against told-K baselines. With --vectors FILE it loads
precomputed unit vectors keyed by atom id (plus the id list and labels)
and reproduces the measured table without touching the standard library.

Draws: seeds 61-65, 4 packages x 3 modules x 15 atoms = 180 atoms each.
Score: module labels (12 modules per draw); table shows module ARI,
purity and the organiser's group count per seed plus the mean row.
Output is byte-deterministic: no timings, no paths, fixed formatting.
"""
import os
import random
import struct
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baselines
import build_corpus
import organiser_v1
import tfidf

SEEDS = [61, 62, 63, 64, 65]
DRAW_FMT = "b1code-draw-v1-%d"
KM_FMT = "b1code-km-v1-%d-%s-k%d"
RAND_FMT = "b1code-rand-v1-%d"
N_GROUPS_TOLD = 12

VEC_MAGIC = b"ORGCODE1"


def draw_seed(seed, packages, mods_by_pkg, atoms_by_mod):
    rng = random.Random(DRAW_FMT % seed)
    pkgs = rng.sample(sorted(packages), 4)
    atoms = []
    for pkg in pkgs:
        mods = rng.sample(sorted(mods_by_pkg[pkg]), 3)
        for mod in mods:
            pool = sorted(atoms_by_mod[(pkg, mod)])
            atoms.extend(rng.sample(pool, 15))
    rng.shuffle(atoms)
    return atoms


def run_organiser(ids, vecs):
    dist = organiser_v1.Dist()
    org = organiser_v1.Organiser(dist=dist)
    for atom_id, vec in zip(ids, vecs):
        org.insert(atom_id, list(vec))
    org.level_up()
    return [org.atom_o1[a][0] for a in ids], org.cluster_counts()


def run_random(seed, n):
    rng = random.Random(RAND_FMT % seed)
    baselines.rand_partition(rng, n, 4)
    return baselines.rand_partition(rng, n, N_GROUPS_TOLD)


def score_seed_tfidf(seed, ids, truth, sparse, dim):
    truth_mod = [truth[i][1] for i in ids]
    sparse_vecs = [sparse[i] for i in ids]
    dense_vecs = [tfidf.densify(v, dim) for v in sparse_vecs]
    org_labels, counts = run_organiser(ids, dense_vecs)
    km_labels = baselines.kmeans_sparse(
        sparse_vecs, N_GROUPS_TOLD, KM_FMT % (seed, "full_tfidf",
                                             N_GROUPS_TOLD))
    al_labels = baselines.avg_link(
        baselines.sim_matrix_sparse(sparse_vecs), N_GROUPS_TOLD)
    rnd_labels = run_random(seed, len(ids))
    return {
        "org": (baselines.ari(truth_mod, org_labels),
                baselines.cluster_stats(org_labels, truth_mod)["purity"],
                counts[1]),
        "km": (baselines.ari(truth_mod, km_labels),
               baselines.cluster_stats(km_labels, truth_mod)["purity"]),
        "al": (baselines.ari(truth_mod, al_labels),
               baselines.cluster_stats(al_labels, truth_mod)["purity"]),
        "rnd": (baselines.ari(truth_mod, rnd_labels),
                baselines.cluster_stats(rnd_labels, truth_mod)["purity"]),
    }


def score_seed_dense(seed, ids, truth, vecmap):
    truth_mod = [truth[i][1] for i in ids]
    vecs = [vecmap[i] for i in ids]
    org_labels, counts = run_organiser(ids, vecs)
    km_labels = baselines.kmeans_dense(
        vecs, N_GROUPS_TOLD, KM_FMT % (seed, "full_minilm", N_GROUPS_TOLD))
    al_labels = baselines.avg_link(
        baselines.sim_matrix_dense(vecs), N_GROUPS_TOLD)
    rnd_labels = run_random(seed, len(ids))
    return {
        "org": (baselines.ari(truth_mod, org_labels),
                baselines.cluster_stats(org_labels, truth_mod)["purity"],
                counts[1]),
        "km": (baselines.ari(truth_mod, km_labels),
               baselines.cluster_stats(km_labels, truth_mod)["purity"]),
        "al": (baselines.ari(truth_mod, al_labels),
               baselines.cluster_stats(al_labels, truth_mod)["purity"]),
        "rnd": (baselines.ari(truth_mod, rnd_labels),
                baselines.cluster_stats(rnd_labels, truth_mod)["purity"]),
    }


def format_table(rows):
    lines = []
    lines.append("seed  org_ARI  org_pur  org_K  "
                 "km_ARI   km_pur   al_ARI   al_pur   rnd_ARI  rnd_pur")
    for seed, res in rows:
        lines.append("%-4s  %-7s  %-7s  %-5d  %-7s  %-7s  %-7s  %-7s  "
                     "%-7s  %s" % (
                         seed,
                         "%.4f" % res["org"][0], "%.4f" % res["org"][1],
                         res["org"][2],
                         "%.4f" % res["km"][0], "%.4f" % res["km"][1],
                         "%.4f" % res["al"][0], "%.4f" % res["al"][1],
                         "%.4f" % res["rnd"][0], "%.4f" % res["rnd"][1]))
    n = len(rows)
    mean = lambda key, i: sum(r[1][key][i] for r in rows) / n
    mean_k = sum(r[1]["org"][2] for r in rows) / n
    lines.append("%-4s  %-7s  %-7s  %-5.1f  %-7s  %-7s  %-7s  %-7s  "
                 "%-7s  %s" % (
                     "mean",
                     "%.4f" % mean("org", 0), "%.4f" % mean("org", 1),
                     mean_k,
                     "%.4f" % mean("km", 0), "%.4f" % mean("km", 1),
                     "%.4f" % mean("al", 0), "%.4f" % mean("al", 1),
                     "%.4f" % mean("rnd", 0), "%.4f" % mean("rnd", 1)))
    lines.append("mean module ARI over seeds %s: organiser %.3f, "
                 "k-means-12 %.3f, avg-link-12 %.3f, random-12 %.3f" % (
                     ",".join(str(s) for s in SEEDS),
                     mean("org", 0), mean("km", 0),
                     mean("al", 0), mean("rnd", 0)))
    return "\n".join(lines) + "\n"


def header_lines(mode_line, corpus_line):
    return [
        "organiser-on-code: group 180 code atoms by module (12 per draw)",
        "mode: %s" % mode_line,
        "draws: seeds 61-65; 4 packages x 3 modules x 15 atoms = 180 each",
        "score: module labels; organiser is not told K, baselines told 12",
        corpus_line,
    ]


def progress(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def mode_a():
    progress("building corpus from this interpreter's standard library")
    corpus = build_corpus.build_corpus()
    elig = build_corpus.eligibility(corpus["atoms"])
    if len(elig["packages"]) < 4:
        raise SystemExit("need >=4 eligible packages, found %d" % (
            len(elig["packages"])))
    progress("building identifier-token TF-IDF vectors")
    model = tfidf.build([(a["id"], a["text"]) for a in corpus["atoms"]])
    dim = len(model["vocab"])
    rows = []
    for seed in SEEDS:
        progress("scoring seed %d" % seed)
        ids = draw_seed(seed, elig["packages"], elig["mods_by_pkg"],
                        elig["atoms_by_mod"])
        assert len(ids) == 180 and len(set(ids)) == 180
        rows.append((seed, score_seed_tfidf(seed, ids, elig["truth"],
                                            model["sparse"], dim)))
    out = header_lines(
        "TF-IDF from this interpreter's standard library (6 packages)",
        "corpus: %d atoms, %d eligible modules, %d terms" % (
            len(corpus["atoms"]), elig["n_eligible_modules"], dim))
    out.append(format_table(rows))
    sys.stdout.write("\n".join(out))
    return 0


def load_vectors_file(path):
    with open(path, "rb") as handle:
        magic = handle.read(8)
        if magic != VEC_MAGIC:
            raise SystemExit("bad vectors file: magic mismatch")
        count, dim, json_len = struct.unpack("<III", handle.read(12))
        import json
        directory = json.loads(handle.read(json_len).decode("utf-8"))
        blob = handle.read()
    ids = directory["ids"]
    labels = directory["labels"]
    if len(ids) != count or len(labels) != count:
        raise SystemExit("bad vectors file: id/label count mismatch")
    expect = count * dim * 4
    if len(blob) != expect:
        raise SystemExit("bad vectors file: blob size mismatch")
    flat = struct.unpack("<%df" % (count * dim), blob)
    vecmap = {}
    for row, atom_id in enumerate(ids):
        base = row * dim
        vecmap[atom_id] = [float(x) for x in flat[base:base + dim]]
    truth = {atom_id: (lab[0], lab[1], None)
             for atom_id, lab in labels.items()}
    return {"ids": ids, "truth": truth, "vecmap": vecmap,
            "dim": dim, "model": directory.get("model", "?"),
            "revision": directory.get("revision", "?")}


def file_eligibility(ids, truth):
    by_mod = {}
    for atom_id in ids:
        pkg, mod = truth[atom_id][0], truth[atom_id][1]
        by_mod.setdefault((pkg, mod), []).append(atom_id)
    mods_by_pkg = {}
    for (pkg, mod), members in by_mod.items():
        if len(members) >= build_corpus.MIN_ATOMS_PER_MODULE:
            mods_by_pkg.setdefault(pkg, set()).add(mod)
    mods_by_pkg = {p: mods for p, mods in mods_by_pkg.items()
                   if len(mods) >= build_corpus.MIN_MODULES_PER_PACKAGE}
    return {"packages": sorted(mods_by_pkg),
            "mods_by_pkg": {p: sorted(mods_by_pkg[p]) for p in mods_by_pkg},
            "atoms_by_mod": {(p, m): sorted(by_mod[(p, m)])
                             for p in mods_by_pkg for m in mods_by_pkg[p]},
            "n_eligible_modules": sum(len(v) for v in mods_by_pkg.values()),
            "n_eligible_atoms": sum(len(by_mod[(p, m)])
                                    for p in mods_by_pkg
                                    for m in mods_by_pkg[p])}


def mode_b(path):
    progress("loading precomputed vectors")
    data = load_vectors_file(path)
    elig = file_eligibility(data["ids"], data["truth"])
    if len(elig["packages"]) < 4:
        raise SystemExit("need >=4 eligible packages, found %d" % (
            len(elig["packages"])))
    rows = []
    for seed in SEEDS:
        progress("scoring seed %d" % seed)
        ids = draw_seed(seed, elig["packages"], elig["mods_by_pkg"],
                        elig["atoms_by_mod"])
        assert len(ids) == 180 and len(set(ids)) == 180
        rows.append((seed, score_seed_dense(seed, ids, data["truth"],
                                            data["vecmap"])))
    out = header_lines(
        "precomputed unit vectors (%s)" % data["model"],
        "corpus: %d atoms x %d dims, %d eligible modules" % (
            len(data["ids"]), data["dim"], elig["n_eligible_modules"]))
    out.append(format_table(rows))
    sys.stdout.write("\n".join(out))
    return 0


def main(argv):
    if len(argv) == 1:
        return mode_a()
    if len(argv) == 3 and argv[1] == "--vectors":
        return mode_b(argv[2])
    raise SystemExit("usage: python3 run.py [--vectors FILE]")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
