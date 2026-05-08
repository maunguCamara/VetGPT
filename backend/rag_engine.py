"""
vetgpt/backend/rag_engine.py

Core RAG pipeline:
  1. Embed user query
  2. Retrieve top-k chunks from ChromaDB
  3. Build prompt with retrieved context
  4. Send to LLM (Claude or GPT-4o)
  5. Return answer + citations

Designed for async FastAPI usage.
"""

import time
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator

import anthropic
from openai import AsyncOpenAI
import httpx

from .config import get_settings
from ingestion.embedder import VetVectorStore

settings = get_settings()


# ──────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────

@dataclass
class Citation:
    """A single source citation from the RAG retrieval."""
    source_file: str
    document_title: str
    page_number: int
    score: float
    excerpt: str            # first 200 chars of the chunk

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "document_title": self.document_title,
            "page_number": self.page_number,
            "score": self.score,
            "excerpt": self.excerpt,
        }

    def format(self) -> str:
        """Human-readable citation string."""
        return f"{self.document_title}, p.{self.page_number}"


@dataclass
class RAGResponse:
    """Full RAG pipeline response."""
    query: str
    answer: str
    citations: list[Citation]
    chunks_retrieved: int
    top_score: float
    llm_model: str
    latency_ms: int
    disclaimer: str = (
        "⚠️ This is an AI-generated reference summary. "
        "Always verify with a licensed veterinarian before clinical decisions."
    )

    @property
    def formatted_references(self) -> str:
        """
        Numbered reference list for display, e.g.:
          [1] WikiVet — p.12
          [2] Merck Vet Manual — p.304
        """
        if not self.citations:
            return ""
        lines = []
        for i, c in enumerate(self.citations, 1):
            lines.append(f"[{i}] {c.document_title} — p.{c.page_number}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "formatted_references": self.formatted_references,
            "chunks_retrieved": self.chunks_retrieved,
            "top_score": self.top_score,
            "llm_model": self.llm_model,
            "latency_ms": self.latency_ms,
            "disclaimer": self.disclaimer,
        }


# ──────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are VetGPT, an AI veterinary reference assistant.
You answer questions for veterinary professionals using content from authoritative \
veterinary manuals, textbooks, and peer-reviewed sources.

LANGUAGE: Detect the language of the question and respond in that same language.
You are fluent in English, Swahili (Kiswahili), French, Arabic, Portuguese,
Spanish, and Chinese. If the question is in Swahili, answer in Swahili.
If in French, answer in French. If in English, answer in English. And so on.
Scientific and drug names should always remain in their standard Latin/English form.

CITATION FORMAT — CRITICAL:
- Each source passage is labelled [Source N: Title, p.X].
- Cite inline as [N] whenever you draw on a source.
- Example (English): "Canine parvovirus causes haemorrhagic enteritis [1]."
- Example (Swahili): "Virusi ya parvovirus husababisha kuhara kwa damu [1]."
- End every answer with a ## References section:
  [1] Title — p.X
  [2] Title — p.X

RULES:
1. Base your answer ONLY on the provided context passages.
   Mark anything from outside the context as [General knowledge].
2. Be precise and clinically accurate. Use correct veterinary terminology.
3. For dosages or drugs, cite the source and recommend confirming with
   current Plumb's Veterinary Drug Handbook or local formulary.
