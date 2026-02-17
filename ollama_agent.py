import ollama

def analyze_with_ollama_model(model_name, context, query):

	template = f"""
		You are a BGP routing analyst. Use the following context to address the tasks.

		Context:
		{context}

		Tasks:
		{query}

		Answer:
	"""
	#print(template)
	response = ollama.generate(model_name, template).response
	return response

