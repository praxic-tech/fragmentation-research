"""
lm_pmi_t12.py — tiers 1 and 2 of the non-LLM attacker ladder (RUN_DECISIONS
D19, "tiers 1 and 2 design"): zero-shot pair scores from a small base causal
language model, decoded with tier 3's decoder family.

No training. For every ordered pair of fragments (a, b) the model reads
[BOS] a b and we keep the summed log-probability of b's tokens, cond[a, b].
For every fragment alone it reads [BOS] b, giving marg[b]. Then

    pmi[a, b] = (cond[a, b] - marg[b]) / len(b)      per-token PMI: does a help predict b?
    S = A     = pmi, z-scored over the pool's off-diagonal entries
    P[a, b]   = marg[a] + cond[a, b]                  log p(a then b)

so crossenc_t3.same_prob(S) = sigmoid of the symmetrised z-PMI, and
crossenc_t3.before_logit(P) = (log p(a b) - log p(b a)) / 2. There is no
position output (pos = 0); the "position" orderer is not offered.

The model sees two texts and nothing else: no ids, labels or pool. Each
fragment is encoded once as tokenizer(" " + text), cut to its first SIDE_CAP
tokens, so a fragment has the same tokens alone and in a pair.

Score files go to the same store layout as tier 3 (crossenc_t3.store_load reads
them); they also keep the raw cond, marg and token counts for audit.
"""

import os
from collections import Counter

import numpy as np

import crossenc_t3 as T3

MODELS = {
    "T1": ("EleutherAI/pythia-160m-deduped", "582159a2dfe3e712a8d47ae83dec95ae3bde8e7e"),
    "T2": ("EleutherAI/pythia-1.4b-deduped", "554d9c1bae3877f740aece41feb90f912cf9fedc"),
}
NAMES = {"T1": "T1-pythia160m", "T2": "T2-pythia1.4b"}
SIDE_CAP = 64


def load(tier, device, dtype=None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    name, rev = MODELS[tier]
    tok = AutoTokenizer.from_pretrained(name, revision=rev)
    model = AutoModelForCausalLM.from_pretrained(name, revision=rev, torch_dtype=dtype or torch.float32)
    return model.to(device).eval(), tok


def encode(tok, texts):
    return [tok(" " + t, add_special_tokens=False)["input_ids"][:SIDE_CAP] for t in texts]


def _bos(tok):
    return tok.bos_token_id if tok.bos_token_id is not None else tok.eos_token_id


def _target_logprobs(model, seqs, starts, device, pad_id):
    """Summed log p of seqs[i][starts[i]:] given everything before it (right padding)."""
    import torch
    L = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), L), pad_id, dtype=torch.long)
    mask = torch.zeros((len(seqs), L), dtype=torch.long)
    for i, s in enumerate(seqs):
        ids[i, :len(s)] = torch.tensor(s)
        mask[i, :len(s)] = 1
    ids, mask = ids.to(device), mask.to(device)
    rows, cols, tgt, owner = [], [], [], []
    for i, (s, st) in enumerate(zip(seqs, starts)):
        for k in range(st, len(s)):
            rows.append(i)
            cols.append(k - 1)                       # hidden state that predicts token k
            tgt.append(s[k])
            owner.append(i)
    with torch.no_grad():
        h = model.base_model(input_ids=ids, attention_mask=mask).last_hidden_state
        hs = h[torch.tensor(rows, device=device), torch.tensor(cols, device=device)]
        logits = model.get_output_embeddings()(hs).float()
        lp = logits.gather(1, torch.tensor(tgt, device=device)[:, None])[:, 0] - torch.logsumexp(logits, 1)
        out = torch.zeros(len(seqs), dtype=torch.float64, device=device)
        out.index_add_(0, torch.tensor(owner, device=device), lp.double())
    return out.cpu().numpy()


