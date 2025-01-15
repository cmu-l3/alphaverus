## A sample utility to find contamination in the benchmark and dafnybench
## Is required before running the evaluations.

from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import pickle
from tqdm import tqdm

load_dotenv()

client = OpenAI()
import json

import sys

he_prog1 = [x['y'] for x in [json.loads(x) for x in open('dataset_hints_fill_4nov_parts.jsonl')]]
he_prog2 = [x['y'] for x in [json.loads(x) for x in open('autoverusbench_cleaned.jsonl')]]

# Let's load the translated programs from different iterations
import json

progs = dict()
for f in [x for x in json.load(open('../verus_iterative_gpt_assisted26/histories/iter6.json'))['solved_pairs']]:
    progs[f[0].strip()] = open(f'../verus_iterative_gpt_assisted26/{f[1]}').read()


database = []
for i,x in enumerate(progs):
    database.append({
        'prog_num': i,
        'program_text': progs[x]
    })


all_outputs = dict()
for prog in tqdm(he_prog1+he_prog2):

  response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": f"Consider the follwoing set of program database:\n```json{json.dumps(database)}```\n\n## Task: Your task is to find the program that is same or very similar (>80%) to this program:\n```\n{prog}\n```\n You should start the solution, by first thinking which programs would be closest and why. Then, you should output the json, containing the same keys as above: prog_num, program_text. It is possible that none of the programs is closest, or even similar. In that case return empty json object."
          }
        ]
      }
    ],
    temperature=0.7,
    max_tokens=2048,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0,
    response_format={
      "type": "text"
    },
    n=4
  )
  print(response.usage)
  all_outputs[prog] = response

  pickle.dump(all_outputs, open(f'contam_analysis26.pkl', 'wb'))