"""
orderers.py — ordering and grouping strategies for Game O and Game L.

Game O strategies (return an ordered list of fragment_ids):
    random_order        — uniform random shuffle (pure baseline)
    greedy_nn_order     — greedy nearest-neighbour path on a text-similarity graph
    mst_order           — max spanning tree path on a text-similarity graph

Game L strategies (return {int: [fragment_ids]}):
    random_grouping     — uniform random assignment
    greedy_grouping     — agglomerative single-linkage merge
    mst_grouping        — max spanning tree, cut (n_groups − 1) weakest edges

All graph-based methods share the same O(n²) pairwise similarity pre-compute
step, then O(n² log n) for sorting / Prim's.  For typical record lengths
(≤ ~50 fragments per record, ≤ ~1000 fragments total) this is fast.
"""

import re
import heapq
import random
from itertools import combinations


# ════════════════════════════════════════════════════════════════════════════════
# Text similarity
# ════════════════════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> list:
    return re.findall(r'[a-z0-9]+', text.lower())


def _bigrams(tokens: list) -> set:
    return set(zip(tokens, tokens[1:]))


def text_similarity(text_a: str, text_b: str) -> float:
    """
    Word-bigram Jaccard similarity.

    Falls back to unigram Jaccard when either sequence is too short to produce
    bigrams (single-token fragments, numeric-only content, etc.).

    Returns a value in [0, 1].
    """
    ta = _tokenize(text_a)
    tb = _tokenize(text_b)
    if not ta or not tb:
        return 0.0

    bg_a = _bigrams(ta)
    bg_b = _bigrams(tb)

    if bg_a or bg_b:
        inter = len(bg_a & bg_b)
        union = len(bg_a | bg_b)
        if union:
            return inter / union

    # Unigram fallback
    sa, sb = set(ta), set(tb)
    denom  = len(sa | sb)
    return len(sa & sb) / denom if denom else 0.0


def _build_sim_fn(frag_ids: list, text_by_id: dict):
    """
    Pre-computes all O(n²) pairwise similarities and returns a fast O(1)
    lookup closure.  Call once per record / pool, then pass the closure to
    the ordering / grouping algorithm.
    """
    cache: dict = {}
    ids = list(frag_ids)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            s = text_similarity(text_by_id[a], text_by_id[b])
            cache[(a, b)] = s
            cache[(b, a)] = s
    return lambda x, y: cache.get((x, y), 0.0)


# ════════════════════════════════════════════════════════════════════════════════
# Shared: Prim's max spanning tree
# ════════════════════════════════════════════════════════════════════════════════

def _prim_mst(nodes: list, sim_fn) -> dict:
    """
    Prim's algorithm for a *maximum* spanning tree.

    Returns adj: {node: [(neighbour, weight), ...]}  — the MST adjacency list.
    """
    if len(nodes) <= 1:
        return {nodes[0]: []} if nodes else {}

    # Start with the first node
    start = nodes[0]
    in_tree = {start}
    adj = {f: [] for f in nodes}
    heap = []   # (-weight, from_node, to_node)

    # Initialize heap with edges from start to all other nodes
    for v in nodes[1:]:
        w = sim_fn(start, v)
        heapq.heappush(heap, (-w, start, v))

    while heap and len(in_tree) < len(nodes):
        neg_w, u, v = heapq.heappop(heap)
        if v in in_tree:
            continue
        w = -neg_w
        # Add edge to MST
        adj[u].append((v, w))
        adj[v].append((u, w))
        in_tree.add(v)
        
        # Add new edges from v to nodes not yet in tree
        for other in nodes:
            if other not in in_tree:
                heapq.heappush(heap, (-sim_fn(v, other), v, other))

    # If some nodes are still disconnected (shouldn't happen with full graph),
    # connect them with the strongest available edge
    if len(in_tree) < len(nodes):
        disconnected = set(nodes) - in_tree
        # Connect each disconnected node to the tree with the strongest edge
        for node in disconnected:
            best_edge = None
            best_weight = -1.0
            for tree_node in in_tree:
                w = sim_fn(node, tree_node)
                if w > best_weight:
                    best_weight = w
                    best_edge = (node, tree_node, w)
            if best_edge:
                n, t, w = best_edge
                adj[n].append((t, w))
                adj[t].append((n, w))
                in_tree.add(n)

    return adj


