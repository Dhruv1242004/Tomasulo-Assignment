# commit.py
# COMMIT stage: instructions leave the ROB in program order, at most "commit
# width" per cycle (same as the issue width unless the input file says otherwise).
#   - ALU / FP / load : need their WB in an earlier cycle, then write the register
#   - branch          : needs to be resolved (its EX ended in an earlier cycle)
#   - store           : needs address, data and a free memory port. It writes the
#                       memory now (the write takes "Cycles in Mem" cycles).

from init import SimError


def commit(m):
    t = m.cycle
    n = 0
    while n < m.cfg.commit_width and m.rob:
        h = m.rob[0]
        k = h.ins.kind

        if k == 'br':
            if h.ex_end is None or h.ex_end >= t:
                break
            target = h.pc + 1 + h.ins.imm
            if h.taken and not 0 <= target <= len(m.program):
                raise SimError("%s (instruction %d) jumps to instruction %d, outside the program" %
                               (h.ins.text, h.pc, target))
            m.n_branches += 1
            m.n_mispredicts += 1 if h.mispredicted else 0

        elif k == 'sd':
            if h.addr_visible is None or h.addr_visible > t:
                break
            if not h.ops[1].ready(t):
                break
            if any(u.mem_end >= t for u in m.port_users):
                break
            if not 0 <= h.address <= 255:
                raise SimError("%s (instruction %d) uses address %d, outside the 256 byte memory" %
                               (h.ins.text, h.pc, h.address))
            m.memory[h.address] = h.ops[1].value
            h.mem_start = t
            h.mem_end = t + m.cfg.ls_mem - 1
            m.port_users.append(h)
            m.lsq.remove(h)

        else:
            if h.wb is None or h.wb >= t:
                break
            if k == 'ld' and not 0 <= h.address <= 255:
                raise SimError("%s (instruction %d) uses address %d, outside the 256 byte memory" %
                               (h.ins.text, h.pc, h.address))
            if h.dest is not None:
                m.regs[h.dest] = h.value

        h.commit = t
        m.rob.popleft()
        if h.dest is not None and m.rat.get(h.dest) is h:
            del m.rat[h.dest]
        m.done_rows.append(h)
        m.last_commit_cycle = t
        n += 1
