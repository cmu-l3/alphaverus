from openai import OpenAI
import openai
import json
import argparse
from typing import List, Tuple
import pickle
import random
from verus_utils import run_code, extract_code
from tqdm import tqdm
import uuid
import os



VERUS_FILE_SUFFIX = str(random.randint(0, 10000))

def check_pairs(prog):
    idx = prog.rfind('fn ', 0, prog.rfind('fn ')) 
    main_idx = prog.find('fn main()')
    # Find first {, replace with "assert false"
    idx2 = prog.find('{', idx)
    prog_require = prog[:idx2] + '{\n\tassert (false);\n' + prog[idx2+1:]
    random_file_name = f'temp{str(random.randint(0, 10000))}.rs'
    open(random_file_name,'w').write(prog_require)
    o,e = run_code(random_file_name)
    if '0 errors' in o:
        try: os.remove(random_file_name)
        except: ...
        return True

    prog_ensure = prog[:idx2] +'{}'+prog[main_idx:]
    open(random_file_name,'w').write(prog_ensure)
    o,e = run_code(random_file_name)
    try: os.remove(random_file_name)
    except: ...
    import re
    num_verified = re.search(r'(\d+) verified', o)
    num_verified = int(num_verified.group(1)) if num_verified else 0
    if '0 errors' in o and num_verified > 0:
        return True
    return False

def check_pairs_loop(prog):
    prog = '\n'.join([x for x in prog.split('\n') if x!=''])
    idx = prog.rfind('fn ', 0, prog.rfind('fn ')) 
    main_idx = prog.find('fn main()')
    function_of_concern = prog[idx:main_idx]
    last_bracket = function_of_concern[:function_of_concern.rfind('}')].rfind('}')

    lines = function_of_concern[:last_bracket+1].split('\n')
    final_code = prog[:idx] + '\n'.join(lines[:-2] + ['assert(false);'] + lines[-2:]) + function_of_concern[last_bracket+1:] + prog[main_idx:]

    random_file_name = f'temp{str(random.randint(0, 10000))}.rs'
    open(random_file_name,'w').write(final_code)
    o,e = run_code(random_file_name)
    try: os.remove(random_file_name)
    except: ...
    if '0 errors' in o and '0 verified' not in o:
        return True

    last_bracket = function_of_concern.rfind('}')
    lines = function_of_concern[:last_bracket+1].split('\n')
    final_code = prog[:idx] + '\n'.join(lines[:-2] + ['assert(false);'] + lines[-2:]) + function_of_concern[last_bracket+1:] + prog[main_idx:]
    random_file_name = f'temp{str(random.randint(0, 10000))}.rs'
    open(random_file_name,'w').write(final_code)
    o,e = run_code(random_file_name)
    try: os.remove(random_file_name)
    except: ...
    if '0 errors' in o and '0 verified' not in o:
        return True
    return False

