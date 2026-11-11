"""
loader.py — Data loading utilities for the evaluation harness.

Functions:
    load_jsonl             — generic JSONL loader
    load_fragments         — loads fragments.jsonl
    load_answer_key        — loads answer_key.jsonl
    group_fragments_by_record — groups fragments by record_id
    load_llm_ordering_guesses — loads LLM ordering guesses
    load_llm_grouping_guesses  — loads LLM grouping guesses
"""

import json
from pathlib import Path
from typing import List, Dict, Any


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file into a list of dicts."""
    data = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def load_fragments(path: Path) -> List[Dict[str, Any]]:
    """
    Load fragments.jsonl.

    Expected format:
        {"record_id": "r_0000", "fragment_id": "frag_0000", "text": "..."}
    """
    return load_jsonl(path)


def load_answer_key(path: Path) -> Dict[str, List[str]]:
    """
    Load answer_key.jsonl.

    Supports multiple formats:
    1. {"record_id": "r_0000", "order": ["frag_0000", "frag_0001", ...]}
    2. {"record_id": "r_0000", "fragments": [{"fragment_id": "...", "position": 0}, ...]}
    3. {"r_0000": ["frag_0000", "frag_0001", ...]}  # record_id as key
    4. Individual entries with fragment_id, record_id, position (one per fragment)
    
    Returns:
        {record_id: [fragment_id, ...]}
    """
    data = load_jsonl(path)
    answer_key = {}
    
    # Check if this is the individual fragment format (each entry has fragment_id, record_id, position)
    if data and all("fragment_id" in d and "record_id" in d and "position" in d for d in data):
        # Group by record_id and sort by position
        record_groups = {}
        for entry in data:
            record_id = entry["record_id"]
            if record_id not in record_groups:
                record_groups[record_id] = []
            record_groups[record_id].append((entry["position"], entry["fragment_id"]))
        
        # Sort each group by position and create the order list
        for record_id, fragments in record_groups.items():
            sorted_fragments = sorted(fragments, key=lambda x: x[0])
            answer_key[record_id] = [frag_id for _, frag_id in sorted_fragments]
        
        return answer_key
    
    # Otherwise, try other formats
    for entry in data:
        # Format 1: Direct record_id with order field
        if "record_id" in entry and "order" in entry:
            record_id = entry["record_id"]
            answer_key[record_id] = entry["order"]
        
        # Format 2: Record_id with fragments list (each with position)
        elif "record_id" in entry and "fragments" in entry:
            record_id = entry["record_id"]
            frags = entry["fragments"]
            if frags and isinstance(frags[0], dict):
                # Check if fragments have position field
                if "position" in frags[0]:
                    sorted_frags = sorted(frags, key=lambda r: r["position"])
                    answer_key[record_id] = [r["fragment_id"] for r in sorted_frags]
                else:
                    # Just use the order as given
                    answer_key[record_id] = [r["fragment_id"] for r in frags]
            else:
                # Fragments is a list of strings
                answer_key[record_id] = frags
        
        # Format 3: Entry has a single key that is the record_id
        elif len(entry) == 1:
            record_id = list(entry.keys())[0]
            value = entry[record_id]
            if isinstance(value, list):
                answer_key[record_id] = value
            else:
                raise ValueError(f"Unknown value type for record {record_id}: {type(value)}")
        
        else:
            # Try to find record_id in any field
            record_id = None
            order = None
            
            # Look for record_id
            for key in ["record_id", "id", "doc_id", "document_id"]:
                if key in entry:
                    record_id = entry[key]
                    break
            
            # Look for order
            for key in ["order", "fragments", "sequence", "ordered_fragments"]:
                if key in entry:
                    order = entry[key]
                    break
            
            if record_id is not None and order is not None:
                if isinstance(order, list):
                    answer_key[record_id] = order
                else:
                    raise ValueError(f"Order for record {record_id} is not a list")
            else:
                # If we have fragment_id and record_id but no position (unlikely at this point)
                if "fragment_id" in entry and "record_id" in entry:
                    record_id = entry["record_id"]
                    if record_id not in answer_key:
                        answer_key[record_id] = []
                    answer_key[record_id].append(entry["fragment_id"])
                else:
                    raise ValueError(f"Unknown answer key format for entry: {entry}")
    
    return answer_key


def group_fragments_by_record(fragments: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Group fragments by record_id.

    Returns:
        {record_id: [fragment_id, ...]}
    """
    groups = {}
    for frag in fragments:
        record_id = frag["record_id"]
        if record_id not in groups:
            groups[record_id] = []
        groups[record_id].append(frag["fragment_id"])
    return groups