4. If the context lacks sufficient information, say so — do not hallucinate.
5. Structure longer answers with ## headings.
6. Never give a definitive diagnosis — you are a reference tool, not a clinician.
7. Always include ## References even for a single source.
"""


LANGUAGE_NAMES = {
    "en": "English", "sw": "Swahili (Kiswahili)", "fr": "French",
    "ar": "Arabic",  "pt": "Portuguese",          "es": "Spanish",
    "zh": "Chinese (Simplified)",
}

def build_prompt(query: str, chunks: list[dict], language: str | None = None) -> str:
    """
    Build the RAG prompt from the query and retrieved chunks.

    Labels each source [Source N] so the LLM can cite them inline.
    If `language` is specified, adds an explicit language instruction
    (in addition to the auto-detect instruction in the system prompt).
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("document_title", chunk.get("source_file", "Unknown"))
        page   = chunk.get("page_number", "?")
        score  = chunk.get("score", 0)
        context_parts.append(
            f"[Source {i}: {source}, p.{page} | relevance {score:.2f}]\n{chunk['text']}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    lang_instruction = ""
    if language and language in LANGUAGE_NAMES:
        lang_instruction = (
            f"\nIMPORTANT: The user has requested a response in "
            f"{LANGUAGE_NAMES[language]}. Write your entire answer in "
            f"{LANGUAGE_NAMES[language]}, keeping scientific/drug names in Latin/English.\n"
        )

    return f"""The following {len(chunks)} passages are from authoritative veterinary references.
Cite them inline as [1], [2], etc. and list them under ## References at the end.
{lang_instruction}
{context_block}

---

Veterinary question: {query}

Answer with inline citations [N] and a ## References section at the end:"""


# ──────────────────────────────────────────────
# RAG Engine
# ──────────────────────────────────────────────

class VetRAGEngine:
    """
    Retrieval-Augmented Generation engine for VetGPT.

    Instantiated once at app startup (singleton via lifespan).
    Thread-safe for async FastAPI usage.
    """

    def __init__(self):
        self._store = VetVectorStore(
            db_path=settings.chroma_db_path,
            collection_name=settings.chroma_collection_name,
        )
        self._anthropic = None
        self._openai = None
        self._init_llm_clients()

    def _init_llm_clients(self):
        """
        Initialise LLM clients based on config.

        Priority order:
          1. Ollama  (local, free — set LLM_PROVIDER=ollama in .env)
          2. Anthropic Claude (cloud)
          3. OpenAI GPT-4o   (cloud)

        Ollama setup:
          curl -fsSL https://ollama.ai/install.sh | sh
          ollama pull qwen2.5:14b        # recommended
          ollama pull qwen2.5:7b         # lighter (4.5 GB)
          Set in .env: LLM_PROVIDER=ollama
                       OLLAMA_MODEL=qwen2.5:14b
                       OLLAMA_BASE_URL=http://localhost:11434
        """
        if settings.anthropic_api_key:
            self._anthropic = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key
            )
        if settings.openai_api_key:
            self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        # Ollama client is stateless (plain HTTP) — no init object needed

    # ──────────────────────────────────────────
    # Main query method
    # ──────────────────────────────────────────

    async def query(
        self,
        query_text: str,
        top_k: int | None = None,
        filter_species: str | None = None,
        filter_source: str | None = None,
    ) -> RAGResponse:
        """
        Full RAG pipeline: retrieve → prompt → LLM → response.

        Args:
            query_text:      User's veterinary question.
            top_k:           Number of chunks to retrieve (default from config).
            filter_species:  Optional species filter e.g. "canine", "equine".
            filter_source:   Optional source filter e.g. "wikivet", "plumbs".

        Returns:
            RAGResponse with answer, citations, and metadata.
        """
        start = time.time()
        top_k = top_k or settings.rag_top_k

        # Step 1: Retrieve relevant chunks
        chunks = self._store.query(
            query_text=query_text,
            n_results=top_k,
            filter_source=filter_source,
        )

        # Filter by minimum score
        chunks = [c for c in chunks if c["score"] >= settings.rag_min_score]

        if not chunks:
            return RAGResponse(
                query=query_text,
                answer=(
                    "I couldn't find relevant information in the indexed veterinary "
                    "references for this query. Try rephrasing, or this topic may not "
                    "yet be in the knowledge base."
                ),
                citations=[],
                chunks_retrieved=0,
                top_score=0.0,
                llm_model="none",
                latency_ms=int((time.time() - start) * 1000),
            )

        # Step 2: Generate answer
        prompt = build_prompt(query_text, chunks)
        answer, model_used = await self._generate(prompt)

        # Step 3: Build citations
        citations = [
            Citation(
                source_file=c.get("source_file", ""),
                document_title=c.get("document_title", c.get("source_file", "")),
                page_number=c.get("page_number", 0),
                score=c["score"],
                excerpt=c["text"][:200],
            )
            for c in chunks
        ]

        latency = int((time.time() - start) * 1000)

        return RAGResponse(
            query=query_text,
            answer=answer,
            citations=citations,
            chunks_retrieved=len(chunks),
            top_score=chunks[0]["score"] if chunks else 0.0,
            llm_model=model_used,
            latency_ms=latency,
        )

    async def stream_query(
        self,
        query_text: str,
        top_k: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming version — yields answer tokens as they arrive.
        Used for the mobile app's real-time typing effect.
        """
        top_k = top_k or settings.rag_top_k
        chunks = self._store.query(query_text, n_results=top_k)
        chunks = [c for c in chunks if c["score"] >= settings.rag_min_score]

        if not chunks:
            yield "No relevant information found in the knowledge base."
            return

        prompt = build_prompt(query_text, chunks)

        if settings.llm_provider == "anthropic" and self._anthropic:
            async with self._anthropic.messages.stream(
                model=settings.llm_model_anthropic,
                max_tokens=settings.llm_max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        elif settings.llm_provider == "openai" and self._openai:
            stream = await self._openai.chat.completions.create(
                model=settings.llm_model_openai,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        elif settings.llm_provider == "ollama":
            # Ollama streaming — server-sent events from local Ollama server
            async for token in self._stream_ollama(prompt):
                yield token

    # ──────────────────────────────────────────
    # Private: LLM generation
    # ──────────────────────────────────────────

    async def _generate(self, prompt: str) -> tuple[str, str]:
        """
        Send prompt to configured LLM, return (answer, model_name).
        Falls back to OpenAI if Anthropic fails.
        """
        if settings.llm_provider == "anthropic" and self._anthropic:
            try:
                response = await self._anthropic.messages.create(
                    model=settings.llm_model_anthropic,
                    max_tokens=settings.llm_max_tokens,
                    temperature=settings.llm_temperature,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text, settings.llm_model_anthropic
            except Exception as e:
                if not self._openai:
                    raise RuntimeError(f"Anthropic failed and no OpenAI fallback: {e}")

        if self._openai:
            response = await self._openai.chat.completions.create(
                model=settings.llm_model_openai,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
            return response.choices[0].message.content, settings.llm_model_openai

        # Ollama — local LLM, no API key needed
        if settings.llm_provider == "ollama":
            return await self._generate_ollama(prompt)

        raise RuntimeError(
            "No LLM configured. Options:\n"
            "  Local (free): set LLM_PROVIDER=ollama, run: ollama pull qwen2.5:14b\n"
            "  Cloud: set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env"
        )

    async def _generate_ollama(self, prompt: str) -> tuple[str, str]:
        """Call local Ollama server (non-streaming)."""
        model    = settings.ollama_model
        base_url = settings.ollama_base_url

        payload  = {
            "model":  model,
            "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
            "options": {
                "temperature":    settings.llm_temperature,
                "num_predict":    settings.llm_max_tokens,
                "num_ctx":        8192,
                "repeat_penalty": 1.1,
            },
        }
        async with httpx.AsyncClient(timeout=360) as client:  # 6 min — covers cold model load
            resp = await client.post(f"{base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", ""), model

    async def _stream_ollama(self, prompt: str):
        """Stream tokens from local Ollama server."""
        model    = settings.ollama_model
        base_url = settings.ollama_base_url

        payload  = {
            "model":  model,
            "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
            "stream": True,
            "options": {
                "temperature":    settings.llm_temperature,
                "num_predict":    settings.llm_max_tokens,
                "num_ctx":        8192,
                "repeat_penalty": 1.1,
            },
        }
        async with httpx.AsyncClient(timeout=360) as client:  # 6 min — covers cold model load
            async with client.stream("POST", f"{base_url}/api/generate", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            chunk = __import__("json").loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
                            if chunk.get("done"):
                                break
                        except Exception:
                            continue

    async def warmup(self) -> None:
        """
        Pre-warm the Ollama model at startup.
        Sends a minimal prompt so the model loads into GPU/RAM before
        the first real user query. Prevents the 3-4 minute cold start.
        Called from main.py lifespan after engine is created.
        """
        if settings.llm_provider != "ollama":
            return
        try:
            print(f"⏳ Warming up Ollama ({settings.ollama_model}) — this may take 2-3 minutes on first load...")
            async with httpx.AsyncClient(timeout=360) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/generate",
                    json={
                        "model":  settings.ollama_model,
                        "prompt": "Ready.",
                        "stream": False,
                        "options": {"num_predict": 1},   # generate only 1 token — just loads model
                    },
                )
                if resp.status_code == 200:
                    print(f"✓ Ollama ({settings.ollama_model}) warmed up and ready.")
                else:
                    print(f"⚠️  Ollama warmup returned {resp.status_code} — queries may be slow on first use.")
        except Exception as e:
            print(f"⚠️  Ollama warmup failed: {e} — queries will be slow on first use.")

    def health(self) -> dict:
        """Return engine health status."""
        db_stats = self._store.stats()
        return {
            "chroma_chunks":   db_stats["total_chunks"],
            "llm_provider":    settings.llm_provider,
            "anthropic_ready": self._anthropic is not None,
            "openai_ready":    self._openai is not None,
            "ollama_ready":    settings.llm_provider == "ollama",
            "ollama_model":    settings.ollama_model if settings.llm_provider == "ollama" else None,
        }