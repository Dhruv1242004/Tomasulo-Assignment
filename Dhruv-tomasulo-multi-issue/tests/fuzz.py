# fuzz.py
# Random programs with random hardware settings, run at issue widths 1-4 and
# checked with check.py.   Usage: python3 fuzz.py [number of programs] [first seed]

import random
import sys

from check import check


def make_program(rng):
    """Random program text (config + registers + memory + instructions)."""
    r = rng.randint
    cfg = ["                 # of rs   EX   Mem   # of FUs",
           "Integer adder    %d  %d    %d" % (r(1, 5), r(1, 4), r(1, 2)),
           "FP adder         %d  %d    %d" % (r(1, 4), r(1, 5), r(1, 2)),
           "FP multiplier    %d  %d    %d" % (r(1, 4), r(1, 8), r(1, 2)),
           "Load/store unit  %d  %d  %d  %d" % (r(1, 5), r(1, 3), r(1, 6), r(1, 2)),
           "ROB entries = %d" % r(2, 20),
           "CDB width = %d" % rng.choice([1, 1, 1, 2]),
           "Load speculation = %s" % rng.choice(['on', 'on', 'off'])]
    if rng.random() < 0.3:
        cfg.append("Commit width = %d" % r(1, 4))
    # R1-R3: addresses, R4: data, R5/R6: constants used to build addresses, R7: loop counter
    regs = ["R1=%d" % (4 * r(1, 3)), "R2=%d" % (4 * r(1, 3)), "R3=%d" % (4 * r(1, 3)),
            "R4=%d" % r(-3, 6), "R5=4", "R6=%d" % rng.choice([0, 4])]
    for f in range(1, 7):
        regs.append("F%d=%s" % (f, rng.choice(['0.5', '1.5', '2.0', '1', '0.25', '3'])))
    cfg.append(', '.join(regs))
    mems = ["Mem[%d]=%s" % (4 * a, rng.choice(['1', '2.5', '3', '0.5', '7'])) for a in range(0, 14) if rng.random() < 0.5]
    if mems:
        cfg.append(', '.join(mems))

    def block(n, loop=False):
        out = []
        while len(out) < n:
            x = rng.random()
            left = n - len(out) - 1
            if x < 0.06:
                # a store whose address is calculated slowly, then a load from the same place
                b = r(1, 3)
                out += ["Addi R%d, R0, %d" % (b, 4 * r(1, 3))]
                out += ["Add R%d, R%d, R0" % (b, b) for _ in range(r(1, 3))]
                out.append("Sd F%d, 0(R%d)" % (r(1, 6), b))
                out.append("Ld F%d, 0(R%d)" % (r(1, 6), rng.choice([1, 2, 3])))
            elif x < 0.12:
                out.append("Addi R%d, R0, %d" % (r(1, 3), 4 * r(1, 3)))          # new base register
            elif x < 0.17:
                out.append("Add R%d, R5, R6" % r(1, 3))                          # base from a slower path
            elif x < 0.27:
                out.append("%s R4, R4, R4" % rng.choice(['Add', 'Sub']))
            elif x < 0.32:
                out.append("Addi R4, R4, %d" % r(-4, 4))
            elif x < 0.44:
                out.append("%s F%d, F%d, F%d" % (rng.choice(['Add.d', 'Sub.d']), r(1, 6), r(1, 6), r(1, 6)))
            elif x < 0.52:
                out.append("Mult.d F%d, F%d, F%d" % (r(1, 6), r(1, 6), r(1, 6)))
            elif x < 0.74:
                out.append("Ld F%d, %d(R%d)" % (r(1, 6), 4 * r(-1, 1), r(1, 3)))
            elif x < 0.92:
                out.append("Sd F%d, %d(R%d)" % (r(1, 6), 4 * r(-1, 1), r(1, 3)))
            elif left >= 0:
                k = r(0, min(3, left))
                out.append("%s R4, R%d, %d" % (rng.choice(['Beq', 'Bne']), rng.choice([0, 5, 6]), k))
        return out

    body = block(r(4, 14))
    if rng.random() < 0.6:
        pre = block(r(0, 4))
        loop = block(r(2, 6))
        n = r(1, 4)
        prog = pre + ["Addi R7, R0, %d" % n] + loop + ["Addi R7, R7, -1"]
        prog.append("Bne R7, R0, %d" % (-(len(loop) + 2)))
        prog += body
    else:
        prog = body
    # a forward branch that jumps over the end of the block is fine (target = end of program)
    return '\n'.join(cfg + [''] + prog) + '\n'


def same(a, b):
    return a == b


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    bad = 0
    cycles = 0
    cov = {'branches': 0, 'mispredicted': 0, 'order violations': 0, 'squashed': 0, 'forwarded loads': 0,
           'loads from memory': 0, 'stores': 0}
    for seed in range(first, first + count):
        text = make_program(random.Random(seed))
        for w in (1, 2, 3, 4):
            try:
                problems, m = check(text, w, max_cycles=20000)
                cycles += m.last_commit_cycle
                cov['branches'] += m.n_branches
                cov['mispredicted'] += m.n_mispredicts
                cov['order violations'] += m.n_violations
                cov['squashed'] += m.n_squashed
                cov['forwarded loads'] += sum(1 for r in m.done_rows if r.ins.kind == 'ld' and r.fwd_from >= 0)
                cov['loads from memory'] += sum(1 for r in m.done_rows if r.ins.kind == 'ld' and r.fwd_from == -1)
                cov['stores'] += sum(1 for r in m.done_rows if r.ins.kind == 'sd')
            except Exception as e:                      # noqa
                problems = ['exception: %r' % e]
            if problems:
                bad += 1
                print('seed %d width %d: %s' % (seed, w, problems[:3]))
                break
    print('%d programs x 4 widths checked, %d failed (%d simulated cycles in total)' % (count, bad, cycles))
    print('coverage: ' + ', '.join('%s %d' % kv for kv in cov.items()))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