def load_llm_ordering_guesses(path: Path) -> Dict[str, List[str]]:
    """
    Load LLM ordering guesses.

    Supports multiple formats:
    1. {"record_id": "r_0000", "order": ["frag_0000", "frag_0001", ...]}
    2. {"record_id": "r_0000", "guessed_order": ["frag_0000", "frag_0001", ...]}
    3. {"r_0000": ["frag_0000", "frag_0001", ...]}  # record_id as key
    4. Individual entries with fragment_id, record_id, position (like answer key)
    
    Returns:
        {record_id: [fragment_id, ...]}
    """
    data = load_jsonl(path)
    guesses = {}
    
    # Check if this is the individual fragment format (like answer key)
    if data and all("fragment_id" in d and "record_id" in d and "position" in d for d in data):
        # Group by record_id and sort by position
        record_groups = {}
        for entry in data:
            record_id = entry["record_id"]
            if record_id not in record_groups:
                record_groups[record_id] = []
            record_groups[record_id].append((entry["position"], entry["fragment_id"]))
        
        # Sort each group by position and create the order list
        for record_id, fragments in record_groups.items():
            sorted_fragments = sorted(fragments, key=lambda x: x[0])
            guesses[record_id] = [frag_id for _, frag_id in sorted_fragments]
        
        return guesses
    
    # Try other formats
    for entry in data:
        record_id = None
        order = None
        
        # Look for record_id
        for key in ["record_id", "id", "doc_id", "document_id"]:
            if key in entry:
                record_id = entry[key]
                break
        
        # Look for order in various possible field names
        for key in ["order", "guessed_order", "predicted_order", "ordering", "fragments", "sequence"]:
            if key in entry and isinstance(entry[key], list):
                order = entry[key]
                break
        
        # If entry is a single key-value pair with a list
        if len(entry) == 1:
            key = list(entry.keys())[0]
            value = entry[key]
            if isinstance(value, list):
                # The key might be the record_id
                record_id = key
                order = value
        
        if record_id is None:
            # Try to infer record_id from the entry
            if "record_id" in entry:
                record_id = entry["record_id"]
            elif "id" in entry:
                record_id = entry["id"]
            else:
                # Skip entries without record_id
                continue
        
        if order is None:
            # Try to find any list in the entry
            for key, value in entry.items():
                if isinstance(value, list) and key not in ["record_id", "id", "doc_id"]:
                    order = value
                    break
        
        if order is None:
            # Skip entries without an order list
            continue
        
        guesses[record_id] = order
    
    return guesses

def load_llm_grouping_guesses(path: Path) -> Dict[int, List[str]]:
    """
    Load LLM grouping guesses.

    Expected format:
        {"groups": {"0": ["frag_0000", "frag_0001", ...], "1": [...]}}
    
    Returns:
        {group_id: [fragment_id, ...]}
    """
    data = load_jsonl(path)
    if not data:
        return {}
    # The file should contain a single object with groups
    entry = data[0]
    if "groups" in entry:
        groups = entry["groups"]
        # Convert string keys to int
        return {int(k): v for k, v in groups.items()}
    else:
        raise ValueError("LLM grouping file must contain a 'groups' key")