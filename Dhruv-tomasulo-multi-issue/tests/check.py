# check.py
# Checks a finished simulation in two independent ways:
#   1. a plain sequential interpreter runs the same program one instruction at
#      a time (no pipeline, no prediction). The simulator must commit exactly
#      the same instructions, load/store the same values, and end with the same
#      registers and memory.
#   2. the cycle numbers in the instruction status table must follow the rules
#      of the machine (stage order, latencies, one CDB, in order issue and commit,
#      unit counts, memory port ...).

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'code'))
from main import run          # noqa: E402
from init import read_input   # noqa: E402


# ---------------------------------------------------------------------
# 1. sequential reference
# ---------------------------------------------------------------------
def reference(text):
    cfg, prog = read_input(text)
    regs = dict(('R%d' % i, 0) for i in range(32))
    regs.update(dict(('F%d' % i, 0) for i in range(32)))
    regs.update(cfg.regs)
    mem = dict(cfg.mem)
    pc, trace = 0, []
    while 0 <= pc < len(prog):
        if len(trace) > 20000:
            raise RuntimeError('reference: program does not stop')
        i = prog[pc]
        nxt = pc + 1
        val = None
        if i.op in ('Add', 'Add.d'):
            regs[i.dest or 'R0'] = val = regs[i.src1] + regs[i.src2]
        elif i.op in ('Sub', 'Sub.d'):
            regs[i.dest or 'R0'] = val = regs[i.src1] - regs[i.src2]
        elif i.op == 'Mult.d':
            regs[i.dest] = val = regs[i.src1] * regs[i.src2]
        elif i.op == 'Addi':
            regs[i.dest or 'R0'] = val = regs[i.src1] + i.imm
        elif i.op == 'Ld':
            a = int(regs[i.base]) + i.imm
            assert 0 <= a <= 255
            regs[i.dest] = val = mem.get(a, 0)
        elif i.op == 'Sd':
            a = int(regs[i.base]) + i.imm
            assert 0 <= a <= 255
            mem[a] = val = regs[i.src1]
        elif i.op in ('Beq', 'Bne'):
            t = (regs[i.src1] == regs[i.src2]) if i.op == 'Beq' else (regs[i.src1] != regs[i.src2])
            if t:
                nxt = pc + 1 + i.imm
                assert 0 <= nxt <= len(prog)
        regs['R0'] = 0
        trace.append((pc, val))
        pc = nxt
    return regs, mem, trace


# ---------------------------------------------------------------------
# 2. timing rules
# ---------------------------------------------------------------------
def overlap_max(intervals):
    """largest number of intervals that cover one cycle"""
    ev = []
    for a, b in intervals:
        ev.append((a, 1))
        ev.append((b + 1, -1))
    ev.sort()
    cur = best = 0
    for _, d in ev:
        cur += d
        best = max(best, cur)
    return best


