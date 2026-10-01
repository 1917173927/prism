import math
import os

import pytest

from app.service.knowledge_embedding import LocalKnowledgeEmbedder, MODEL_CACHE, MODEL_REVISION, cosine


def test_cosine_rejects_nonfinite_and_mismatched_vectors():
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([0, 0], [1, 0]) == 0
    with pytest.raises(ValueError):
        cosine([1], [1, 2])
    with pytest.raises(ValueError):
        cosine([math.nan], [1])


@pytest.mark.skipif(os.environ.get("PRISM_RUN_REAL_KNOWLEDGE_EMBEDDING") != "1", reason="real embedding validation must be explicitly requested")
def test_real_local_model_when_optional_dependency_and_pinned_cache_are_present():
    pytest.importorskip("sentence_transformers")
    snapshot = MODEL_CACHE / "models--intfloat--multilingual-e5-small" / "snapshots" / MODEL_REVISION
    if not snapshot.exists():
        pytest.skip("revision-pinned local model cache not installed")
    embedder = LocalKnowledgeEmbedder()
    passages = embedder.encode(["实现波动率采用历史收益", "基金披露持仓穿透行业", "股票波动幅度源自历史回报序列"])
    query = embedder.encode(["历史收益的波动程度"], query=True)[0]
    assert len(query) == 384
    assert len(passages) == 3
    assert cosine(query, passages[0]) > cosine(query, passages[1])
    assert all(math.isfinite(value) for vector in passages for value in vector)
