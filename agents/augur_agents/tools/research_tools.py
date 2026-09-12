"""Literature search for the Research Agent (stub).

Read-only and advisory. These tools stand in for a ``research-mcp`` over the
arXiv / Semantic Scholar APIs; the tool names and return shapes are what that
server will expose, so swapping it in later does not change the agent.

The corpus below is small, real, and deliberately relevant to what this platform
does - the papers behind the techniques in ``docs/ultrascale_playbook.md``. It is
*not* a search engine: a query that matches nothing returns nothing rather than
inventing a plausible-looking paper, because an agent instructed to cite its
sources must not be handed fabricated ones.
"""

from __future__ import annotations

import re
from typing import Any

## =============================================================================
# Corpus
#
# Real papers, summarised. `topics` carries the keywords search matches on, so a
# query does not have to hit the exact wording of a title.
## =============================================================================

_PAPERS: list[dict[str, Any]] = [
    {
        "arxiv_id": "1706.03762",
        "title": "Attention Is All You Need",
        "authors": ["Vaswani", "Shazeer", "Parmar", "Uszkoreit", "Jones", "Gomez",
                    "Kaiser", "Polosukhin"],
        "date": "2017-06-12",
        "categories": ["cs.CL", "cs.LG"],
        "abstract": (
            "Introduces the Transformer, an architecture based solely on attention "
            "mechanisms, dispensing with recurrence and convolutions entirely. "
            "Establishes multi-head self-attention and the encoder-decoder stack "
            "that nearly all subsequent language models build on."
        ),
        "topics": ["transformer", "attention", "architecture", "self-attention",
                   "multi-head"],
        "sections": {
            "Architecture": "Encoder-decoder stacks of multi-head self-attention "
                            "and position-wise feed-forward layers.",
            "Why attention": "Constant path length between any two positions and "
                             "full parallelism across the sequence, unlike RNNs.",
        },
    },
    {
        "arxiv_id": "2001.08361",
        "title": "Scaling Laws for Neural Language Models",
        "authors": ["Kaplan", "McCandlish", "Henighan", "Brown", "Chess", "Child"],
        "date": "2020-01-23",
        "categories": ["cs.LG"],
        "abstract": (
            "Loss scales as a power law with model size, dataset size, and compute, "
            "across more than seven orders of magnitude. Larger models are "
            "substantially more sample-efficient, so compute-optimal training "
            "involves very large models on modest data, stopped well short of "
            "convergence."
        ),
        "topics": ["scaling laws", "compute", "model size", "data", "budget",
                   "efficiency"],
        "sections": {
            "Result": "Power-law relationships between loss and each of N, D, C.",
            "Implication": "Spend a growing compute budget mostly on parameters.",
        },
    },
    {
        "arxiv_id": "2203.15556",
        "title": "Training Compute-Optimal Large Language Models (Chinchilla)",
        "authors": ["Hoffmann", "Borgeaud", "Mensch", "Buchatskaya", "Cai"],
        "date": "2022-03-29",
        "categories": ["cs.CL", "cs.LG"],
        "abstract": (
            "Revisits the scaling laws and finds that existing large models are "
            "significantly undertrained: model size and training tokens should be "
            "scaled roughly equally. Chinchilla (70B, 1.4T tokens) outperforms "
            "Gopher (280B) while using the same compute budget."
        ),
        "topics": ["scaling laws", "compute", "tokens", "budget", "chinchilla",
                   "data", "efficiency", "how many tokens"],
        "sections": {
            "Finding": "Roughly 20 training tokens per parameter is compute-optimal.",
            "Implication": "Most models before this were too large for their data.",
        },
    },
    {
        "arxiv_id": "1710.03740",
        "title": "Mixed Precision Training",
        "authors": ["Micikevicius", "Narang", "Alben", "Diamos", "Elsen"],
        "date": "2017-10-10",
        "categories": ["cs.AI", "cs.LG"],
        "abstract": (
            "Trains networks in half precision while matching full-precision "
            "accuracy, using three techniques: an FP32 master copy of the weights "
            "for the optimizer update, loss scaling to keep small gradients from "
            "underflowing, and FP32 accumulation for reductions."
        ),
        "topics": ["mixed precision", "fp16", "bf16", "loss scaling", "precision",
                   "memory", "numerical stability"],
        "sections": {
            "Master weights": "Small updates would round to zero in FP16 and never "
                              "recover, so the optimizer keeps an FP32 copy.",
            "Loss scaling": "Scale the loss before backward, unscale before the step.",
        },
    },
    {
        "arxiv_id": "1910.02054",
        "title": "ZeRO: Memory Optimizations Toward Training Trillion Parameter Models",
        "authors": ["Rajbhandari", "Rasley", "Ruwase", "He"],
        "date": "2019-10-04",
        "categories": ["cs.LG", "cs.DC"],
        "abstract": (
            "Removes the memory redundancy of data-parallel training by sharding "
            "optimizer states (stage 1), gradients (stage 2), and parameters "
            "(stage 3) across data-parallel ranks, reconstructing full tensors on "
            "demand. Per-device memory for these falls linearly with the degree of "
            "data parallelism."
        ),
        "topics": ["zero", "fsdp", "sharding", "data parallel", "memory",
                   "optimizer states", "distributed", "deepspeed"],
        "sections": {
            "Stages": "1 shards optimizer state, 2 adds gradients, 3 adds parameters.",
            "Cost": "Stage 3 adds ~1.5x communication, largely hidden by prefetching.",
        },
    },
    {
        "arxiv_id": "1909.08053",
        "title": "Megatron-LM: Training Multi-Billion Parameter Language Models "
                 "Using Model Parallelism",
        "authors": ["Shoeybi", "Patwary", "Puri", "LeGresley", "Casper", "Catanzaro"],
        "date": "2019-09-17",
        "categories": ["cs.CL"],
        "abstract": (
            "Introduces intra-layer tensor parallelism for transformers: split the "
            "MLP and attention weight matrices column-wise then row-wise so each "
            "block needs only a single all-reduce in forward and backward."
        ),
        "topics": ["tensor parallel", "model parallel", "megatron", "distributed",
                   "sharding"],
        "sections": {
            "Pattern": "Column-parallel followed by row-parallel minimises comms.",
            "Limit": "Communication is on the critical path, so keep it in a node.",
        },
    },
    {
        "arxiv_id": "1811.06965",
        "title": "GPipe: Efficient Training of Giant Neural Networks using Pipeline "
                 "Parallelism",
        "authors": ["Huang", "Cheng", "Bapna", "Firat", "Chen"],
        "date": "2018-11-16",
        "categories": ["cs.CV", "cs.LG"],
        "abstract": (
            "Partitions a model across accelerators by layer and splits each "
            "mini-batch into micro-batches pipelined through the stages, reducing "
            "the idle 'bubble' to (p-1)/m for p stages and m micro-batches."
        ),
        "topics": ["pipeline parallel", "gpipe", "bubble", "micro-batch",
                   "distributed", "memory"],
        "sections": {
            "Bubble": "Idle time shrinks as the micro-batch count grows.",
            "Cost": "Activations for all in-flight micro-batches must be held.",
        },
    },
    {
        "arxiv_id": "2205.14135",
        "title": "FlashAttention: Fast and Memory-Efficient Exact Attention with "
                 "IO-Awareness",
        "authors": ["Dao", "Fu", "Ermon", "Rudra", "Ré"],
        "date": "2022-05-27",
        "categories": ["cs.LG"],
        "abstract": (
            "Computes exact attention in tiles that fit in on-chip SRAM, using an "
            "online softmax so the full attention matrix is never materialised in "
            "HBM. Cuts memory from quadratic to linear in sequence length and is "
            "substantially faster in wall-clock terms."
        ),
        "topics": ["flashattention", "attention", "kernel", "memory", "long context",
                   "efficiency", "cuda", "io-aware"],
        "sections": {
            "Idea": "Tile Q/K/V into SRAM, never write the S or P matrices to HBM.",
            "Result": "Exact, not an approximation - it displaced linear attention.",
        },
    },
    {
        "arxiv_id": "2307.08691",
        "title": "FlashAttention-2: Faster Attention with Better Parallelism and "
                 "Work Partitioning",
        "authors": ["Dao"],
        "date": "2023-07-17",
        "categories": ["cs.LG"],
        "abstract": (
            "Reduces non-matmul FLOPs and improves work partitioning across warps "
            "and thread blocks, roughly doubling FlashAttention's throughput and "
            "reaching a substantially higher fraction of peak on A100."
        ),
        "topics": ["flashattention", "attention", "kernel", "cuda", "efficiency",
                   "long context"],
        "sections": {
            "Change": "Better warp-level partitioning; fewer non-matmul operations.",
        },
    },
    {
        "arxiv_id": "2310.01889",
        "title": "Ring Attention with Blockwise Transformers for Near-Infinite Context",
        "authors": ["Liu", "Zaharia", "Abbeel"],
        "date": "2023-10-03",
        "categories": ["cs.CL"],
        "abstract": (
            "Distributes long sequences across devices arranged in a ring, "
            "overlapping the transfer of key/value blocks to the next device with "
            "the attention computation on the current block, so context length "
            "scales with device count without added approximation."
        ),
        "topics": ["ring attention", "context parallel", "long context", "sequence",
                   "distributed", "attention"],
        "sections": {
            "Mechanism": "Overlap K/V rotation around the ring with block compute.",
            "Caveat": "Causal masks make naive chunking unbalanced; zig-zag fixes it.",
        },
    },
    {
        "arxiv_id": "2106.09685",
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "authors": ["Hu", "Shen", "Wallis", "Allen-Zhu", "Li", "Wang", "Chen"],
        "date": "2021-06-17",
        "categories": ["cs.CL", "cs.LG"],
        "abstract": (
            "Freezes the pretrained weights and injects trainable low-rank "
            "decomposition matrices into each layer, cutting trainable parameters "
            "by orders of magnitude with no additional inference latency once "
            "merged, and quality comparable to full fine-tuning."
        ),
        "topics": ["lora", "peft", "fine-tuning", "adapter", "low-rank", "memory",
                   "efficiency"],
        "sections": {
            "Idea": "Learn a low-rank update dW = BA alongside frozen W.",
            "Benefit": "Optimizer state shrinks with the trainable parameter count.",
        },
    },
    {
        "arxiv_id": "2305.14314",
        "title": "QLoRA: Efficient Finetuning of Quantized LLMs",
        "authors": ["Dettmers", "Pagnoni", "Holtzman", "Zettlemoyer"],
        "date": "2023-05-23",
        "categories": ["cs.LG"],
        "abstract": (
            "Backpropagates through a frozen 4-bit quantized base model into LoRA "
            "adapters, using the 4-bit NormalFloat data type, double quantization, "
            "and paged optimizers. Finetunes a 65B model on a single 48GB GPU while "
            "preserving full 16-bit finetuning quality."
        ),
        "topics": ["qlora", "quantization", "4-bit", "peft", "fine-tuning", "memory",
                   "nf4", "single gpu"],
        "sections": {
            "NF4": "An information-theoretically optimal dtype for normal weights.",
            "Result": "Large-model finetuning on one consumer-scale GPU.",
        },
    },
    {
        "arxiv_id": "2101.03961",
        "title": "Switch Transformers: Scaling to Trillion Parameter Models with "
                 "Simple and Efficient Sparsity",
        "authors": ["Fedus", "Zoph", "Shazeer"],
        "date": "2021-01-11",
        "categories": ["cs.LG"],
        "abstract": (
            "Simplifies mixture-of-experts routing to a single expert per token, "
            "making sparse models stable and simple enough to scale to trillions of "
            "parameters with constant FLOPs per token."
        ),
        "topics": ["moe", "mixture of experts", "sparsity", "routing", "expert "
                   "parallel", "switch"],
        "sections": {
            "Routing": "Top-1 routing with a capacity factor and load balancing loss.",
        },
    },
    {
        "arxiv_id": "2401.04088",
        "title": "Mixtral of Experts",
        "authors": ["Jiang", "Sablayrolles", "Roux", "Mensch", "Savary"],
        "date": "2024-01-08",
        "categories": ["cs.LG"],
        "abstract": (
            "A sparse mixture-of-experts language model where each layer routes "
            "every token to 2 of 8 experts, giving 47B total parameters but only "
            "13B active per token, matching or beating much larger dense models."
        ),
        "topics": ["moe", "mixture of experts", "mixtral", "routing", "sparse",
                   "expert parallel"],
        "sections": {
            "Shape": "8 experts per layer, top-2 routing, 13B active parameters.",
        },
    },
    {
        "arxiv_id": "2412.19437",
        "title": "DeepSeek-V3 Technical Report",
        "authors": ["DeepSeek-AI"],
        "date": "2024-12-27",
        "categories": ["cs.CL"],
        "abstract": (
            "A 671B-parameter mixture-of-experts model (37B active) trained on 14.8T "
            "tokens. Notable for the first large-scale public FP8 training recipe, "
            "Multi-head Latent Attention to shrink the KV cache, the DualPipe "
            "near-zero-bubble pipeline schedule, and pipeline parallelism combined "
            "with ZeRO-1."
        ),
        "topics": ["deepseek", "fp8", "moe", "pipeline parallel", "dualpipe",
                   "mla", "training recipe", "large scale", "precision"],
        "sections": {
            "FP8": "FP8 matmuls with higher-precision master weights and per-tile "
                   "scaling to control activation outliers.",
            "DualPipe": "Splits the backward pass to fill pipeline bubbles.",
        },
    },
    {
        "arxiv_id": "2307.09288",
        "title": "Llama 2: Open Foundation and Fine-Tuned Chat Models",
        "authors": ["Touvron", "Martin", "Stone", "Albert", "Almahairi"],
        "date": "2023-07-18",
        "categories": ["cs.CL"],
        "abstract": (
            "A family of 7B to 70B pretrained and fine-tuned models, documenting "
            "grouped-query attention, the RLHF pipeline, and the data and safety "
            "methodology used."
        ),
        "topics": ["llama", "open model", "gqa", "grouped-query attention", "rlhf",
                   "fine-tuning", "base model"],
        "sections": {
            "GQA": "Shares key/value heads across query heads to shrink the KV cache.",
        },
    },
]

