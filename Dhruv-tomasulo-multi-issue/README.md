# Tomasulo simulator with multiple issue

A Python simulator of an out-of-order processor with Tomasulo's algorithm, a reorder
buffer, a load/store queue and branch prediction. It can issue 1 to 4 instructions per cycle.

## Run it

    cd code
    python3 main.py                       # runs test_case.txt
    python3 main.py ../tests/t04_branches.txt 3     # file, issue width
    python3 main.py ../tests/t10_cdb_limit.txt 4 500   # file, width, max cycles

Needs only Python 3 (no extra packages).

## Input file

Hardware table (rs / EX cycles / MEM cycles / units), then optional lines:
`ROB entries = N`, `Issue width = N` (1-4), `Commit width = N`, `CDB width = N`,
`Load speculation = on|off`, register values (`R1=10, F2=3.5`), memory values
(`Mem[8]=2.5`), and then one instruction per line. Branch offsets count instructions.
Memory addresses are 0..255.

## Output

The table of cycles for every instruction (ISSUE, EX, MEM, WB, COMMIT; an instruction that
is executed again after a recovery shows several entries), counters (IPC, branches,
mispredictions, load/store order violations), the registers and the non-zero memory.

## Files

- `code/` - the simulator (`init.py` parsing and data, `issue.py`, `exe.py`, `mem.py`,
  `wb.py`, `commit.py`, `recover.py`, `print_status.py`, `main.py`, `data_structure.txt`)
- `tests/t01 ... t10` - my test programs; each file starts with a comment saying what it tests
- `tests/run_tests.py` - runs all tests at widths 1-4, checks them, saves `tests/results/`
- `tests/check.py` - a plain sequential interpreter plus a timing-rule checker
- `tests/fuzz.py` - random programs; `python3 fuzz.py 200` checks 200 programs at all widths
- `REPORT.md` / `REPORT.pdf` - the report
