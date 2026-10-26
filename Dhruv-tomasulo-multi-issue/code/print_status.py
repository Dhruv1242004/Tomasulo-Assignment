# print_status.py
# Printing: the instruction status table, the registers and the memory.

def ps(unit):
    """Print every field of every item of a list (debug helper from the starter)."""
    if len(unit) == 0:
        print('empty!')
    else:
        for item in unit:
            print('******')
            for field, value in vars(item).items():
                print(field + ': ', str(value))


def pss(item):
    """Print every field of one item (debug helper from the starter)."""
    for field, value in vars(item).items():
        print(field + ': ', str(value))


def fmt(v):
    """Short text for a register or memory value."""
    if isinstance(v, float):
        s = ('%.6f' % v).rstrip('0')
        if s.endswith('.'):
            s += '0'
        return '0.0' if s == '-0.0' else s
    return str(v)


def _span(a, b):
    return '[]' if a is None else '[%d, %d]' % (a, b)


def _one(x):
    return '[]' if x is None else '[%d]' % x


def print_table(rows):
    print(''.ljust(30) + 'ISSUE'.ljust(12) + 'EX'.ljust(12) + 'MEM'.ljust(12) +
          'WB'.ljust(10) + 'COMMIT')
    for e in rows:
        print(e.ins.text.ljust(30) + _one(e.issue).ljust(12) + _span(e.ex_start, e.ex_end).ljust(12) +
              _span(e.mem_start, e.mem_end).ljust(12) + _one(e.wb).ljust(10) + _one(e.commit))


def print_registers(regs):
    print('REGISTER VALUES')
    for kind in ('R', 'F'):
        for first in range(0, 32, 8):
            names = [kind + str(i) for i in range(first, first + 8)]
            print('        ' + ''.join(n.ljust(10) for n in names))
            print('value:  ' + ''.join(fmt(regs[n]).ljust(10) for n in names))
        print()


def print_memory(memory):
    print('NON-ZERO MEMORY VALUES')
    print('Addresses'.ljust(12) + 'Values')
    for a in sorted(memory):
        if memory[a] != 0:
            print(str(a).ljust(12) + fmt(memory[a]))


def print_report(m):
    print_table(m.done_rows)
    print()
    n = len(m.done_rows)
    cycles = m.last_commit_cycle
    print('Instructions committed: %d    Cycles: %d    IPC: %.3f    Issue width: %d' %
          (n, cycles, n / cycles if cycles else 0.0, m.cfg.issue_width))
    print('Branches: %d    Mispredicted: %d    Load/store order violations: %d    Squashed instructions: %d' %
          (m.n_branches, m.n_mispredicts, m.n_violations, m.n_squashed))
    for line in m.events:
        print('  ' + line)
    print()
    print_registers(m.regs)
    print_memory(m.memory)
