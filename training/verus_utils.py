import os

VERUS_PATH = os.getenv('VERUS_PATH', 'verus')  # Default to 'verus' if not set

def extract_code(res, add_main=True):
    start = res.find('```')
    end = res[start+3:].find('```')
    res_to_save = res[start + res[start:].find('\n'):start+3+end].strip()

    if add_main and res_to_save.find('main()')==-1:
        res_to_save += '\n\nfn main() {}'
    return res_to_save

def save_code_to_file(code, file_suffix = ''):
    with open(f'temp{file_suffix}.rs', 'w') as f:
        f.write(code)
    return f'temp{file_suffix}.rs'

def extract_and_save_code(res, file_suffix = ''):
    res_to_save = extract_code(res)
    return save_code_to_file(res_to_save, file_suffix)

def run_code(file_name, timeout_duration=10):
    import subprocess
    try:
        result = subprocess.run(
            [VERUS_PATH, file_name, '--multiple-errors', '100'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_duration  # Timeout in seconds
        )
        return result.stdout.decode('utf-8'), result.stderr.decode('utf-8')
    except subprocess.TimeoutExpired:
        return "", "Process timed out after {} seconds".format(timeout_duration)
