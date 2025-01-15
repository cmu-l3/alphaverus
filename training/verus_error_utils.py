import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ErrorBlock:
    type: str  # 'error' or 'note'
    title: str
    message: str
    file: str
    start_line: int
    end_line: Optional[int] = None

def parse_error_message(error_message: str) -> List[ErrorBlock]:
    blocks = []
    lines = error_message.split('\n')
    
    block_pattern = re.compile(r'^(error|note): (.+)$')
    file_line_pattern = re.compile(r'^  --> (.+):(\d+):(\d+)$')
    message_start_pattern = re.compile(r'^   \|$')
    message_end_pattern = re.compile(r'^   = .+$')
    
    current_block = None
    message_lines = []
    in_message = False

    for line in lines:
        block_match = block_pattern.match(line)
        if block_match:
            if current_block:
                current_block.message = '\n'.join(message_lines).strip()
                blocks.append(current_block)
            
            current_block = ErrorBlock(
                type=block_match.group(1),
                title=block_match.group(2),
                message='',
                file='',
                start_line=0
            )
            message_lines = []
            in_message = False
            continue

        file_line_match = file_line_pattern.match(line)
        if file_line_match and current_block:
            current_block.file = file_line_match.group(1)
            current_block.start_line = int(file_line_match.group(2))
            continue

        if message_start_pattern.match(line):
            in_message = True
            continue

        if message_end_pattern.match(line):
            in_message = False
            continue

        if in_message:
            message_lines.append(line)

        end_line_match = re.match(r'^(\d+) \|', line)
        if end_line_match and current_block:
            current_block.end_line = int(end_line_match.group(1))

    if current_block:
        current_block.message = '\n'.join(message_lines).strip()
        blocks.append(current_block)

    return blocks

def count_errors(blocks: List[ErrorBlock]) -> int:
    return sum(1 for block in blocks if block.type == 'error')


if __name__ == '__main__':
    # Example usage
    error_message = """
error: postcondition not satisfied
  --> temp.rs:19:1
   |
17 | /         r <==> !(forall|i: int|
18 | |             0 <= i <= operation.len() ==> sum(#[trigger] operation@.subrange(0, i)) >= 0),
   | |_________________________________________________________________________________________- failed this postcondition
19 | / {
20 | |     // We use i128 since it allows us to have sufficiently large numbers without overflowing.
21 | |     let mut s = 0i128;
22 | |     for i in 0usize..operation.len()
...  |
34 | |     false
35 | | }
   | |_^ at the end of the function body
error: invariant not satisfied at end of loop body
  --> temp.rs:25:13
   |
25 |             s == sum(operation@.subrange(0, i as int)) as i128,
   |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
note: recommendation not met: value may be out of range of the target type (use `#[verifier::truncate]` on the cast to silence this warning)
  --> temp.rs:25:18
   |
25 |             s == sum(operation@.subrange(0, i as int)) as i128,
   |                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
error: possible arithmetic underflow/overflow
  --> temp.rs:29:13
   |
29 |         s = s + operation[i] as i128;
   |             ^^^^^^^^^^^^^^^^^^^^^^^^
error: postcondition not satisfied
  --> temp.rs:31:13
   |
17 | /         r <==> !(forall|i: int|
18 | |             0 <= i <= operation.len() ==> sum(#[trigger] operation@.subrange(0, i)) >= 0),
   | |_________________________________________________________________________________________- failed this postcondition
...
31 |               return true;
   |               ^^^^^^^^^^^ at this exit
error: aborting due to 4 previous errors
"""

    parsed_blocks = parse_error_message(error_message)
    error_count = count_errors(parsed_blocks)

    print(f"Total errors: {error_count}")
    for block in parsed_blocks:
        print(f"\nType: {block.type}")
        print(f"Title: {block.title}")
        print(f"File: {block.file}")
        print(f"Start line: {block.start_line}")
        print(f"End line: {block.end_line}")
        print(f"Message:\n{block.message}")