def timing_problems(m):
    cfg = m.cfg
    rows = m.done_rows
    bad = []

    def err(r, msg):
        bad.append('#%d %s: %s' % (rows.index(r), r.ins.text, msg))

    ex_time = {'int': cfg.int_ex, 'br': cfg.int_ex, 'fpadd': cfg.fpadd_ex,
               'fpmul': cfg.fpmul_ex, 'ld': cfg.ls_ex, 'sd': cfg.ls_ex}
    last_writer = {}
    prev_issue = prev_commit = 0
    for r in rows:
        k = r.ins.kind
        i = r.ins
        # stage order and length
        if r.issue is None or r.ex_start is None:
            err(r, 'missing stage')
            continue
        if not r.issue < r.ex_start:
            err(r, 'EX must start after ISSUE')
        if r.ex_end - r.ex_start + 1 != ex_time[k]:
            err(r, 'EX length is %d, expected %d' % (r.ex_end - r.ex_start + 1, ex_time[k]))
        if r.issue < prev_issue:
            err(r, 'issue is not in order')
        prev_issue = r.issue
        if r.commit < prev_commit:
            err(r, 'commit is not in order')
        prev_commit = r.commit
        # operands
        srcs = {'int': [i.src1, i.src2], 'br': [i.src1, i.src2], 'fpadd': [i.src1, i.src2],
                'fpmul': [i.src1, i.src2], 'ld': [i.base], 'sd': [i.base]}[k]
        if i.op == 'Addi':
            srcs = [i.src1]
        for s in srcs:
            w = last_writer.get(s)
            if w is not None and not r.ex_start >= w.wb + 1:
                err(r, 'EX starts in cycle %d but %s is only broadcast in cycle %d' % (r.ex_start, s, w.wb))
        # results
        if k in ('int', 'fpadd', 'fpmul'):
            if not r.wb >= r.ex_end + 1:
                err(r, 'WB too early')
        if k == 'ld':
            if not r.mem_start >= r.ex_end + 1:
                err(r, 'MEM must start after EX')
            length = r.mem_end - r.mem_start + 1
            if length not in (1, cfg.ls_mem):
                err(r, 'MEM takes %d cycles' % length)
            if not r.wb >= r.mem_end + 1:
                err(r, 'WB too early')
        # commit
        if k in ('int', 'fpadd', 'fpmul', 'ld'):
            if not r.commit >= r.wb + 1:
                err(r, 'COMMIT must be after WB')
        elif k == 'br':
            if r.wb is not None or not r.commit >= r.ex_end + 1:
                err(r, 'branch commit too early')
        else:
            if not r.commit >= r.ex_end + 1 or r.mem_start != r.commit or r.wb is not None:
                err(r, 'store: commit/mem wrong')
            w = last_writer.get(i.src1)
            if w is not None and not r.commit >= w.wb + 1:
                err(r, 'store commits before its data is broadcast')
            if r.mem_end - r.mem_start + 1 != cfg.ls_mem:
                err(r, 'store write takes %d cycles' % (r.mem_end - r.mem_start + 1))
        if r.dest is not None:
            last_writer[r.dest] = r

    # per cycle limits
    for name, key, limit in (('issue', lambda r: r.issue, cfg.issue_width),
                             ('commit', lambda r: r.commit, cfg.commit_width),
                             ('WB', lambda r: r.wb, cfg.cdb_width)):
        count = {}
        for r in rows:
            c = key(r)
            if c is not None:
                count[c] = count.get(c, 0) + 1
        for c, n in count.items():
            if n > limit:
                bad.append('%d %s in cycle %d (limit %d)' % (n, name, c, limit))

    # units
    for kinds, units, pipelined, label in ((('int', 'br'), cfg.int_units, False, 'integer unit'),
                                            (('fpadd',), cfg.fpadd_units, True, 'FP adder'),
                                            (('fpmul',), cfg.fpmul_units, True, 'FP multiplier'),
                                            (('ld', 'sd'), cfg.ls_units, False, 'address adder')):
        sel = [r for r in rows if r.ins.kind in kinds]
        if pipelined:
            starts = {}
            for r in sel:
                starts[r.ex_start] = starts.get(r.ex_start, 0) + 1
            if starts and max(starts.values()) > units:
                bad.append('more than %d starts per cycle in the %s' % (units, label))
        elif overlap_max([(r.ex_start, r.ex_end) for r in sel]) > units:
            bad.append('more than %d instructions at the same time in the %s' % (units, label))

    # memory port: loads that read memory and store writes
    port = []
    for r in rows:
        if r.ins.kind == 'sd' or (r.ins.kind == 'ld' and r.mem_end - r.mem_start + 1 == cfg.ls_mem
                                  and r.fwd_from == -1):
            port.append((r.mem_start, r.mem_end))
    if overlap_max(port) > 1:
        bad.append('two memory accesses at the same time (one port)')

    # ROB: an entry is in the ROB from its ISSUE cycle until the cycle before its COMMIT
    # (the commit stage runs before the issue stage in the same cycle and frees the entry)
    if overlap_max([(r.issue, r.commit - 1) for r in rows]) > cfg.rob_size:
        bad.append('more than %d instructions in the ROB' % cfg.rob_size)
    return bad


def check(text, width=None, **kw):
    """Run the simulator on text and return a list of problems (empty = fine)."""
    m = run(text, width, **kw)
    problems = []
    regs, mem, trace = reference(text)
    got = [(r.pc, (r.value if r.ins.kind in ('int', 'fpadd', 'fpmul', 'ld')
                   else r.ops[1].value if r.ins.kind == 'sd' else None)) for r in m.done_rows]
    want = []
    for pc, v in trace:
        want.append((pc, v))
    # destination R0 is never written, so the simulator has no value for it
    for idx, ((gp, gv), (wp, wv)) in enumerate(zip(got, want)):
        if gp != wp:
            problems.append('instruction %d: simulator committed pc %d, reference executed pc %d' % (idx, gp, wp))
            break
        ins = m.program[wp]
        if ins.kind in ('br',) or (ins.dest is None and ins.kind != 'sd'):
            continue
        if gv != wv:
            problems.append('instruction %d (%s): value %r, reference %r' % (idx, ins.text, gv, wv))
            break
    if len(got) != len(want):
        problems.append('simulator committed %d instructions, reference executed %d' % (len(got), len(want)))
    for r in regs:
        if m.regs[r] != regs[r]:
            problems.append('register %s: %r, reference %r' % (r, m.regs[r], regs[r]))
    mem_ref = dict((a, v) for a, v in mem.items() if v != 0)
    mem_sim = dict((a, v) for a, v in m.memory.items() if v != 0)
    if mem_ref != mem_sim:
        problems.append('memory differs: %r vs reference %r' % (mem_sim, mem_ref))
    problems += timing_problems(m)
    return problems, m
