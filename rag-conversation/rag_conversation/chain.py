import os
from operator import itemgetter
from langchain.vectorstores import Chroma
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema import format_document
from langchain.prompts.prompt import PromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough, RunnableParallel, RunnableMap

# Load
from langchain.document_loaders import WebBaseLoader
loader = WebBaseLoader("https://lilianweng.github.io/posts/2023-06-23-agent/")
data = loader.load()

# Split
from langchain.text_splitter import RecursiveCharacterTextSplitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
all_splits = text_splitter.split_documents(data)

# Add to vectorDB
dir = os.getcwd()
vectorstore = Chroma.from_documents(documents=all_splits, 
                                    persist_directory=dir,
                                    collection_name="rag-conversation",
                                    embedding=OpenAIEmbeddings(),
                                    )
retriever = vectorstore.as_retriever()

# Condense question prompt
_template = """Given the following conversation and a follow up question, rephrase the follow up question to be a standalone question, in its original language.
Chat History:
{chat_history}
Follow Up Input: {question}
Standalone question:"""
CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(_template)

# RAG answer synthesis prompt
template = """Answer the question based only on the following context:
{context}

Question: {question}
"""
ANSWER_PROMPT = ChatPromptTemplate.from_template(template)

# Conversational Retrieval Chain
DEFAULT_DOCUMENT_PROMPT = PromptTemplate.from_template(template="{page_content}")
def _combine_documents(docs, document_prompt = DEFAULT_DOCUMENT_PROMPT, document_separator="\n\n"):
    doc_strings = [format_document(doc, document_prompt) for doc in docs]
    return document_separator.join(doc_strings)

from typing import Tuple, List
def _format_chat_history(chat_history: List[Tuple]) -> str:
    buffer = ""
    for dialogue_turn in chat_history:
        human = "Human: " + dialogue_turn[0]
        ai = "Assistant: " + dialogue_turn[1]
        buffer += "\n" + "\n".join([human, ai])
    return buffer

_inputs = RunnableMap(
    standalone_question=RunnablePassthrough.assign(
        chat_history=lambda x: _format_chat_history(x['chat_history'])
    ) | CONDENSE_QUESTION_PROMPT | ChatOpenAI(temperature=0) | StrOutputParser(),
)
_context = {
    "context": itemgetter("standalone_question") | retriever | _combine_documents,
    "question": lambda x: x["standalone_question"]
}
conversational_qa_chain = _inputs | _context | ANSWER_PROMPT | ChatOpenAI()