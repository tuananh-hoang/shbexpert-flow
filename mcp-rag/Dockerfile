FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_DIR=/opt/fastembed_cache

COPY mcp-rag/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Bake the embedding model into the IMAGE at build time (build has network
# access; the running container in the demo VM may not — PRD 14.4 requires
# the demo to survive with no external internet). Without this, fastembed
# lazily downloads ~240MB from HuggingFace on first request, breaking the
# offline requirement and adding ~15s latency to whichever request is
# unlucky enough to trigger it. QdrantClient(":memory:") only initializes
# the local embedding backend — no real Qdrant server needed for this step.
RUN python3 -c "from qdrant_client import QdrantClient; QdrantClient(':memory:').set_model('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/opt/fastembed_cache')"

COPY mcp-rag/app/ /app/app/
COPY scripts/ /app/scripts/

EXPOSE 8201
CMD ["python", "-m", "app.server"]
