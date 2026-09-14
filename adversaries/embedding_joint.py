"""
embedding_joint.py — POST-HOC EXPLORATORY EMBEDDING ADVERSARY (RUN_DECISIONS
D14; design: docs/embedding_adversary_design.md).

Group with sentence embeddings, order with the frozen Memon-inspired module:
    grouping   all-mpnet-base-v2 (pinned revision), L2-normalised, cosine;
               average linkage cut to EXACTLY the known N -- the same steps
               as memon_joint.group_known_n with the similarity swapped
               (checked by the smoke test)
    ordering   memon_joint.direction_edges (character-bigram boundary
               likelihood, n = d = 2) -> tanh weight -> order_from_sim.order_cluster
               (SHA-256 seeded, D13). Unchanged.
The embedding representation is the only architectural change. F1_L is the
primary comparison; F1_J and q are secondary (different clusters can move q).

Masking happens here, as in memon_joint: an offline attacker builds no prompt,
so nothing else would stop raw ids reaching a tie rule.
"""

import os
import sys

import numpy as np
from scipy.cluster.hierarchy import cut_tree
from scipy.cluster.hierarchy import linkage as hier_linkage
from scipy.spatial.distance import squareform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from masking import assert_ids_masked, mask_fragment_ids      # noqa: E402
from memon import build_model, build_vocab                    # noqa: E402
from memon_joint import DEFAULT_D, DEFAULT_N, direction_edges  # noqa: E402
from order_from_sim import order_cluster                      # noqa: E402

MODEL_ID = "sentence-transformers/all-mpnet-base-v2"
REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"          # frozen, D14
MODEL_FILES = ["model.safetensors", "tokenizer.json", "vocab.txt", "config.json", "modules.json",
               "1_Pooling/config.json", "sentence_bert_config.json", "config_sentence_transformers.json",
               "special_tokens_map.json", "tokenizer_config.json"]
BATCH_SIZE = 64


def model_path():
    """The pinned snapshot, the ten needed files only."""
    from huggingface_hub import snapshot_download
    return snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=MODEL_FILES)


def load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_path(), device="cpu")


def embed(texts, model, batch_size=BATCH_SIZE):
    return np.asarray(model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                                   convert_to_numpy=True, show_progress_bar=False), dtype=np.float64)


def cut_exact_n(ids, sim_matrix, n_groups, seed=42):
    """memon_joint.group_known_n's steps on a precomputed similarity matrix:
    D = 1 - sim, 1e-6 seeded jitter, symmetrise, average linkage, cut to
    exactly n_groups, clusters sorted by smallest member."""
    m = len(ids)
    if m <= n_groups:
        return [[f] for f in sorted(ids)]
    rng = np.random.default_rng(seed)
    # Cosine similarity of L2-normalised float embeddings can exceed 1 by
    # rounding (~1e-7), which makes 1 - sim slightly negative and scipy refuses
    # the linkage. Cosine distance is non-negative by definition, so clamp at 0.
    # A no-op for TF-IDF similarity, which never exceeds 1 (smoke check 7).
    D = np.clip(1.0 - np.asarray(sim_matrix, dtype=np.float64), 0.0, None)
    np.fill_diagonal(D, 0.0)
    D += rng.random((m, m)) * 1e-6
    D = (D + D.T) / 2.0
    np.fill_diagonal(D, 0.0)
    labels = [int(x) for x in cut_tree(hier_linkage(squareform(D, checks=False), method="average"),
                                       n_clusters=[n_groups])[:, 0]]
    grouped = {}
    for idx, lab in enumerate(labels):
        grouped.setdefault(lab, []).append(ids[idx])
    return sorted((sorted(v) for v in grouped.values()), key=lambda c: c[0])


def attack(fragments, n_docs, model, n=DEFAULT_N, d=DEFAULT_D, seed=42, mask_seed=None,
           batch_size=BATCH_SIZE):
    masked, id_map = mask_fragment_ids(fragments, seed=seed if mask_seed is None else mask_seed)
    back = dict(id_map)
    ids = [f["fragment_id"] for f in masked]
    assert_ids_masked(ids, where="embedding_joint.attack")
    text_by_id = {f["fragment_id"]: f["text"] for f in masked}

    E = embed([text_by_id[i] for i in ids], model, batch_size=batch_size)
    clusters = cut_exact_n(ids, E @ E.T, n_docs, seed=seed)

    ngram = build_model(masked, n)
    vocab = build_vocab(masked)
    ordered, infos = [], []
    for c in clusters:
        if len(c) <= 1:
            ordered.append(list(c))
            continue
        order, info = order_cluster(c, direction_edges(c, text_by_id, ngram, vocab, n, d))
        ordered.append(order)
        infos.append(info)
    placed = [x for g in ordered for x in g]
    assert sorted(placed) == sorted(ids), "embedding_joint dropped or duplicated ids"
    sizes = sorted((len(g) for g in ordered), reverse=True)
    return [[back[x] for x in g] for g in ordered], {
        "attacker": "embedding (exploratory)", "model": MODEL_ID, "revision": REVISION,
        "n": n, "d": d, "seed": seed, "n_fragments": len(ids), "n_docs_given": n_docs,
        "n_groups": len(ordered), "largest": sizes[0] if sizes else 0,
        "singletons": sum(1 for s in sizes if s == 1),
        "all_orderings_connected": all(i["fully_connected"] for i in infos)}
