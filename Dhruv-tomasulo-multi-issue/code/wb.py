# wb.py
# WB stage: results go over the common data bus (CDB). By default one result
# per cycle, the one that finished first. The value is written into the ROB and
# the instructions waiting for it can use it from the next cycle on.


def wb(m):
    t = m.cycle
    ready = [r for r in m.results if r[1] < t]       # finished in an earlier cycle
    ready.sort(key=lambda r: (r[1], r[0].seq))
    for r in ready[:m.cfg.cdb_width]:
        m.results.remove(r)
        e = r[0]
        e.wb = t
        for x in m.rob:                              # wake up the waiting operands
            for op in x.ops:
                if op.producer is e:
                    op.value = e.value
                    op.avail = t + 1
                    op.producer = None
