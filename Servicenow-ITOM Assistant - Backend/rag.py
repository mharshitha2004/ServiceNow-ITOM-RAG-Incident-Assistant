import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from retrieve import (
    retrieve_candidates,
    rerank_candidates,
    get_adjacent_context_chunks,
)

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from .env")

PRIMARY_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODELS = [
    name.strip()
    for name in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash").split(",")
    if name.strip() and name.strip() != "gemini-3.5-flash-lite"
]

# ---------------------------------------------------------------------------
# LLM with retry + fallback (replaces gemini_call.py's hand-rolled retry loop)
#
# .with_retry() retries the SAME model a few times with backoff on any
# exception (covers Gemini's transient 429/5xx errors, same as
# gemini_call.py's RETRYABLE_STATUS_CODES did explicitly). If every retry
# on the primary model still fails, .with_fallbacks() moves on to the next
# model in FALLBACK_MODELS, in order.
#
# One behavior difference from gemini_call.py, worth knowing: the original
# code distinguished retryable (429/5xx) from permanent errors (e.g. a bad
# API key) and only retried/fell back on the former, raising permanent
# errors immediately. LangChain's with_retry() retries on any exception
# by default, so a permanent error now also burns through retries (and the
# fallback chain) before surfacing - a few extra seconds of delay on a
# genuinely broken config, not a change in the final result.
# ---------------------------------------------------------------------------


def _make_llm(model_name: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key).with_retry(
        stop_after_attempt=3,
        wait_exponential_jitter=True,
    )


_primary_llm = _make_llm(PRIMARY_MODEL)
_fallback_llms = [_make_llm(name) for name in FALLBACK_MODELS]

llm = _primary_llm.with_fallbacks(_fallback_llms) if _fallback_llms else _primary_llm

PROMPT_TEXT = """
You are a ServiceNow ITOM documentation assistant.

Answer the user's question using ONLY the provided documentation context.

CORE INSTRUCTIONS:
- Follow the terminology, organization, and meaning used in the documentation.
- Do not invent, assume, or add technical details not supported by the context.
- Do not fill gaps using general knowledge.
- Keep the answer clear, beginner-friendly, and sufficiently detailed.

COMPLETENESS:
- Identify every part of the user's question before answering.
- Answer each part separately.
- If the question asks for a comparison, identify and explain EVERY relevant comparison category found in the context.
- If the context contains a table, cover all relevant rows and columns, including information continued in adjacent chunks.
- Do not omit relevant details simply to make the answer shorter.
- Do not repeat the same information unnecessarily.
- If a requested detail is missing from the context, explicitly state that it is not available in the provided context.

STRUCTURE:
- Use headings and bullet points where appropriate.
- If the documentation identifies N phases, provide exactly N separately numbered phases.
- Give each phase its own heading and explanation.
- Do not combine distinct phases, steps, or concepts into one item.
- For comparisons, use a table when it improves clarity.
- If a phase or concept is mentioned but not sufficiently explained in the context, state that the context does not explain it fully.

ACCURACY:
- Preserve technical terms and acronyms exactly as written in the context.
- Do not alter terms such as CI, CIs, CMDB, MID Server, or ITOM.
- Do not change the meaning of technical statements.
- Before responding, check that the answer is consistent with the provided context.
- Correct spelling errors without changing technical terminology.

FINAL CHECK:
Before returning the answer, silently verify:
1. Have I answered every part of the user's question?
2. Have I included all relevant details from the context?
3. Have I covered every relevant comparison category or listed item?
4. Have I avoided unsupported claims?
5. Have I preserved the documentation's terminology?

Return only the final answer.

Documentation context:
{context}

User question:
{question}
"""

# {context} and {question} are filled in at .invoke() time - no manual
# string formatting, so there is no risk of forgetting to escape braces in
# the prompt text (it happens to have none, but future edits are safe now).
_prompt = ChatPromptTemplate.from_template(PROMPT_TEXT)
_chain = _prompt | llm | StrOutputParser()


def _format_chunk_header(chunk: dict) -> str:
    metadata = chunk.get("metadata", {})
    chunk_id = chunk.get("chunk_id", "Unknown")

    # PDF chunks carry page numbers; web-scraped chunks (see
    # ingestion/scrape_servicenow_sources.py) carry a title + URL instead
    # (page_start is the string "N/A" for those). Format whichever this
    # chunk actually has, so citations stay meaningful either way.
    page_start = metadata.get("page_start", metadata.get("page", "Unknown"))

    if page_start not in ("N/A", None):
        page_end = metadata.get("page_end", page_start)
        return f"[Chunk {chunk_id} | PDF pages {page_start}-{page_end}]"

    title = metadata.get("title")
    source = metadata.get("source", "Unknown source")
    if title:
        return f"[Chunk {chunk_id} | {title} | {source}]"
    return f"[Chunk {chunk_id} | {source}]"


def generate_answer(question, retrieved_chunks):
    if not retrieved_chunks:
        return "I couldn't find relevant information in the ServiceNow documentation."

    context_parts = []

    for item in retrieved_chunks:
        text = item.get("text", "")
        context_parts.append(f"{_format_chunk_header(item)}\n{text}")

    context = "\n\n".join(context_parts)

    response = _chain.invoke({"context": context, "question": question})

    return response or "Gemini did not return a text response."


def answer_question(question):
    print("\nSearching ServiceNow documentation...")

    candidates = retrieve_candidates(question)

    print(f"Retrieved {len(candidates)} candidates from Pinecone.")

    reranked = rerank_candidates(question, candidates)

    context_chunks = get_adjacent_context_chunks(
        reranked,
        question=question,
        neighbors_per_seed=2,
        # Was 12 - the retrieve.py fix raised the useful default to 24
        # (forward continuation + document-order sorting so a multi-step
        # procedure isn't truncated or scattered), but this explicit
        # argument was silently overriding that default back down. See
        # the "Chunks sent to Gemini" log line to confirm this actually
        # takes effect (should read up to 24, not 12).
        max_context_chunks=24,
    )

    print(f"Reranked seed chunks: {len(reranked)}")
    print(f"Chunks sent to Gemini, including neighbors: {len(context_chunks)}")

    answer = generate_answer(question, context_chunks)

    print("\n" + "=" * 70)
    print("GEMINI ANSWER")
    print("=" * 70)
    print(answer)
    return answer


if __name__ == "__main__":
    print("\nServiceNow ITOM RAG Assistant")
    print("Type 'exit' to stop.")

    while True:
        question = input("\nAsk a ServiceNow ITOM question: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        if not question:
            print("Please enter a question.")
            continue

        try:
            answer_question(question)
        except Exception as error:
            print("Error:", error)