def lm_raw(texts, model, tok, device, token_budget=24000, max_batch=1024):
    """cond (u x u), marg (u,), nb (u,) over the unique texts, and the index map."""
    uniq = sorted(set(texts))
    u = len(uniq)
    dup = {i for i, t in enumerate(uniq) if Counter(texts)[t] > 1}
    toks = encode(tok, uniq)
    nb = np.array([len(t) for t in toks])
    if (nb == 0).any():
        raise ValueError("a fragment encodes to zero tokens")
    bos, pad = _bos(tok), (tok.pad_token_id if tok.pad_token_id is not None else _bos(tok))

    marg = np.zeros(u)
    order = np.argsort(nb, kind="stable")
    i = 0
    while i < u:
        L = nb[order[min(i + max_batch, u) - 1]] + 1
        bs = int(max(1, min(max_batch, token_budget // L)))
        js = order[i:i + bs]
        marg[js] = _target_logprobs(model, [[bos] + toks[j] for j in js], [1] * len(js), device, pad)
        i += bs

    aa, bb = np.meshgrid(np.arange(u), np.arange(u), indexing="ij")
    keep = (aa != bb) | np.isin(aa, list(dup))
    a_idx, b_idx = aa[keep], bb[keep]
    o = np.argsort(nb[a_idx] + nb[b_idx], kind="stable")
    a_idx, b_idx = a_idx[o], b_idx[o]
    cond = np.zeros((u, u))
    i = 0
    while i < len(a_idx):
        last = min(i + max_batch, len(a_idx)) - 1
        L = nb[a_idx[last]] + nb[b_idx[last]] + 1
        bs = int(max(1, min(max_batch, token_budget // L)))
        ja, jb = a_idx[i:i + bs], b_idx[i:i + bs]
        seqs = [[bos] + toks[x] + toks[y] for x, y in zip(ja, jb)]
        cond[ja, jb] = _target_logprobs(model, seqs, [1 + nb[x] for x in ja], device, pad)
        i += bs
    return uniq, cond, marg, nb, int(len(a_idx))


def to_scores(texts, uniq, cond, marg, nb):
    """The tier 3 score dict {S, P, A, pos} for `texts` in the caller's order."""
    uidx = {t: i for i, t in enumerate(uniq)}
    f = np.array([uidx[t] for t in texts])
    m = len(texts)
    off = ~np.eye(m, dtype=bool)
    c, mg, n = cond[f][:, f], marg[f], nb[f].astype(np.float64)
    pmi = (c - mg[None, :]) / n[None, :]
    vals = pmi[off]
    mu, sd = float(vals.mean()), float(vals.std())
    z = np.where(off, (pmi - mu) / (sd if sd > 0 else 1.0), 0.0)
    P = np.where(off, mg[:, None] + c, 0.0)
    return {"S": z.astype(np.float32), "A": z.astype(np.float32), "P": P.astype(np.float32),
            "pos": np.zeros(m, dtype=np.float32)}


def score_texts(texts, model, tok, device, **kw):
    uniq, cond, marg, nb, n_pairs = lm_raw(texts, model, tok, device, **kw)
    sc = to_scores(texts, uniq, cond, marg, nb)
    uidx = {t: i for i, t in enumerate(uniq)}
    f = np.array([uidx[t] for t in texts])
    sc.update(cond=cond[f][:, f].astype(np.float32), marg=marg[f].astype(np.float32), nb=nb[f], n_pairs_scored=n_pairs)
    return sc


def store_save(store_dir, texts, sc):
    sha = T3.texts_sha(texts)
    p = T3.store_path(store_dir, sha)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp.npz"
    np.savez_compressed(tmp, S=sc["S"], P=sc["P"], A=sc["A"], pos=sc["pos"], cond=sc["cond"], marg=sc["marg"],
                        nb=sc["nb"], n=np.int64(len(texts)), n_pairs_scored=np.int64(sc["n_pairs_scored"]))
    os.replace(tmp, p)
    return sha


def attack_from_scores(tier, fragments, n_docs, store_dir, cfg, seed=42, mask_seed=None):
    groups, tel = T3.attack_from_scores(fragments, n_docs, store_dir, cfg, seed, mask_seed)
    tel["attacker"] = NAMES[tier]
    return groups, tel
