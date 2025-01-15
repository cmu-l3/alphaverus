import pandas as pd
import json
from openai import OpenAI
import openai
from dotenv import load_dotenv
load_dotenv()
client = openai.Client(base_url=f"http://127.0.0.1:30000/v1", api_key="EMPTY")
from tqdm import tqdm
import pickle


# Regex of form: The answer is [Yes/No]
import re
def extract_answer(response, choice_idx = 0):
  try:
    # return re.search(r'the answer is (yes|no)', response.choices[choice_idx].message.content.lower()).group(1)
    return re.findall(r'the final answer is <(yes|no)>', response.choices[choice_idx].message.content.lower())[-1]
  except:
    try:
        return re.findall(r'the final answer is (yes|no)', response.choices[choice_idx].message.content.lower())[-1]
    except:
        try:
            return re.findall(r'the final answer is "(yes|no)"', response.choices[choice_idx].message.content.lower())[-1]
        except:
            try:
                return re.findall(r'the final answer is <(yes|no)', response.choices[choice_idx].message.content.lower())[-1]
            except:
                try:
                    return re.findall(r'the final answer is \*\*(yes|no)', response.choices[choice_idx].message.content.lower())[-1]
                except:
                    return "EMPTY"



def check_pairs(pairs, use_cache = True):
    # TODO: Any kind of lock logic
    print("Checking pairs")
    try:
        if use_cache:
            cache = pickle.load(open("openai_cache.pkl", "rb"))
        else:
            cache = dict()
    except:
        cache = dict()
    all_responses = []
    for x,y in tqdm(pairs):
        dafny_code = x
        rust_code = y

        if cache.get((dafny_code, rust_code)):
            print('Cache hit')
            all_responses.append(cache[(dafny_code, rust_code)])
            continue

        rust_code_uncommented = '\n'.join([line for line in rust_code.splitlines() if line.strip() and not line.strip().startswith("//")])

        response = client.chat.completions.create(
            # model="chatgpt-4o-latest",
            # model = 'gpt-4o',
            model = 'default',
            # model = 'gpt-4o-mini',
            messages=[
            {
                "role": "user",
                "content": [
                {
                    "type": "text",
                    "text": f"Consider the following function:\n```rust\n{rust_code_uncommented.strip()}\n\n```\nand\n\n```dafny\n{dafny_code.strip()}\n```\n\nWill the two methods return computationally same results? Ignore the correctness or interference by proof statements. Minor differences such as overflows, corner cases can be ignored. Remember, comments should be ignored. Differences in return behavior may be ignored. For instance, if Program 1 (rust code) returns an err type or something similar for corner cases, while Program 2 (dafny code) returns -1, None or something similar, the two programs are still considered same and answer should be <Yes>. If Program 1 (rust code) is more general than Program 2 (dafny code), then also, they are considered same, and return answer <Yes>. Further, if Program 1 (rust code) has added an additional condition to ensure that overflows are not encountered, then also, they are considered same, and return answer <Yes>. However, trivial preconditions such as setting max length of an array to a very small number such as less than 3 is not permitted, and answer should be <No>. Follow the following format:\n[What Program 1 (rust code) Does]\n[What Program 2 (dafny code) Does]\n[Step by Step Thoughts on comparison between methods]\n[Is Program 1 (rust code) more general than Program 2 (dafny code)?]\nFinally, answer in format: The final answer is <>.\n\nStart thinking."
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
            n=8
        )
        print(response.usage)
        all_responses.append(response)
        cache[(dafny_code, rust_code)] = response

    faulty_pairs = []

    if use_cache:
        pickle.dump(cache, open("openai_cache.pkl", "wb"))

    for i,response in enumerate(all_responses):
        no_counts = 0
        yes_counts = 0
        for x in range(8):
            ans = extract_answer(response, x)
            if ans=='no': no_counts+=1
            if ans=='yes': yes_counts+=1
            # if ans=='no': faulty_pairs.append(i)
        # if no_counts>=2 or (no_counts==1 and yes_counts<=2): faulty_pairs.append(i)
        if no_counts>=yes_counts: faulty_pairs.append(i)
        if no_counts>=3: faulty_pairs.append(i)

    return faulty_pairs