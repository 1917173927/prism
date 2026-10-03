"""Explicit model download; application startup never downloads model files."""
from app.service.knowledge_embedding import MODEL_CACHE, MODEL_ID, MODEL_REVISION


def main():
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=MODEL_ID, revision=MODEL_REVISION, cache_dir=str(MODEL_CACHE),
                      allow_patterns=["*.json", "*.txt", "*.safetensors", "sentencepiece.bpe.model"])
    print(f"Cached {MODEL_ID} at pinned revision {MODEL_REVISION}")


if __name__ == "__main__":
    main()
