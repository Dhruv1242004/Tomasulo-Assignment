# main.py
# Tomasulo algorithm simulator with 1 to 4 instructions issued per cycle.
#
# Usage:  python3 main.py [input file] [issue width] [max cycles]
#   input file   default: test_case.txt
#   issue width  1 to 4, overrides the value in the input file
#   max cycles   stop with an error if the program needs more (default 100000)

import sys

from init import read_input, Machine, SimError
from print_status import print_report
from issue import issue
from exe import exe
from mem import mem
from wb import wb
from commit import commit


def run(text, issue_width=None, max_cycles=100000):
    """Simulate a program given as text. Returns the finished Machine."""
    cfg, program = read_input(text, issue_width)
    for name in ('int_ex', 'fpadd_ex', 'fpmul_ex', 'ls_ex', 'ls_mem'):
        if getattr(cfg, name) < 1:
            raise SimError('%s must be at least 1' % name)
    m = Machine(cfg, program)

    while True:
        m.cycle += 1
        # last stage first: every stage only sees what earlier cycles produced
        commit(m)
        wb(m)
        mem(m)
        issue(m)
        exe(m)

        if not m.rob and not 0 <= m.pc < len(program):
            break                                   # program finished
        if m.cycle >= max_cycles:
            raise SimError('stopped after %d cycles, the program does not finish' % max_cycles)
        if m.cycle - m.last_commit_cycle > 10000:
            raise SimError('nothing committed for 10000 cycles (deadlock)')
    return m


def main(argv):
    name = argv[1] if len(argv) > 1 else 'test_case.txt'
    width = int(argv[2]) if len(argv) > 2 else None
    limit = int(argv[3]) if len(argv) > 3 else 100000
    try:
        with open(name) as f:
            text = f.read()
        m = run(text, width, limit)
    except (SimError, OSError, ValueError) as err:
        print('Error: %s' % err)
        return 1
    print_report(m)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
