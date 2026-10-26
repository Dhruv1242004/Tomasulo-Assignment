# issue.py
# ISSUE stage: fetch, decode, rename and put up to "issue width" instructions
# (in program order) into the ROB and into a reservation station or the
# load/store queue. A branch is predicted here.

from init import ROBEntry, Operand


def rs_class(ins):
    """Which reservation station an instruction goes to (None: load/store queue)."""
    if ins.kind in ('int', 'br'):      # branches use the integer ALU
        return 'int'
    if ins.kind in ('fpadd', 'fpmul'):
        return ins.kind
    return None


def read_operand(m, reg):
    """Value of a register for a new instruction, or the ROB entry we must wait for."""
    if reg == 'R0':
        return Operand(0, 0)
    producer = m.rat.get(reg)
    if producer is None:                        # value is in the register file
        return Operand(m.regs[reg], 0)
    if producer.wb is not None:                 # already broadcast, value sits in the ROB
        return Operand(producer.value, producer.wb + 1)
    return Operand(None, None, producer)        # wait for the broadcast


def predict_branch(m, pc):
    """1-bit predictor + BTB with 8 entries, indexed with the low 3 bits of the word address."""
    entry = m.btb[pc & 7]
    if entry is not None and entry[0] == pc and entry[2] == 1:
        return True, entry[1]
    return False, pc + 1


def issue(m):
    t = m.cycle
    cfg = m.cfg
    if t < m.issue_block:                       # recovering from a misprediction
        return
    issued = 0
    while issued < cfg.issue_width:
        if m.pc < 0 or m.pc >= len(m.program):  # nothing to fetch
            break
        ins = m.program[m.pc]
        cls = rs_class(ins)

        # in order issue: stop at the first instruction that finds no room
        if len(m.rob) >= cfg.rob_size:
            break
        if cls is not None and len(m.rs[cls]) >= m.rs_size[cls]:
            break
        if cls is None and len(m.lsq) >= cfg.ls_rs:
            break

        # new ROB entry
        e = ROBEntry(m.seq, 'ROB%d' % (m.seq % cfg.rob_size), m.pc, ins, t)
        m.seq += 1

        # source operands (read before the destination is renamed)
        if ins.op == 'Addi':
            e.ops = [read_operand(m, ins.src1), Operand(ins.imm, 0)]
        elif ins.kind == 'ld':
            e.ops = [read_operand(m, ins.base)]
        elif ins.kind == 'sd':
            e.ops = [read_operand(m, ins.base), read_operand(m, ins.src1)]
        else:
            e.ops = [read_operand(m, ins.src1), read_operand(m, ins.src2)]

        # rename the destination
        if e.dest is not None:
            m.rat[e.dest] = e

        m.rob.append(e)
        if cls is not None:
            m.rs[cls].append(e)
        else:
            m.lsq.append(e)
            e.in_lsq = True

        # next instruction to fetch
        if ins.kind == 'br':
            e.pred_taken, e.pred_next = predict_branch(m, m.pc)
            m.pc = e.pred_next
            issued += 1
            if e.pred_taken:                    # fetch cannot go past a taken branch in one cycle
                break
        else:
            m.pc += 1
            issued += 1
