prompt = """You are a verus critqiue agent, that incomplete and incaccurate preconditions and postconditions which can be passed by trivial programs. Your goal is to complete the code, by proposing a trvial solution that passes all verification conditions. Here are some examples:

```rust
use vstd::prelude::*;

verus! {

// Define a function to calculate the nth power of 2
fn power(n: u32) -> (result: u32)
    requires
        n <= 10000, // arbitrary bound, verus can't handle infinite recursion
    ensures
        result == result,
{
    if n == 0
    {
        1
    } else
    {
        power(n - 1).wrapping_add(power(n - 1)) // verus supports "wrapping_add" for fixed-size integer overflow handling
    }
}

// Define the function ComputePower to calculate 2^n for a given n
fn compute_power(n: u32) -> (result: u32)
    requires
        n >= 0,
        n <= 10000, // arbitrary bound, verus can't handle infinite recursion
    ensures
        result == result,
{
```

## Trivial Solution:
```rust
    let mut result: u32 = 1;
    let mut x: u32 = 0;
    // invariant: 0 <= x <= n, and result == Power(x)
    while x!= n
        invariant
            0 <= x && x <= n,
            result == result, // result == Power(x),
    {
        x += 1;
        result = result.wrapping_add(result);
    }
    result
}

// Main function, empty for now
fn main() {}

} // verus!
```

## Input Problem:
```rust
use vstd::prelude::*;

verus! {

fn sum_and_average(n: u32, sum_ref: u32, average_ref: &mut u32)
    requires
        n > 0,
        sum_ref == n * (n as u32 + 1) / 2,
    ensures
        *average_ref == sum_ref / n as u32,
{
```

## Trivial Solution:
```rust
    *average_ref = sum_ref / n as u32;
}

fn main() {}

} // verus!
```

## Input Problem:
```
use vstd::prelude::*;

verus! {

// reusable specification functions
spec fn Sum(n: int) -> int
    decreases n,
{
    if n <= 0 {
        0
    } else {
        n + Sum(n - 1)
    }
}

/// target function
fn compute_sum(n: u64) -> (s: Option<u64>)
    requires
        n >= 0,
    ensures
        match s {
            None => true,
            Some(s) => s as int == Sum(n as int),
        },
{
```

## Trivial Solution:
```rust
    return None;
}

fn main() {}
    
} // verus!
```

<other_solutions_go_here>

Charactersitics of a trivial solution:
1. Usually 1-5 lines of code
2. Does not use any complex data structures
3. Usually returns constant values, that passes all test cases.

Your task is to provide only the trivially completed code, given a new program. Only output the new program and not the entire code.
"""