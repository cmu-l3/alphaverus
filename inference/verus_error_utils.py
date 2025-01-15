import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ErrorBlock:
    type: str  # 'error' or 'note'
    error_type: str
    title: str
    message: str
    file: str
    start_line: int
    end_line: Optional[int] = None

def parse_error_message(error_message: str) -> List[ErrorBlock]:
    blocks = []
    lines = error_message.split('\n')
    
    block_pattern = re.compile(r'^(error|note)(\[*.*\]*): (.+)$')
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
                error_type=block_match.group(2),
                title=block_match.group(3),
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