_BY_ID = {p["arxiv_id"]: p for p in _PAPERS}

_STOPWORDS = {
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with", "is",
    "are", "what", "how", "why", "which", "best", "latest", "recent", "new",
    "about", "paper", "papers", "research", "using", "use", "can", "do", "does",
}


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9\-]+", text.lower()) if w not in _STOPWORDS]


def _score(paper: dict[str, Any], terms: list[str]) -> int:
    """Weighted keyword overlap. Topics count most - they are the curated index."""
    if not terms:
        return 0
    haystacks = (
        (" ".join(paper["topics"]).lower(), 3),
        (paper["title"].lower(), 2),
        (paper["abstract"].lower(), 1),
    )
    return sum(w for text, w in haystacks for t in terms if t in text)


def _public(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "arxiv_id": paper["arxiv_id"],
        "title": paper["title"],
        "authors": paper["authors"],
        "date": paper["date"],
        "categories": paper["categories"],
        "abstract": paper["abstract"],
        "url": f"https://arxiv.org/abs/{paper['arxiv_id']}",
    }


_STUB_NOTE = (
    "Stub corpus: a small curated set of real papers, not a live arXiv search. "
    "Absence from these results does not mean a paper does not exist."
)


def search_papers(
    query: str, since: str | None = None, limit: int = 5
) -> dict[str, Any]:
    """Search the literature corpus.

    Args:
        query: free text, e.g. "how to train long context efficiently".
        since: optional ISO date; only papers published on or after it.
        limit: maximum results (capped at 10).

    Returns a ranked list. An empty list means nothing matched - report that
    rather than answering from memory.
    """
    terms = _tokenize(query or "")
    scored = [(s, p) for p in _PAPERS if (s := _score(p, terms)) > 0]
    if since:
        scored = [(s, p) for s, p in scored if p["date"] >= since]
    scored.sort(key=lambda sp: (-sp[0], sp[1]["date"]))
    results = [_public(p) for _, p in scored[: max(1, min(limit, 10))]]
    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "note": _STUB_NOTE if results else (
            f"No paper in the corpus matches {query!r}. Say so plainly - do not "
            f"answer from memory or invent a citation."
        ),
    }


