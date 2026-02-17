import google.generativeai as genai


genai.configure(api_key="#################")


def analyze_with_gemini(context, query):
    template = f"""
You are a BGP routing analyst. Use the following context to address the tasks.

Context:
{context}

Tasks:
{query}

Answer:
"""

    # Step 3: Load model
    model = genai.GenerativeModel("models/gemini-2.0-flash")
    
    # Step 4: Generate response
    response = model.generate_content(template)

    # Step 5: Return result
    return response.text


#for model in genai.list_models():
#   print(model.name, model.supported_generation_methods)

#print(analyze_with_gemini("", "DO you understand this AS path [49673, 3216, 6762, 9498, 10075, 139026, 23923]?"))
