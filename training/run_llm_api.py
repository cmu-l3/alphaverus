import openai
import os
from dotenv import load_dotenv
load_dotenv()

import pickle

import uuid
os.makedirs('dumps', exist_ok=True)


client_local = openai.Client(
    base_url="http://127.0.0.1:30000/v1", api_key="EMPTY")
client_openai = openai.Client(api_key=os.environ['OPENAI_API_KEY'])



def run_llm(history, model, max_tokens = 1024, temperature = 0.3, n = 8, port = 30000):
    if model == 'default':
        if port!=30000:
            client = openai.Client(base_url=f"http://127.0.0.1:{port}/v1", api_key="EMPTY")
        else: 
            client = client_local
    else:
        client = client_openai

    response = client.chat.completions.create(
        model='default', 
        messages = history,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        response_format={
            "type": "text"
        },
        n = n,
    )


    filename = 'dumps/' + str(uuid.uuid4()) + f'_{model}.json'
    with open(filename, 'wb') as f:
        pickle.dump(response, f)
        # Save the response.usage for future reference, and cost calculation.

    return [x.message.content for x in response.choices]
    
