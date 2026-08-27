import requests

def analyze_with_ChatOpenAI_model(model_name, context, query):
    url = 'http://localhost:8000/v1/chat/completions'
    headers = {"Authorization": "Bearer EMPTY"}  # API key not required locally if using vLLM default
    
    template = f"""You are a BGP routing analyst. Use the following context to address the tasks.
Context:
{context}
Tasks:
{query}
Answer:
"""

    data = {
        "model": model_name,
        "messages": [
                {"role": "user", "content": template}
            ],
            #"max_tokens": 1024,
            "temperature": 0.0
    }

    response = requests.post(url, json=data, verify=False)  # verify=False if using self-signed cert
    result = response.json()
    raw_text = result['choices'][0]['message']['content']
    return raw_text