# ════════════════════════════════════════════════════════════════════════════════
# Game O: ordering strategies
# ════════════════════════════════════════════════════════════════════════════════

def random_order(frag_ids: list) -> list:
    """Uniform random shuffle.  Pure combinatorial baseline."""
    order = list(frag_ids)
    random.shuffle(order)
    return order


def greedy_nn_order(frag_ids: list, text_by_id: dict) -> list:
    """
    Greedy nearest-neighbour path through fragments.

    Start heuristic: the fragment with the lowest average similarity to all
    others — likely an endpoint of the sequential chain.  We try the two
    best candidates and keep whichever chain has the higher total path score.

    Complexity: O(n²) pre-compute + O(n²) path construction.
    """
    n = len(frag_ids)
    if n <= 1:
        return list(frag_ids)

    sim = _build_sim_fn(frag_ids, text_by_id)

    # Average similarity per node — endpoints tend to score lowest
    avg_sim = {
        f: sum(sim(f, g) for g in frag_ids if g != f) / (n - 1)
        for f in frag_ids
    }
    # Try two candidate start nodes (ties broken by fragment ID for reproducibility)
    starts = sorted(frag_ids, key=lambda f: (avg_sim[f], f))[:2]

    def _build_chain(start: str) -> list:
        visited = {start}
        chain   = [start]
        while len(chain) < n:
            last = chain[-1]
            nxt  = max(
                (f for f in frag_ids if f not in visited),
                key=lambda f: sim(last, f)
            )
            chain.append(nxt)
            visited.add(nxt)
        return chain

    best_chain, best_score = None, -1.0
    for start in starts:
        chain = _build_chain(start)
        score = sum(sim(chain[i], chain[i+1]) for i in range(n - 1))
        if score > best_score:
            best_score = score
            best_chain = chain
    return best_chain


def mst_order(frag_ids: list, text_by_id: dict) -> list:
    """
    Maximum spanning tree path.

    1. Build the full pairwise weight graph.
    2. Compute the MST with Prim's (maximising similarity weight).
    3. Find a leaf (degree-1 node) — likely a chain endpoint.
    4. Walk from that leaf, always following the highest-weight unvisited edge.

    For a true sequential chain the MST *is* the path, so this recovers it
    exactly when the similarity function respects adjacency.

    Complexity: O(n² log n).
    """
    n = len(frag_ids)
    if n <= 1:
        return list(frag_ids)

    sim = _build_sim_fn(frag_ids, text_by_id)
    adj = _prim_mst(list(frag_ids), sim)

    # Find a leaf (degree <= 1) - start from there
    leaves = [f for f in frag_ids if len(adj[f]) <= 1]
    start = leaves[0] if leaves else frag_ids[0]

    # Walk the tree - always follow the highest-weight unvisited edge
    path = [start]
    visited = {start}
    current = start
    
    while len(path) < n:
        # Get all unvisited neighbors
        candidates = [(nbr, w) for nbr, w in adj[current] if nbr not in visited]
        if not candidates:
            # If we get stuck but haven't visited all nodes, find the nearest unvisited node
            # and jump to it (this handles disconnected components)
            remaining = [f for f in frag_ids if f not in visited]
            if remaining:
                # Find the best connection from any visited node to any unvisited node
                best_edge = None
                best_weight = -1.0
                for visited_node in visited:
                    for unvisited_node in remaining:
                        w = sim(visited_node, unvisited_node)
                        if w > best_weight:
                            best_weight = w
                            best_edge = (visited_node, unvisited_node)
                if best_edge:
                    from_node, to_node = best_edge
                    # Add the path between them
                    if from_node == current:
                        path.append(to_node)
                        visited.add(to_node)
                        current = to_node
                    else:
                        # Jump to the visited node then to the unvisited one
                        path.append(to_node)
                        visited.add(to_node)
                        current = to_node
                else:
                    # No connections found - just add remaining nodes
                    path.extend(remaining)
                    visited.update(remaining)
            break
        
        # Choose the highest weight edge
        nxt, _ = max(candidates, key=lambda x: x[1])
        path.append(nxt)
        visited.add(nxt)
        current = nxt

    # Ensure we return exactly the same fragments
    if len(path) != n:
        # Add any missing fragments
        missing = [f for f in frag_ids if f not in path]
        path.extend(missing)
    
    return path


