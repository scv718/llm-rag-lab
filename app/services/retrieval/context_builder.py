MAX_CONTEXT_CHARS = 12000


def build_context_and_citations(ranked_hits: list[dict], max_context_chars: int = MAX_CONTEXT_CHARS) -> tuple[str, list[dict]]:
    context_lines = ["[참고 발췌]"]
    citations = []
    current_chars = len(context_lines[0]) + 1

    normalized_hits = merge_adjacent_code_hits(ranked_hits)

    for hit in normalized_hits:
        if hit["source"] in {"keyword", "path"}:
            line = f"- (kind={hit['source']}, score={hit['score']}, path={hit['path']}, line={hit['line']}, keywords={','.join(hit['matched_keywords'])}) {hit['text']}"
            if current_chars + len(line) + 1 > max_context_chars:
                break
            context_lines.append(line)
            current_chars += len(line) + 1
            citations.append(
                {
                    "kind": hit["source"],
                    "path": hit["path"],
                    "line": hit["line"],
                    "matched_keywords": hit["matched_keywords"],
                    "text": hit["text"],
                    "score": hit["score"],
                }
            )
            continue

        metadata = hit["metadata"]
        document = hit["document"]
        distance = hit["distance"]

        if metadata.get("kind") == "doc":
            line = f"- (kind=doc, source_type={metadata.get('source_type', 'doc')}, score={hit['score']}, page={metadata.get('page')}, chunk_id={metadata.get('chunk_id', '')}) {document}"
            if current_chars + len(line) + 1 > max_context_chars:
                break
            context_lines.append(line)
            current_chars += len(line) + 1
            citations.append(
                {
                    "kind": "doc",
                    "source_type": metadata.get("source_type"),
                    "filename": metadata.get("filename"),
                    "page": metadata.get("page"),
                    "chunk_id": metadata.get("chunk_id"),
                    "chunk_index": metadata.get("chunk_index"),
                    "distance": distance,
                    "score": hit["score"],
                }
            )
        else:
            line = f"- (kind=code, source_type={metadata.get('source_type', 'code')}, score={hit['score']}, path={metadata.get('path')}, L{metadata.get('start_line')}-L{metadata.get('end_line')}, chunk_id={metadata.get('chunk_id', '')}) {document}"
            if current_chars + len(line) + 1 > max_context_chars:
                break
            citations.append(
                {
                    "kind": "code",
                    "source_type": metadata.get("source_type"),
                    "filename": metadata.get("filename"),
                    "path": metadata.get("path"),
                    "start_line": metadata.get("start_line"),
                    "end_line": metadata.get("end_line"),
                    "chunk_id": metadata.get("chunk_id"),
                    "distance": distance,
                    "score": hit["score"],
                }
            )
            context_lines.append(line)
            current_chars += len(line) + 1

    return "\n".join(context_lines), citations


def merge_adjacent_code_hits(ranked_hits: list[dict], max_gap: int = 5) -> list[dict]:
    merged = []
    for hit in ranked_hits:
        if hit.get("source") != "vector":
            merged.append(hit)
            continue

        metadata = hit.get("metadata", {})
        if metadata.get("kind") != "code":
            merged.append(hit)
            continue

        if not merged:
            merged.append(hit)
            continue

        prev = merged[-1]
        prev_meta = prev.get("metadata", {})
        if (
            prev.get("source") == "vector"
            and prev_meta.get("kind") == "code"
            and prev_meta.get("path") == metadata.get("path")
            and prev_meta.get("end_line") is not None
            and metadata.get("start_line") is not None
            and int(metadata.get("start_line")) - int(prev_meta.get("end_line")) <= max_gap
        ):
            merged[-1] = {
                **prev,
                "document": f"{prev.get('document', '')}\n{hit.get('document', '')}".strip(),
                "distance": min(float(prev.get("distance", 1.0)), float(hit.get("distance", 1.0))),
                "score": max(float(prev.get("score", 0.0)), float(hit.get("score", 0.0))),
                "metadata": {
                    **prev_meta,
                    "end_line": metadata.get("end_line"),
                },
            }
            continue

        merged.append(hit)

    return merged
