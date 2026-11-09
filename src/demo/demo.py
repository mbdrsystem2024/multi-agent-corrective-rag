"""Линейное RAG-демо: оркестратор → поиск → критик → полнота → вывод."""

import csv
import json
import os
import sys
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field


QUESTION: str = "Какие 10 признаков низкой результативности сотрудника описаны в документах?"

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO.parent
PROMPTS = REPO / "prompts" / "demo"


class Plan(BaseModel):
    questions: list[str] = Field(min_length=1, description="Атомарные подвопросы")


class State(TypedDict):
    question: str
    questions: list[str]
    evidence: list[dict]
    draft: str
    review: str
    completeness: str
    answer: str


def prompt(name):
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def build_graph(model, vector_store):
    manifest = REPO / "data" / "raw" / "manifest.csv"
    urls = {}
    if manifest.is_file():
        with manifest.open(encoding="utf-8") as file:
            urls = {row["file"]: row["page_url"] for row in csv.DictReader(file)}

    def ask(instruction, data):
        return model.invoke([
            ("system", prompt("rules") + "\n" + prompt(instruction)),
            ("human", json.dumps(data, ensure_ascii=False)),
        ]).text

    def orchestrator(state):
        plan = model.with_structured_output(Plan).invoke([
            ("system", prompt("orchestrator")),
            ("human", state["question"]),
        ])
        return {"questions": plan.questions}

    def searcher(state):
        evidence = []
        for question in state["questions"]:
            chunks = []
            for doc in vector_store.similarity_search(question, k=4):
                meta = dict(doc.metadata)
                if meta.get("doc_id") in urls:
                    meta.setdefault("url", urls[meta["doc_id"]])
                chunks.append({
                    "id": f"{meta.get('doc_id', meta.get('source', 'unknown'))}:"
                          f"{meta.get('chunk_index', 'unknown')}",
                    "metadata": meta,
                    "text": doc.page_content,
                })
            evidence.append({"question": question, "chunks": chunks})
        draft = ask(
            "searcher",
            {"question": state["question"], "evidence": evidence},
        )
        return {"evidence": evidence, "draft": draft}

    def critic(state):
        review = ask(
            "critic",
            {"question": state["question"], "draft": state["draft"],
             "evidence": state["evidence"]},
        )
        return {"review": review}

    def completeness_checker(state):
        completeness = ask(
            "completeness_checker",
            {"question": state["question"], "questions": state["questions"],
             "review": state["review"], "evidence": state["evidence"]},
        )
        return {"completeness": completeness}

    def output(state):
        return {"answer": state["review"] + "\n\nПроверка полноты:\n"
                + state["completeness"]}

    graph = StateGraph(State)
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("searcher", searcher)
    graph.add_node("critic", critic)
    graph.add_node("completeness_checker", completeness_checker)
    graph.add_node("output", output)
    graph.add_edge(START, "orchestrator")
    graph.add_edge("orchestrator", "searcher")
    graph.add_edge("searcher", "critic")
    graph.add_edge("critic", "completeness_checker")
    graph.add_edge("completeness_checker", "output")
    graph.add_edge("output", END)
    return graph.compile()


def main(question: str):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")


    db_path = ROOT / "memory" / "chroma_db"


    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    store = Chroma(
        collection_name="handbook", embedding_function=embeddings,
        persist_directory=str(db_path), create_collection_if_not_exists=False,
    )

    model = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        temperature=0, max_retries=2, timeout=120,
    )
    
    graph = build_graph(model, store)
    for event in graph.stream({"question": question}, stream_mode="updates"):
        for node, update in event.items():
            print(f"\n--- {node} ---", flush=True)
            if node == "orchestrator":
                print("\n".join(f"- {q}" for q in update["questions"]), flush=True)
            elif node == "output":
                print(update["answer"], flush=True)


if __name__ == "__main__":
    main(QUESTION)
