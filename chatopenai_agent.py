from langchain_openai import ChatOpenAI


def analyze_with_ChatOpenAI_model(model_name, context, query):
    llm = ChatOpenAI(
        model=model_name,
        openai_api_key="EMPTY",                 # vLLM ignores the key
        openai_api_base="http://localhost:8000/v1",  # your vLLM server
        #max_tokens = 1024,
        temperature=0.0
    )

    template = f"""
You are a BGP routing analyst. Use the following context to address the tasks.

Context:
{context}

Tasks:
{query}

Answer:
"""
    response = llm.invoke(str(template))

    return response.content