def get_paper(arxiv_id: str) -> dict[str, Any]:
    """Full record for one paper, including per-section summaries."""
    paper = _BY_ID.get((arxiv_id or "").strip())
    if paper is None:
        return {
            "success": False,
            "error": (
                f"No paper {arxiv_id!r} in the corpus. Available ids: "
                f"{', '.join(sorted(_BY_ID))}."
            ),
        }
    out = _public(paper)
    out["sections"] = paper["sections"]
    return {"success": True, "paper": out, "note": _STUB_NOTE}


def summarize_findings(arxiv_ids: list[str], question: str) -> dict[str, Any]:
    """Gather the evidence for a question from specific papers.

    Deliberately returns *material with citations* rather than a written answer:
    the synthesis is the agent's job, and the agent must be able to attribute
    every sentence it writes to one of these entries.
    """
    ids = [i.strip() for i in (arxiv_ids or []) if i and i.strip()]
    if not ids:
        return {"success": False, "error": "Pass at least one arxiv_id."}

    found, missing = [], []
    for pid in ids:
        paper = _BY_ID.get(pid)
        if paper is None:
            missing.append(pid)
            continue
        found.append({
            "arxiv_id": paper["arxiv_id"],
            "title": paper["title"],
            "date": paper["date"],
            "url": f"https://arxiv.org/abs/{paper['arxiv_id']}",
            "abstract": paper["abstract"],
            "key_points": paper["sections"],
        })
    if not found:
        return {"success": False, "error": f"None of {ids} are in the corpus."}
    return {
        "success": True,
        "question": question,
        "evidence": found,
        "not_found": missing,
        "sources": [f"arXiv:{p['arxiv_id']} - {p['title']}" for p in found],
        "note": (
            "Base the answer only on `evidence`, attribute every claim to an "
            "arxiv_id, and list the sources. " + _STUB_NOTE
        ),
    }


RESEARCH_TOOLS = [search_papers, get_paper, summarize_findings]

__all__ = ["search_papers", "get_paper", "summarize_findings", "RESEARCH_TOOLS"]
