# exe.py
# EX stage.
#   - ALU / FP instructions run in their functional unit
#   - loads and stores calculate their address in the address adder of the
#     load/store unit (they do not use the integer ALU)
#   - branches are resolved at the end of their EX stage
# An instruction can start EX in the cycle after it was issued, and when all
# its operands were broadcast in an earlier cycle.

from recover import squash


def _purge(m):
    """Forget instructions whose EX stage ended in an earlier cycle."""
    t = m.cycle
    for k in m.in_ex:
        m.in_ex[k] = [e for e in m.in_ex[k] if e.ex_end >= t]
    m.addr_unit = [e for e in m.addr_unit if e.ex_end >= t]


def _compute(e):
    a = e.ops[0].value
    b = e.ops[1].value
    op = e.ins.op
    if op in ('Add', 'Addi', 'Add.d'):
        return a + b
    if op in ('Sub', 'Sub.d'):
        return a - b
    return a * b                                # Mult.d


def _finish_branch(m, e):
    t = m.cycle
    a, b = e.ops[0].value, e.ops[1].value
    e.taken = (a == b) if e.ins.op == 'Beq' else (a != b)
    target = e.pc + 1 + e.ins.imm
    actual_next = target if e.taken else e.pc + 1

    # update the predictor
    idx = e.pc & 7
    old = m.btb[idx]
    if e.taken:
        m.btb[idx] = (e.pc, target, 1)
    elif old is not None and old[0] == e.pc:
        m.btb[idx] = (e.pc, old[1], 0)

    if actual_next != e.pred_next:
        e.mispredicted = True
        m.events.append("cycle %d: %s (instruction %d) was mispredicted, %d younger instructions "
                        "squashed, fetch restarts at instruction %d in cycle %d" %
                        (t, e.ins.text, e.pc, sum(1 for x in m.rob if x.seq > e.seq),
                         actual_next, t + 2))
        squash(m, e.seq, actual_next, t)


def _finish_address(m, e):
    t = m.cycle
    base = e.ops[0].value
    e.address = int(base) + e.ins.imm
    e.addr_visible = t + 1
    if e.ins.kind != 'sd':
        return
    # a load that is younger than this store, has the same address and got its
    # value from somewhere older than this store has read a wrong value
    bad = None
    for x in m.rob:
        if (x.seq > e.seq and x.ins.kind == 'ld' and x.mem_start is not None
                and x.address == e.address and x.fwd_from < e.seq):
            if bad is None or x.seq < bad.seq:
                bad = x
    if bad is not None:
        m.n_violations += 1
        m.events.append("cycle %d: load %s (instruction %d) read address %d before the older store "
                        "%s (instruction %d) knew its address, so it is executed again; fetch "
                        "restarts at instruction %d in cycle %d" %
                        (t, bad.ins.text, bad.pc, e.address, e.ins.text, e.pc, bad.pc, t + 2))
        squash(m, bad.seq - 1, bad.pc, t)


def exe(m):
    t = m.cycle
    _purge(m)

    # ---- start of EX (an instruction with a 1 cycle EX also ends in this cycle) ----
    for k in ('int', 'fpadd', 'fpmul'):
        ready = [e for e in m.rs[k]
                 if e.issue < t and all(op.ready(t) for op in e.ops)]
        if m.pipelined[k]:
            free = m.units[k] - sum(1 for e in m.in_ex[k] if e.ex_start == t)
        else:
            free = m.units[k] - len(m.in_ex[k])
        for e in ready[:max(free, 0)]:
            e.ex_start = t
            e.ex_end = t + m.ex_time[k] - 1
            m.rs[k].remove(e)                   # the reservation station is free again
            m.in_ex[k].append(e)

    # loads and stores: address calculation, oldest first
    free = m.cfg.ls_units - len(m.addr_unit)
    for e in m.lsq:
        if free <= 0:
            break
        if e.ex_start is None and e.issue < t and e.ops[0].ready(t):
            e.ex_start = t
            e.ex_end = t + m.cfg.ls_ex - 1
            m.addr_unit.append(e)
            free -= 1

    # ---- end of EX for the instructions that finish in this cycle ----
    finishing = []
    for k in m.in_ex:
        finishing += [e for e in m.in_ex[k] if e.ex_end == t]
    finishing += [e for e in m.addr_unit if e.ex_end == t]
    finishing.sort(key=lambda e: e.seq)
    for e in finishing:
        if e.squashed:                          # killed by an older branch in this cycle
            continue
        if e.ins.kind == 'br':
            _finish_branch(m, e)
        elif e.ins.kind in ('ld', 'sd'):
            _finish_address(m, e)
        else:
            e.value = _compute(e)
            m.results.append((e, t))            # can be broadcast from the next cycle on