# ════════════════════════════════════════════════════════════════════════════════
# Game L: grouping strategies
# ════════════════════════════════════════════════════════════════════════════════

def random_grouping(fragments: list, n_groups: int) -> dict:
    """
    Uniform random round-robin assignment of fragments to n_groups groups.
    Returns {int: [fragment_ids]}.
    """
    frag_ids = [f["fragment_id"] for f in fragments]
    shuffled = frag_ids[:]
    random.shuffle(shuffled)
    groups = {i: [] for i in range(n_groups)}
    for idx, fid in enumerate(shuffled):
        groups[idx % n_groups].append(fid)
    return groups


def greedy_grouping(fragments: list, n_groups: int) -> dict:
    """
    Agglomerative single-linkage grouping.

    Sort all fragment pairs by similarity (descending), then merge with
    Union-Find until exactly n_groups components remain.

    For small datasets (≤ ~1000 fragments) this is fast; the bottleneck is
    the O(n²) pair enumeration.

    Returns {int: [fragment_ids]}.
    """
    frag_ids   = [f["fragment_id"] for f in fragments]
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}
    n          = len(frag_ids)

    if n_groups >= n:
        return {i: [f] for i, f in enumerate(frag_ids)}

    # Union-Find with path compression + rank
    parent = {f: f for f in frag_ids}
    rank   = {f: 0 for f in frag_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]   # path halving
            x = parent[x]
        return x

    def union(x: str, y: str) -> bool:
        rx, ry = find(x), find(y)
        if rx == ry:
            return False
        if rank[rx] < rank[ry]:
            rx, ry = ry, rx
        parent[ry] = rx
        if rank[rx] == rank[ry]:
            rank[rx] += 1
        return True

    # All pairs sorted by similarity descending
    ids   = list(frag_ids)
    pairs = sorted(
        ((text_similarity(text_by_id[a], text_by_id[b]), a, b)
         for i, a in enumerate(ids) for b in ids[i + 1:]),
        reverse=True
    )

    n_components = n
    for s, a, b in pairs:
        if n_components <= n_groups:
            break
        if union(a, b):
            n_components -= 1

    # Collect connected components
    comp: dict = {}
    for f in frag_ids:
        comp.setdefault(find(f), []).append(f)
    return {i: members for i, members in enumerate(comp.values())}


def mst_grouping(fragments: list, n_groups: int) -> dict:
    """
    MST-cut grouping.

    1. Build the maximum spanning tree on all fragments.
    2. Cut the (n_groups − 1) weakest edges.
    3. Return the resulting connected components.

    This is the natural dual of mst_order: the same MST construction,
    but instead of reading off a single path we partition the tree.

    Returns {int: [fragment_ids]}.
    """
    frag_ids   = [f["fragment_id"] for f in fragments]
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}
    n          = len(frag_ids)

    if n_groups >= n:
        return {i: [f] for i, f in enumerate(frag_ids)}

    sim = _build_sim_fn(frag_ids, text_by_id)
    adj = _prim_mst(frag_ids, sim)

    # Collect all MST edges with their weights
    seen:  set  = set()
    edges: list = []                   # [(weight, u, v)]
    for u, neighbors in adj.items():
        for v, w in neighbors:
            key = (min(u, v), max(u, v))
            if key not in seen:
                seen.add(key)
                edges.append((w, u, v))

    # Cut the (n_groups − 1) weakest edges
    edges.sort()                       # ascending by weight
    cut: set = set()
    for w, u, v in edges[: n_groups - 1]:
        cut.add((u, v))
        cut.add((v, u))

    # Rebuild adjacency without cut edges
    pruned = {f: [] for f in frag_ids}
    for w, u, v in edges:
        if (u, v) not in cut:
            pruned[u].append(v)
            pruned[v].append(u)

    # Connected components via DFS
    visited:   set  = set()
    groups:    dict = {}
    gid             = 0
    for start in frag_ids:
        if start in visited:
            continue
        component: list = []
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            stack.extend(pruned[node])
        groups[gid] = component
        gid += 1

    return groups