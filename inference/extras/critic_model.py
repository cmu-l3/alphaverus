from critique_prompt import prompt as critique_system_prompt
from run_llm_api import run_llm
from verus_utils import extract_code, run_code
import os
import random
import re
import pickle
def run_critic_model(prog, exemplars = []):
    

    pickle_file = 'critic_cache.pkl'
    if os.path.exists(pickle_file):
        with open(pickle_file, 'rb') as f:
            critic_cache = pickle.load(f)
    else:
        critic_cache = {}


    exemplar_string = ""

    if len(exemplars) > 100:
        import numpy as np
        np.random.shuffle(exemplars)
        exemplars = exemplars[:100]

    for x,y in exemplars:
        idx = x.rfind('fn ', 0, x.rfind('fn main()')) 
        idx2 = x.find('{', idx)    
        exemplar_string += f"### Input Problem:\n{x[:idx2+1].strip()}\n\n ### Trivial Solution:\n{y.strip()}\n\n"
    
    idx = prog.rfind('fn ', 0, prog.rfind('fn main()')) 
    idx2 = prog.find('{', idx)
    paran = '{}'
    history = [
        {
            'role' : 'system',
            'content' : critique_system_prompt.replace('<other_solutions_go_here>',exemplar_string)
        },
        {
            'role' : 'user',
            'content' : f'Consider the following program:\n```\n{prog[:idx2+1].strip()}\n```\n\nWrite a trivial program that passess the verification. Think of very simple trivial programs, such as returning the default value, returning empty list, return False, None, or sometimes based on a condition. Only output the additional code you write. Make sure to include the empty main function: fn main(){paran} as shown in examples. You can use array_variable.set(idx, value) to set the value of an array at a given index.' 
        }
    ]
    response = run_llm(history, 'default', n = 32, temperature=0.7, max_tokens = 256)
    all_faults = []
    for r in response:

        code = extract_code(history[-1]['content'], add_main=False) + extract_code(r)
        random_file_name = 'temp' + str(random.randint(100, 99999)) + '.rs'
        open(random_file_name, 'w').write(code)
        o, e = run_code(random_file_name)
        try:
            os.remove(random_file_name)
        except: ...
        num_verified = re.search(r'(\d+) verified', o)
        num_verified = int(num_verified.group(1)) if num_verified else 0

        num_errors = re.search(r'(\d+) errors', o)
        num_errors = int(num_errors.group(1)) if num_errors else 0

        if num_errors == 0 and num_verified > 0:
            all_faults.append(r)

    critic_cache[prog] = all_faults

    with open(pickle_file, 'wb') as f:
        pickle.dump(critic_cache, f)

    if len(all_faults) > 0:
        return True, all_faults
    return False, []