def main(config):


    SAVE_DIR = config['SAVE_DIR']
    PROMPT_RANDOM_EXAMPLES : List[Tuple[str, str]] = config['PROMPT_RANDOM_EXAMPLES']
    PROGRAMS_FILE = config['PROGRAMS_FILE']
    MODEL = config['MODEL_NAME']
    temperature = config['CONVERT']['TEMPERATURE']
    batch_size = config['BATCH_SIZE'] 
    contam_exclude = config['contam_exclude']   

    contam_exclude = {k.strip():v for k,v in contam_exclude.items()}


    programs = [json.loads(x)['x'].strip() for x in open(PROGRAMS_FILE).readlines()]
    ys = [json.loads(x)['y'].strip() for x in open(PROGRAMS_FILE).readlines()]

    def pull_random_examples(df_prog):
        import random
        if df_prog in contam_exclude:
            print('Deleting an exemplar')
            to_remove = contam_exclude[df_prog.strip()]
            prompt_random_examples = [x for x in PROMPT_RANDOM_EXAMPLES if x.strip()!=to_remove.strip()]
            print('Deleted from', len(PROMPT_RANDOM_EXAMPLES), 'to', len(prompt_random_examples))
        else:
            prompt_random_examples = PROMPT_RANDOM_EXAMPLES
        choices = random.sample(prompt_random_examples, k=len(prompt_random_examples)//2)

        messages = []
        for i,choice in enumerate(choices):
            idx = choice[:choice.find('fn main()')].rfind('fn ') 
            non_body_code = choice[:idx+choice[idx:].find('\n{')+2].strip()
            completion = choice[idx+choice[idx:].find('\n{')+3:].strip()

            messages.append({
                "role": "user",
                "content": f"Consider the following verus code:\n```{non_body_code}```\n\nThe code contains the relevant spec functions and the preconditions (requires) and postconditions (ensures) for the main function. Your goal is to complete the function, by adding necessary procedure, along with proof statements (such as invariants, asserts, proof blocks etc) to prove the program. Only output the new program and not the entire code. You are not allowed to create new functions, however can use any functions already defined if within the scope. Remember to just output the completion without the function signature, requires and ensures. Only the body of the function is required. Remember to end in: \n```rust\n{paran_close} // End of function\n{paran_close} // verus!\nfn main() {paran}\n```\n\n"
            })
            messages.append({
                "role": "assistant",
                "content": f"```rust\n{completion}\n```"
            })
        return messages

    solved_programs = []

    for prog_num, program in enumerate(programs):

        client = openai.Client(
            base_url="http://127.0.0.1:30000/v1", api_key="EMPTY")

        paran = '{}'
        paran_close = '}'
        model = MODEL #'default'

        messages=[
            {
                "role": "system",
                "content": open('final_system_prompt.rs').read() 
            },
            {
                "role": "user",
                "content": [
                {
                    "type": "text",
                    "text": f"Consider the following incomplete verus code:\n```{program}\n```\n\nThe code contains the relevant spec functions and the preconditions (requires) and postconditions (ensures) for the main function. Your goal is to complete the function, by adding necessary procedure, along with proof statements (such as invariants, asserts, proof blocks etc) to prove the program. Only output the new program and not the entire code. You are not allowed to create new functions, however can use any functions already defined if within the scope. Remember to just output the completion without the function signature, requires and ensures. Only the body of the function is required. Remember to end in: \n```rust\n{paran_close} // End of function\n{paran_close} // verus!\nfn main() {paran}\n```\n\n"
                }
                ]
            }
        ]
        if len(PROMPT_RANDOM_EXAMPLES)>0:
            messages = messages[:1] + pull_random_examples(ys[prog_num]) + messages[1:]
        print('going to call openai')
        response = client.chat.completions.create(
            model=model,
            messages = messages,
            temperature=temperature,
            max_tokens=1024,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={
            "type": "text"
            },
            n=batch_size
        )
        print('called openai')

        select_uuid = str(uuid.uuid4())
        dumped_filename = 'dumped_generations/' + select_uuid + f'_{model.split("/")[-1]}.pkl'

        with open(dumped_filename, 'wb') as f:
            pickle.dump(response, f)


        all_errs = []
        all_outs = []
        num_verifies = []
        good_indexes = []
        for _ in tqdm(range(len(response.choices))):
            ec = extract_code(response.choices[_].message.content)
            if ec.strip().startswith('{'):
                ec = ec.strip()[1:]
            code = program + ec.strip()

            file_name = f'temp{VERUS_FILE_SUFFIX}.rs'
            open(file_name, 'w').write(code)
            output, err = run_code(file_name)

            if err.find('the name `main` is defined multiple times')!=-1:
                last_main_idx = code.rindex('fn main() {}')
                code = code[:last_main_idx] + code[last_main_idx + len('fn main() {}'):]
                open(file_name, 'w').write(code)
                output, err = run_code(file_name)
            
            print(err)
            print('\n'*5)

            extracted_code = code

            import re
            num_verified = re.search(r'(\d+) verified', output)
            num_verified = int(num_verified.group(1)) if num_verified else 0

            num_errors = re.search(r'(\d+) errors', output)
            num_errors = int(num_errors.group(1)) if num_errors else 0

            os.makedirs(f'{SAVE_DIR}/dumps', exist_ok=True)
            with open(f'{SAVE_DIR}/dumps/verified_prog={prog_num}_{num_verified}_{num_errors}_' + f'{select_uuid}_{_}' + '.rs', 'w') as f:
                f.write(extracted_code)

            if extracted_code.count('assume')>0:
                num_verifies.append(-1)
                continue
            # Remove all white spaces
            if extracted_code.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').find('ensurestrue')!=-1:
                num_verifies.append(-1)
                continue

            extracted_code_uncommented = '\n'.join([line for line in extracted_code.splitlines() if line.strip() and not line.strip().startswith("//")])
            if len(extracted_code_uncommented.splitlines())<(len([x for x in extracted_code.splitlines() if x.strip()!=''])//2):
                # This means, there are lot of comments in the code, that is going to mislead the gpt verifier
                num_verifies.append(-1)
                continue

            if extracted_code_uncommented.find('ensures')==-1:
                num_verifies.append(-1)
                continue

            if extracted_code_uncommented.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').count('{}') >= 2 + program.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', '').count('{}'):
                num_verifies.append(-1)
                continue

            if extracted_code.find('#[verifier::external]')!=-1:
                num_verifies.append(-1)
                continue

            if extracted_code.find('#[verifier::external_body]')!=-1:
                num_verifies.append(-1)
                continue

            if err.find('warning: unreachable statement')!=-1:
                num_verifies.append(-1)
                continue

            import re

            def is_valid_string(s):
                # Pattern to find '&mut' not followed by 'Vec', allowing for optional spaces
                pattern_invalid_ampersand_mut = r'&mut(?!\s*Vec\b)'
                
                if re.search(pattern_invalid_ampersand_mut, s):
                    return False  # Invalid if '&mut' not followed by 'Vec' is found
                return True  # Valid string

            if not is_valid_string(extracted_code):
                num_verifies.append(-1)
                continue
            

            if num_verified==1 and num_errors==0:
                num_verifies.append(-1)
                continue
            if num_verified!=0 or num_errors!=0:
                print(num_verified, num_errors)
                good_indexes.append(_)
                # Save in a file
                # Create the directory if it does not exist
                os.makedirs(f'{SAVE_DIR}', exist_ok=True)
                with open(f'{SAVE_DIR}/verified_prog={prog_num}_{num_verified}_{num_errors}_' + f'{select_uuid}_{_}' + '.rs', 'w') as f:
                    f.write(extracted_code)
            num_verifies.append(num_verified)

            # Do a regex search for <number> verified
            if num_verified>0 and num_errors==0:
                solved_programs.append((prog_num, program, extracted_code))
            
            all_errs.append(err)
            all_outs.append(output)
        print(len(good_indexes), [num_verifies[_] for _ in good_indexes])
        # Delete the file_name
        try: os.system(f'rm -f {file_name}')
        except: ...
    return solved_programs


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--SAVE_DIR', type=str, default='solved_programs_hev')
    parser.add_argument('--PROMPT_RANDOM_EXAMPLES', type=str, default='../training/iter5.json')
    parser.add_argument('--BASE_PATH', type=str, default='../training/')
    parser.add_argument('--PROGRAMS_FILE', type=str, default='datasets/hev.jsonl')
    parser.add_argument('--model', type=str, default='default')
    parser.add_argument('--temperature', type=float, default=0.7)
    parser.add_argument('--batch_size', type=int, default=32)
    
    args = parser.parse_args()

    config = {
        'SAVE_DIR': args.SAVE_DIR,
        'PROMPT_RANDOM_EXAMPLES': json.load(open(args.PROMPT_RANDOM_EXAMPLES)),
        'PROGRAMS_FILE': args.PROGRAMS_FILE,
        'MODEL_NAME': args.model,
        'CONVERT': {
            'TEMPERATURE': args.temperature
        },
        'BATCH_SIZE': args.batch_size
    }

    config['contam_exclude'] = json.load(open('contam_exclude26.json'))

    exemplars = []
    for x,y in config['PROMPT_RANDOM_EXAMPLES']['solved_pairs']:
        code = open(os.path.join(args.BASE_PATH, y)).read()
        exemplars.append(code)
    config['PROMPT_RANDOM_EXAMPLES'] = exemplars

    main(config)