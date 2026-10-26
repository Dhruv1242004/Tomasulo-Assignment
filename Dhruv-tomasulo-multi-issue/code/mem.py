# mem.py
# MEM stage of loads.
#   - A load whose address is known first looks at the older stores in the
#     load/store queue. If the nearest older store with the same address has
#     its data, the load takes the value from it (forwarding, 1 cycle).
#   - Otherwise it reads the memory (the memory has one port and is not
#     pipelined, so one access at a time, "Cycles in Mem" cycles).
#   - With "load speculation = on" (the default) a load does not wait for older
#     stores whose address is still unknown. If such a store turns out to have
#     the same address, exe.py finds this and the load is executed again.
# Stores write the memory when they commit (see commit.py).


def port_free(m, t):
    return all(u.mem_end < t for u in m.port_users)


def memory_read(m, address):
    return m.memory.get(address, 0)


def _decide(m, e, t):
    """What can load e do in cycle t: ('forward', store), ('memory',) or ('wait',)."""
    older = [s for s in m.lsq if s.seq < e.seq and s.ins.kind == 'sd']
    unknown = [s for s in older if s.addr_visible is None or s.addr_visible > t]
    if unknown and not m.cfg.load_speculation:
        return ('wait',)
    for s in reversed(older):                   # nearest store first
        if s.addr_visible is None or s.addr_visible > t:
            continue
        if s.address == e.address:
            if s.ops[1].ready(t):
                return ('forward', s)
            return ('wait',)                    # same address, data not ready yet
    return ('memory',)


def mem(m):
    t = m.cycle
    m.port_users = [u for u in m.port_users if u.mem_end >= t]
    # a load leaves the queue after it got its value
    m.lsq = [e for e in m.lsq if not (e.ins.kind == 'ld' and e.mem_end is not None and e.mem_end < t)]

    started = 0
    for e in m.lsq:                             # oldest first
        if started >= m.cfg.ls_units:
            break
        if e.ins.kind != 'ld' or e.mem_start is not None:
            continue
        if e.addr_visible is None or e.addr_visible > t:
            continue
        what = _decide(m, e, t)
        if what[0] == 'forward':
            e.mem_start = e.mem_end = t
            e.fwd_from = what[1].seq
            e.value = what[1].ops[1].value
            m.results.append((e, t))
            started += 1
        elif what[0] == 'memory' and port_free(m, t):
            e.mem_start = t
            e.mem_end = t + m.cfg.ls_mem - 1
            e.fwd_from = -1
            e.value = memory_read(m, e.address)
            m.port_users.append(e)
            m.results.append((e, e.mem_end))
            started += 1
